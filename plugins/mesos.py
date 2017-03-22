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
import uuid

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

    def stop(self, failover):
        self.driver.stop(failover=failover)


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

    def registered(self, driver, frameworkId, masterInfo):
        self.logger.info("Registered with framework ID %s" % frameworkId.value)
        self.redis_handler.set(
            self.config['redis_prefix'] + ':mesos:frameworkId',
            frameworkId.value
            )

        # Reconcile at startup
        # if 'mesos' in self.config and 'reconcile' in self.config['mesos'] and self.config['mesos']['reconcile']:
        #     self.logger.info("Reconcile any running task")
        #     tasks = self.jobs_handler.find({'status.primary': 'running'})
        #     running_tasks = []
        #     for task in tasks:
        #         task_status = mesos_pb2.TaskStatus()
        #         task_id = mesos_pb2.TaskID()
        #         task_id.value = str(task['id'])
        #         task_status.task_id.MergeFrom(task_id)
        #         task_status.state = 1
        #         self.logger.debug('Mesos:Reconcile:Task:' + str(task['id']))
        #         running_tasks.append(task_status)
        #     driver.reconcileTasks(running_tasks)


    def resourceOffers(self, driver, offers):
        filters = {'refuse_seconds': 5}
        for offer in offers:

            self.logger.debug('Recieving offer:' + offer.hostname)

            available_tasks = self.getAvailableTasks(offer)

            tasks_to_launch = self.addOfferInfo(available_tasks, offer)

            # TODO: for test only. mock task
            tasks_to_launch[0].task_id.value = str(uuid.uuid4())
            tasks_to_launch[0].container.mesos.image.docker.name='busybox'
            self.logger.debug('launching task:' + str(tasks_to_launch))
            driver.launchTasks(offer.id, tasks_to_launch, filters)

    def getResource(self, res, name):
        for r in res:
            r = Dict(r)
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
        redis_tasks = self.redis_handler.lrange(self.config['redis_prefix'] + ':mesos:pending', 0, -1)
        for redis_task in redis_tasks:
            task = json.loads(redis_task)
            task = self.taskAdapter(task)
            # self.logger.debug('loading tasks from database: ' + json.dumps(task))
            tasks.append(task)
            
        return tasks

    def taskAdapter(self, request_task):
        '''
        transform the json formatted redis task into a mesos task, without the execution info
        '''
        task = Dict()
        request_task = Dict(request_task)
        task.task_id.value = str(request_task.id)
        task.name = request_task.meta.name
        requirements = request_task.requirements
        task.resources = [
            dict(name='cpus', type='SCALAR', scalar={'value': requirements.cpu}),
            dict(name='mem', type='SCALAR', scalar={'value': requirements.ram * 1000}),
            dict(name='gpus', type='SCALAR', scalar={'value': requirements.gpu or 0}),
        ]


        task.container = self.containerAdapter(request_task.container)


        task.executor.command = Dict(value=request_task.command.script)
        task.executor.executor_id.value = 'MinimalExecutor'

        return task

    def containerAdapter(self, request_container):
        # containerizer
        container = Dict(type='MESOS')
        # image provider
        container.mesos.image = Dict(
            type='DOCKER',
            docker={'name':request_container.image}
            )

        #for debug
        container.type = 'DOCKER'
        container.docker.image = 'busybox'
        container.volumes = self.volumesAdapter(request_container.volumes)
        return container

    def volumesAdapter(self, request_volumes):
        volumes = []
        for request_volume in request_volumes:
            volume = self.volumeAdapter(request_volume)
            volumes.append(volume)
        return volumes

    def volumeAdapter(self, request_volume):
        volume = Dict()

        # the container path is default to host path if not set
        volume.host_path = request_volume.path
        volume.container_path = request_volume.mount or volume.path

        if request_volume.acl == 'rw':
            volume.mode = 'RW'
        else:
            volume.mode = 'RO'
        return volume

    def getAvailableTasks(self, offer):
        self.pending_tasks = self.getTasksFromDB()
        for pending_task in self.pending_tasks:
            if self.hasEnoughResource(offer,pending_task):
                self.logger.debug('\nget pending tasks: '.join(pending_task.task_id))
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

        return set([resource['name'] for resource in resources])


    def hasEnoughResource(self, offer, task):
        '''
        check wether the resources are enough. Currently only for scalar
        '''
        offer_resources = offer.resources
        requested_resources = task.resources
        for resource_name in self.getResourcesNames(requested_resources):
            if self.getResource(offer_resources, resource_name) < self.getResource(requested_resources, resource_name):
                self.logger.warn("Not enough %s" % resource_name)
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
            framework.id.value = prevFrameworkId
        if os.getenv("MESOS_CHECKPOINT"):
            self.logger.info("Enabling checkpoint for the framework")
            framework.checkpoint = True

        mesos_scheduler = MesosScheduler(executor)
        mesos_scheduler.set_logger(self.logger)
        mesos_scheduler.set_config(self.cfg)
        driver = MesosSchedulerDriver(
            mesos_scheduler,
            framework,
            self.cfg['mesos']['master'],
            use_addict=True,
        )

        driver_thread = MesosThread()
        driver_thread.set_driver(driver)
        self.driver = driver_thread
        driver_thread.start()

        print('Scheduler running, Ctrl+C to quit.')


    def close(self):
        '''
        Request end of executor if needed
        '''
        if self.driver is not None:
            self.driver.stop(failover=True)
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
