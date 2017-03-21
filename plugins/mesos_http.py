#!/usr/bin/env python2.7
from __future__ import print_function

import sys
import uuid
import time
import socket
import signal
import getpass
from threading import Thread

from pymesos import MesosSchedulerDriver, Scheduler, encode_data
from addict import Dict

import json
import redis

TASK_CPU = 0.1
TASK_MEM = 32
EXECUTOR_CPUS = 0.1
EXECUTOR_MEM = 32
config = Dict(
    redis_host='localhost',
    redis_port=6379,
    redis_db=0,
    redis_prefix='god',
    )


class MinimalScheduler(Scheduler):

    def __init__(self, executor):
        self.executor = executor
        self.pending_tasks = []
        self.redis_handler = redis.StrictRedis(host=config['redis_host'], port=config['redis_port'], db=config['redis_db'], decode_responses=True)

    def resourceOffers(self, driver, offers):
        filters = {'refuse_seconds': 5}
        for offer in offers:
            logging.debug('Recieving offer:' + json.dumps(offer))

            available_tasks = self.getAvailableTasks(offer)

            tasks_to_launch = self.addOfferInfo(available_tasks, offer)

            driver.launchTasks(offer.id, tasks_to_launch, filters)

    def getResource(self, res, name):
        for r in res:
            if r.name == name:
                return r.scalar.value
        return 0

    def statusUpdate(self, driver, update):
        logging.debug('Status update TID %s %s',
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
            logging.debug('loading tasks from database: ' + json.dumps(task))
            tasks.append(task)
            redis_task = self.redis_handler.lpop(self.config['redis_prefix'] + ':mesos:pending')

        return tasks

    def taskAdapter(self, redis_task):
        '''
        transform the json formatted redis task into a mesos task, without the execution info
        '''
        task = Dict()
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

def main(master):
    executor = Dict()
    executor.executor_id.value = 'MinimalExecutor'
    executor.name = executor.executor_id.value


    framework = Dict()
    framework.user = getpass.getuser()
    framework.name = "MinimalFramework"
    framework.hostname = socket.gethostname()


    driver = MesosSchedulerDriver(
        MinimalScheduler(executor),
        framework,
        master,
        use_addict=True,
    )

    def signal_handler(signal, frame):
        driver.stop()

    def run_driver_thread():
        driver.run()

    driver_thread = Thread(target=run_driver_thread, args=())
    driver_thread.start()

    print('Scheduler running, Ctrl+C to quit.')
    signal.signal(signal.SIGINT, signal_handler)

    while driver_thread.is_alive():
        time.sleep(1)


if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.DEBUG)
    if len(sys.argv) != 2:
        print("Usage: {} <mesos_master>".format(sys.argv[0]))
        sys.exit(1)
    else:
        main(sys.argv[1])
