from godocker.daemon import Daemon

import time, sys
import redis
import json
import logging
import signal
import os
import datetime
import time
from pymongo import MongoClient
from bson.json_util import dumps
from config import Config
from yapsy.PluginManager import PluginManager

from godocker.iSchedulerPlugin import ISchedulerPlugin
from godocker.iExecutorPlugin import IExecutorPlugin
from godocker.iAuthPlugin import IAuthPlugin
from godocker.pairtreeStorage import PairtreeStorage


class GoDScheduler(Daemon):
    '''
    One instance only
    '''

    SIGINT = False

    def init(self):
        '''
        Database initialization
        '''
        self.db_jobs.ensure_index('id')
        self.db_jobs.ensure_index('user.id')
        self.db_jobs.ensure_index('status.primary')
        self.db_jobsover.ensure_index('status.primary')
        self.db_users.ensure_index('id')

    def load_config(self, f):
        '''
        Load configuration from file path
        '''
        cfg_file = file(f)
        self.cfg = Config(cfg_file)
        self.r = redis.StrictRedis(host=self.cfg.redis_host, port=self.cfg.redis_port, db=self.cfg.redis_db)
        self.mongo = MongoClient(self.cfg.mongo_url)
        self.db = self.mongo[self.cfg.mongo_db]
        self.db_jobs = self.db.jobs
        self.db_jobsover = self.db.jobsover
        self.db_users = self.db.users

        self.logger = logging.getLogger('godocker')
        self.logger.setLevel(logging.DEBUG)
        fh = logging.FileHandler('go.log')
        fh.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)

        if not self.cfg.plugins_dir:
            dirname, filename = os.path.split(os.path.abspath(__file__))
            self.cfg.plugins_dir = os.path.join(dirname, '..', 'plugins')

        self.store = PairtreeStorage(self.cfg)

        # Build the manager
        simplePluginManager = PluginManager()
        # Tell it the default place(s) where to find plugins
        simplePluginManager.setPluginPlaces([self.cfg.plugins_dir])
        simplePluginManager.setCategoriesFilter({
           "Scheduler": ISchedulerPlugin,
           "Executor": IExecutorPlugin,
           "Auth": IAuthPlugin
         })
        # Load all plugins
        simplePluginManager.collectPlugins()

        # Activate plugins
        self.scheduler = None
        for pluginInfo in simplePluginManager.getPluginsOfCategory("Scheduler"):
           #simplePluginManager.activatePluginByName(pluginInfo.name)
           if pluginInfo.plugin_object.get_name() == self.cfg.scheduler_policy:
             self.scheduler = pluginInfo.plugin_object
             self.scheduler.set_config(self.cfg)
             self.scheduler.set_logger(self.logger)
             print "Loading scheduler: "+self.scheduler.get_name()
        self.executor = None
        for pluginInfo in simplePluginManager.getPluginsOfCategory("Executor"):
           #simplePluginManager.activatePluginByName(pluginInfo.name)
           if pluginInfo.plugin_object.get_name() == self.cfg.executor:
             self.executor = pluginInfo.plugin_object
             self.executor.set_config(self.cfg)
             self.executor.set_logger(self.logger)
             print "Loading executor: "+self.executor.get_name()


    def add_task(self, task):
        '''
        Add a new task, if status not set, set it to pending

        Automatically atribute an id to the task

        :param task: Task to insert
        :type task: dict
        :return: task id
        '''
        task_id = self.r.incr(self.cfg.redis_prefix+':jobs')
        self.r.incr(self.cfg.redis_prefix+':jobs:queued')
        task['id'] = task_id
        if not task['status']['primary']:
            task['status']['primary'] = 'pending'
        self.db_jobs.insert(task)
        return task_id

    def schedule_tasks(self, pending_list):
        '''
        Schedule tasks according to pending list

        :return: list of tasks ordered
        '''
        #for pending_job in pending_list:
        #  job  = json.loads(pending_job)
        #return None
        return self.scheduler.schedule(pending_list, None)


    def _update_scheduled_task_status(self, running_tasks, rejected_tasks):
        if running_tasks:
            for r in running_tasks:
                self.r.rpush(self.cfg.redis_prefix+':jobs:running', r['id'])
                #self.r.set('god:job:'+str(r['id'])+':container', r['container']['id'])
                self.r.set(self.cfg.redis_prefix+':job:'+str(r['id'])+':task', dumps(r))
                self.r.decr(self.cfg.redis_prefix+':jobs:queued')
                dt = datetime.datetime.now()
                self.db_jobs.update({'_id': r['_id']},
                                    {'$set': {
                                        'status.primary': 'running',
                                        'status.secondary': None,
                                        'status.date_running': time.mktime(dt.timetuple()),
                                        'container': r['container']}})
        if rejected_tasks:
            for r in rejected_tasks:
                # Put back mapping allocated ports
                if container['meta'] and 'Node' in container['meta'] and 'Name' in container['meta']['Node']:
                    host = r['container']['meta']['Node']['Name']
                    for port in r['container']['ports']:
                        self.r.rpush(self.cfg.redis_prefix+':ports:'+host, port)
                self.db_jobs.update({'_id': r['_id']}, {'$set': {'status.secondary': 'rejected by scheduler', 'container.ports': []}})


    def _create_command(self, task):
        '''
        Write command script on disk
        '''
        script_file = self.store.add_file(task, 'cmd.sh', task['command']['cmd'])
        os.chmod(script_file, 0755)
        task['command']['script'] = os.path.join('/mnt/go-docker',os.path.basename(script_file))
            # Add task directory
        task_dir = self.store.get_task_dir(task)
        task['container']['volumes'].append({
            'name': 'go-docker',
            'acl': 'rw',
            'path': task_dir,
            'mount': '/mnt/go-docker'
        })

    def run_tasks(self, queued_list):
        '''
        Execute tasks on Docker scheduler in order
        '''
        for task in queued_list:
            # Create run script
            self._create_command(task)
            self.logger.debug("Execute:Task:Run:Try")
            self.logger.debug(str(task))

        (running_tasks, rejected_tasks) = self.executor.run_tasks(queued_list, self._update_scheduled_task_status, self.get_mapping_port)
        self._update_scheduled_task_status(running_tasks, rejected_tasks)

    def reschedule_tasks(self, resched_list):
        '''
        Restart/reschedule running tasks in list
        '''
        #TODO
        pass

    def get_mapping_port(self, host, task):
        '''
        Get a port mapping for interactive tasks

        :param host: hostname of the container
        :type host: str
        :param task: task
        :type task: int
        :return: available port
        '''
        if not self.r.exists(self.cfg.redis_prefix+':ports:'+host):
            for i in range(self.cfg.port_start):
                self.r.rpush(self.cfg.redis_prefix+':ports:'+host, self.cfg.port_start + i)
        port = self.r.lpop(self.cfg.redis_prefix+':ports:'+host)
        self.logger.debug('Port:Give:'+task['container']['meta']['Node']['Name']+':'+str(port))
        task['container']['ports'].append(port)
        return port


    def manage_tasks(self):
        '''
        Schedule and run tasks / kill tasks

        '''

        print "Get pending task"
        #pending_tasks = []
        #pending_tasks_length = self.r.llen('jobs:pending')
        #for i in range(min(pending_tasks_length, self.cfg.max_job_pop)):
        #    pending_tasks.append(self.r.lpop('jobs:pending'))

        pending_tasks = self.db_jobs.find({'status.primary': 'pending'})
        task_list = []
        for p in pending_tasks:
            task_list.append(p)
        queued_tasks = self.schedule_tasks(task_list)
        self.run_tasks(queued_tasks)

        print 'Get tasks to reschedule'
        #reschedule_task_list = []
        #reschedule_task_length = self.r.llen('jobs:reschedule')
        #for i in range(min(reschedule_task_length, self.cfg.max_job_pop)):
        #    reschedule_task_list.append(self.r.lpop('jobs:rechedule'))

        reschedule_task_list = self.db_jobs.find({'status.primary': 'reschedule'})
        task_list = []
        for p in pending_tasks:
            task_list.append(p)
        self.reschedule_tasks(task_list)

    def signal_handler(self, signum, frame):
        GoDScheduler.SIGINT = True
        self.logger.warn('User request to exit')

    def run(self):
        '''
        Main executor loop

        '''

        while True and not GoDScheduler.SIGINT:
            # Schedule timer
            self.manage_tasks()
            time.sleep(2)
