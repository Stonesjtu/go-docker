from __future__ import print_function

from godocker.iExecutorPlugin import IExecutorPlugin
import json
import time
import os
import sys
import redis
import urllib3
import socket
import signal
import getpass

from threading import Thread
from bson.json_util import dumps
from os.path import abspath, join, dirname

from pymesos import MesosSchedulerDriver, Scheduler
from addict import Dict



config = Dict(
    redis_host='localhost',
    redis_port=6379,
    redis_db=0,
    redis_prefix='god',
    )



class MesosThread(Thread):

    def set_driver(self, driver):
        self.driver = driver

    def run(self):
        self.driver.run()

    def stop(self):
        self.driver.stop()


class MesosScheduler(Scheduler):

    def __init__(self, executor):
        self.executor = executor
        self.Terminated = False
        self.jobs_handler = None
        self.network = None

    def features(self):
        '''
        Get supported features

        :return: list of features within ['docker-plugin-zfs']
        '''
        return ['docker-plugin-zfs', 'interactive', 'cni', 'gpus']

    def set_config(self, config):
        self.config = config
        self.redis_handler = redis.StrictRedis(host=self.config['redis_host'], port=self.config['redis_port'], db=self.config['redis_db'], decode_responses=True)

    def set_logger(self, logger):
        self.logger = logger

    def resourceOffers(self, driver, offers):
        filters = {'refuse_seconds': 5}
        for offer in offers:
            self.logger.debug('Recieving offer:' + json.dumps(offer))

            available_tasks = self.getAvailableTasks(offer)

            tasks_to_launch = self.addOfferInfo(available_tasks, offer)

            driver.launchTasks(offer.id, tasks_to_launch, filters)

    def getResource(self, res, name):
        for r in res:
            if r.name == name:
                return r.scalar.value
        return 0

    def statusUpdate(self, driver, update):
        self.logger.debug('Status update TID %s %s',
                      update.task_id.value,
                      update.state)

    def getTasksFromDB(self):
        '''
        Get the list of tasks from database or redis cache
        '''
        tasks = []
        redis_task = self.redis_handler.lpop(self.config['redis_prefix'] + ':mesos:pending')
        while redis_task is not None:
            task = json.loads(redis_task)
            task = self.taskAdapter(task)
            self.logger.debug('loading tasks from database: ' + json.dumps(task))
            tasks.append(task)
            redis_task = self.redis_handler.lpop(self.config['redis_prefix'] + ':mesos:pending')

        return tasks

    def taskAdapter(self, redis_task):
        '''
        transform the json formatted redis task into a mesos task, without the execution info
        '''
        task = Dict()
        redis_task = Dict(redis_task)
        task.task_id = redis_task.id
        task.name = redis_task.meta.name
        requirements = redis_task.requirements
        task.resources = [
            dict(name='cpus', type='SCALAR', scalar={'value': requirements.cpu}),
            dict(name='mem', type='SCALAR', scalar={'value': requirements.ram * 1000}),
            dict(name='gpus', type='SCALAR', scalar={'value': requirements.gpu or 0}),
        ]

        # containerizer
        container = Dict(type='MESOS')
        # image provider
        container.mesos = Dict(type='DOCKER', docker={'name':redis_task.container.image})
        task.container = container

        task.executor.command = Dict(value=redis_task.command.script)

        return task

    def getAvailableTasks(self, offer):
        for pending_task in self.pending_tasks:
            if self.hasEnoughResource(offer,pending_task):
                return [pending_task]
        return []

    def addOfferInfo(self, available_tasks, offer):
        tasks = []
        for available_task in available_tasks:
            task = Dict(available_task)
            task.agent_id.value = offer.agent_id.value
            tasks.append(task)
        return tasks
        # return [task for task in self.pending_tasks if self.hasEnoughResource(offer, task)]

    def getResourcesNames(self, resources):

        return set([resource.name for resource in resources])


    def hasEnoughResource(self, offer, task):
        '''
        check wether the resources are enough. Currently only for scalar
        '''
        offer_resources = offer.resources
        requested_resources = task.resources
        for resource_name in self.getResourcesNames(requested_resources):
            if self.getResource(offer_resources, resource_name) < self.getResource(requested_resources, resource_name):
                logging.warn("Not enough %s" % resource_name)
                return False
        return True

    

class Mesos(IExecutorPlugin):

    def get_name(self):
        return "mesos"

    def get_type(self):
        return "Executor"

    def features(self):
        '''
        Get supported features

        :return: list of features within ['kill', 'pause','resources.port', 'cni']
        '''
        feats = ['kill', 'resources.port', 'cni', 'interactive']
        if self.cfg['mesos']['native_gpu']:
            feats.append('gpus')
        return feats

    def set_config(self, cfg):
        self.cfg = cfg
        self.Terminated = False
        self.driver = None
        self.redis_handler = redis.StrictRedis(host=self.cfg['redis_host'], port=self.cfg['redis_port'], db=self.cfg['redis_db'], decode_responses=True)

    def open(self, proc_type):
        '''
        Request start of executor if needed
        '''
        if proc_type is not None and proc_type == 1:
            # do not start framework on watchers
            return
        import logging
        logging.basicConfig(level=logging.DEBUG)


        executor = Dict()
        executor.executor_id.value = 'MinimalExecutor'
        executor.name = executor.executor_id.value


        framework = Dict()
        framework.user = getpass.getuser()
        framework.name = "MinimalFramework"
        framework.hostname = socket.gethostname()
        framework.failover_timeout = 3600 * 24 * 7  # 1 week
        prevFrameworkId = self.redis_handler.get(self.cfg['redis_prefix'] + ':mesos:frameworkId')
        if prevFrameworkId:
            # Reuse previous framework identifier
            self.logger.info("Mesos:FrameworkId:" + str(prevFrameworkId))
            framework.id = prevFrameworkId
        if os.getenv("MESOS_CHECKPOINT"):
            self.logger.info("Enabling checkpoint for the framework")
            framework.checkpoint = True

        driver = MesosSchedulerDriver(
            MesosScheduler(executor),
            framework,
            self.cfg['mesos']['master'],
            use_addict=True,
        )

        driver_thread = Thread(MesosThread(driver))
        driver_thread.start()

        print('Scheduler running, Ctrl+C to quit.')


    def close(self):
        '''
        Request end of executor if needed
        '''
        if self.driver is not None:
            self.driver.stop(True)
        self.Terminated = True

    def run_all_tasks(self, tasks, callback=None):
        '''
        Execute all task list on executor system, all tasks must be executed together

        NOT IMPLEMENTED, will reject all tasks

        :param tasks: list of tasks to run
        :type tasks: list
        :param callback: callback function to update tasks status (running/rejected)
        :type callback: func(running list,rejected list)
        :return: tuple of submitted and rejected/errored tasks
        '''
        self.logger.error('run_all_tasks not implemented')
        return ([], tasks)

    def run_tasks(self, tasks, callback=None):
        '''
        Execute task list on executor system

        :param tasks: list of tasks to run
        :type tasks: list
        :param callback: callback function to update tasks status (running/rejected)
        :type callback: func(running list,rejected list)
        :return: tuple of submitted and rejected/errored tasks
        '''
        # Add tasks in redis to be managed by mesos
        self.redis_handler.set(self.cfg['redis_prefix'] + ':mesos:offer', 0)
        for task in tasks:
            self.redis_handler.rpush(self.cfg['redis_prefix'] + ':mesos:pending', dumps(task))
        # Wait for offer receival and treatment
        self.logger.debug('Mesos:WaitForOffer:Begin')
        mesos_offer = int(self.redis_handler.get(self.cfg['redis_prefix'] + ':mesos:offer'))
        while mesos_offer != 1 and not self.Terminated:
            self.logger.debug('Mesos:WaitForOffer:Wait')
            time.sleep(1)
            mesos_offer = int(self.redis_handler.get(self.cfg['redis_prefix'] + ':mesos:offer'))
        self.logger.debug('Mesos:WaitForOffer:End')
        # Get result
        rejected_tasks = []
        running_tasks = []
        redis_task = self.redis_handler.lpop(self.cfg['redis_prefix'] + ':mesos:running')
        while redis_task is not None:
            task = json.loads(redis_task)
            task['container']['status'] = 'initializing'
            running_tasks.append(task)
            redis_task = self.redis_handler.lpop(self.cfg['redis_prefix'] + ':mesos:running')
        redis_task = self.redis_handler.lpop(self.cfg['redis_prefix'] + ':mesos:rejected')
        while redis_task is not None:
            task = json.loads(redis_task)
            rejected_tasks.append(task)
            redis_task = self.redis_handler.lpop(self.cfg['redis_prefix'] + ':mesos:rejected')

        return (running_tasks, rejected_tasks)

    def watch_tasks(self, task):
        '''
        Get task status

        Must update task with following params if task is over:
            task['container']['meta']['State']['ExitCode']
        In case of node failure:
            task['status']['failure'] = { 'reason': reason_of_failure,
                                           'nodes': [ node(s)_where_failure_occured]}


        :param task: current task
        :type task: Task
        :param over: is task over
        :type over: bool
        '''
        self.logger.debug('Mesos:Task:Check:Running:' + str(task['id']))
        mesos_task = self.redis_handler.get(self.cfg['redis_prefix'] + ':mesos:over:' + str(task['id']))
        if mesos_task is not None and int(mesos_task) in [2, 3, 4, 5, 7]:
            self.logger.debug('Mesos:Task:Check:IsOver:' + str(task['id']))
            exit_code = int(mesos_task)
            if 'State' not in task['container']['meta']:
                task['container']['meta']['State'] = {}
            if exit_code == 2:
                task['container']['meta']['State']['ExitCode'] = 0
            elif exit_code == 4:
                task['container']['meta']['State']['ExitCode'] = 137
            else:
                task['container']['meta']['State']['ExitCode'] = 1
            task['status']['reason'] = None
            if int(mesos_task) in [3, 5, 7]:
                reason = self.redis_handler.get(self.cfg['redis_prefix'] + ':mesos:over:' + str(task['id']) + ':reason')
                if not reason:
                    reason = None
                if reason is None and int(mesos_task) == 3:
                    task['status']['reason'] = None
                else:
                    task['status']['reason'] = 'System crashed or failed to start the task: ' + str(reason)
                node_name = None
                if 'Node' in task['container']['meta'] and 'Name' in task['container']['meta']['Node']:
                    node_name = task['container']['meta']['Node']['Name']
                if 'failure' not in task['status']:
                    task['status']['failure'] = {'reason': reason, 'nodes': []}
                if node_name:
                    task['status']['failure']['nodes'].append(node_name)
            self.redis_handler.delete(self.cfg['redis_prefix'] + ':mesos:over:' + str(task['id']))
            self.redis_handler.delete(self.cfg['redis_prefix'] + ':mesos:over:' + str(task['id']) + ':reason')
            return (task, True)
        else:
            self.logger.debug('Mesos:Task:Check:IsRunning:' + str(task['id']))
            self.get_container_id(task)
            return (task, False)

    def get_container_id(self, task):
        '''
        Extract container id from slave
        '''
        if 'id' not in task['container']:
            task['container']['id'] = None

        if task['container']['id']:
            return

        if self.cfg['mesos']['unified']:
            http = urllib3.PoolManager()
            r = None
            try:
                r = http.urlopen('GET', 'http://' + task['container']['meta']['Node']['Name'] + ':5051/containers/' + str(task['id']))
                if r.status == 200:
                    containers = json.loads(r.data)
                    for container in containers:
                        task['container']['id'] = container['container_id']
                    self.jobs_handler.update({'id': task['id']}, {'$set': {'container.id': task['container']['id']}})
            except Exception as e:
                self.logger.error('Could not get container identifier: ' + str(e))


    def kill_task(self, task):
        '''
        Kills a running task

        :param tasks: task to kill
        :type tasks: Task
        :return: (Task, over) over is True if task could be killed
        '''
        self.logger.debug('Mesos:Task:Kill:Check:' + str(task['id']))
        mesos_task = self.redis_handler.get(self.cfg['redis_prefix'] + ':mesos:over:' + str(task['id']))
        if mesos_task is not None and int(mesos_task) in [2, 3, 4, 5, 7]:
            self.logger.debug('Mesos:Task:Kill:IsOver:' + str(task['id']))
            exit_code = int(mesos_task)
            if 'State' not in task['container']['meta']:
                task['container']['meta']['State'] = {}
            if exit_code == 2:
                task['container']['meta']['State']['ExitCode'] = 0
            elif exit_code == 4:
                task['container']['meta']['State']['ExitCode'] = 137
            else:
                task['container']['meta']['State']['ExitCode'] = 1
            self.redis_handler.delete(self.cfg['redis_prefix'] + ':mesos:over:' + str(task['id']))
            return (task, True)
        else:
            self.logger.debug('Mesos:Task:Kill:IsRunning:' + str(task['id']))
            self.redis_handler.rpush(self.cfg['redis_prefix'] + ':mesos:kill', str(task['id']))

            return (task, None)

        return (task, True)

    def suspend_task(self, task):
        '''
        Suspend/pause a task

        :param tasks: task to suspend
        :type tasks: Task
        :return: (Task, over) over is True if task could be suspended
        '''
        self.logger.error('Not supported')
        return (task, False)

    def resume_task(self, task):
        '''
        Resume/restart a task

        :param tasks: task to resumed
        :type tasks: Task
        :return: (Task, over) over is True if task could be resumed
        '''
        self.logger.error('Not supported')
        return (task, False)

    def usage(self):
        '''
        Get resource usage

        :return: array of nodes with used/total resources with
            {
                'name': slave_hostname,
                'cpu': (cpus_used, cpu_total),
                'mem': (mem_used, mem_total),
                'gpus': (gpus_used, gpus_total)
                'disk': (disk_used, disk_total),
            }

        '''
        mesos_master = self.redis_handler.get(self.cfg['redis_prefix'] + ':mesos:master')
        if not mesos_master:
            return []

        http = urllib3.PoolManager()
        r = http.urlopen('GET', 'http://' + mesos_master + '/master/state.json')
        master = json.loads(r.data)

        slaves = []
        for slave in master['slaves']:
            if slave['active']:
                r = http.urlopen('GET', 'http://' + slave['hostname'] + ':5051/metrics/snapshot')
                state = json.loads(r.data)
                if 'slave/gpus_total' not in state:
                    state['slave/gpus_total'] = 0
                    state['slave/gpus_used'] = 0
                slaves.append({
                    'name': slave['hostname'],
                    'cpu': (int(state['slave/cpus_used']), int(state['slave/cpus_total'])),
                    'gpus': (int(state['slave/gpus_used']), int(state['slave/gpus_total'])),
                    'mem': (int(state['slave/mem_used']), int(state['slave/mem_total'])),
                    'disk': (int(state['slave/disk_used']), int(state['slave/disk_total']))
                })
        return slaves
