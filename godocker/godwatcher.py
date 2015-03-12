from godocker.daemon import Daemon
from config import Config
import time, sys
import redis
import json
import logging
import signal
import datetime
import time
import os
from pymongo import MongoClient
from bson.json_util import dumps
from bson.objectid import ObjectId

from yapsy.PluginManager import PluginManager
from godocker.iSchedulerPlugin import ISchedulerPlugin
from godocker.iExecutorPlugin import IExecutorPlugin
from godocker.iAuthPlugin import IAuthPlugin



class GoDWatcher(Daemon):
    '''
    Can be horizontally scaled
    '''

    SIGINT = False


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


    def kill_tasks(self, task_list):
        '''
        Kill tasks in list
        '''
        for task in task_list:
            (task, over) = self.executor.kill_task(task)
            # If not over, executor could not kill the task
            if over:
                for port in task['container']['ports']:
                    host = task['container']['meta']['Node']['Name']
                    self.logger.debug('Port:Back:'+host+':'+str(port))
                    self.r.rpush(self.cfg.redis_prefix+':ports:'+host, port)
                task['container']['ports'] = []
                self.db_jobs.remove({'_id': task['_id']})
                task['status']['primary'] = 'over'
                task['status']['secondary'] = 'killed'
                dt = datetime.datetime.now()
                task['status']['date_over'] = time.mktime(dt.timetuple())
                self.db_jobsover.insert(task)
                self.r.delete(self.cfg.redis_prefix+':job:'+str(task['id'])+':task')
            else:
                # Could not kill, put back in queue
                self.logger.warn('Executor:Kill:Error:'+task['id'])
                self.r.rpush(self.cfg.redis_prefix+':jobs:kill',dumps(task))

    def suspend_tasks(self, suspend_list):
        '''
        Suspend/pause tasks in list
        '''
        #TODO
        pass


    def resume_tasks(self, resume_list):
        '''
        Resume tasks in list
        '''
        #TODO
        pass



    def schedule_tasks(self, pending_list):
        '''
        Schedule tasks according to pending list

        :return: list of tasks ordered
        '''
        #for pending_job in pending_list:
        #  job  = json.loads(pending_job)
        #return None
        return self.scheduler.schedule(pending_list, None)


    def check_running_jobs(self):
        '''
        Checks if running jobs are over
        '''
        print "Check running jobs"
        nb_elt = 1
        #elts  = self.r.lrange('jobs:running', lmin, lmin+lrange)
        task_id = self.r.lpop(self.cfg.redis_prefix+':jobs:running')
        if not task_id:
            return
        elt = self.r.get(self.cfg.redis_prefix+':job:'+str(task_id)+':task')
        while True:
            #elts = self.db_jobs.find({'status.primary': 'running'}, limit=self.cfg.max_job_pop)
            try:
                if not elt:
                    return
                task = json.loads(elt)
                (task, over) = self.executor.watch_tasks(task)
                self.logger.debug("TASK:"+str(task['id'])+":"+str(over))
                if over:
                    # Free ports
                    # Put back mapping allocated ports
                    for port in task['container']['ports']:
                        host = task['container']['meta']['Node']['Name']
                        self.logger.debug('Port:Back:'+host+':'+str(port))
                        self.r.rpush(self.cfg.redis_prefix+':ports:'+host, port)
                    task['container']['ports'] = []

                    self.db_jobs.remove({'_id': ObjectId(task['_id']['$oid'])})
                    task['status']['primary'] = 'over'
                    task['status']['secondary'] = ''
                    dt = datetime.datetime.now()
                    task['status']['date_over'] = time.mktime(dt.timetuple())
                    task['_id'] = ObjectId(task['_id']['$oid'])
                    self.db_jobsover.insert(task)
                    #self.r.del('god:job:'+str(task['id'])+':container'
                    self.r.delete(self.cfg.redis_prefix+':job:'+str(task['id'])+':task')
                else:
                    self.r.rpush(self.cfg.redis_prefix+':jobs:running', task['id'])
                    self.r.set(self.cfg.redis_prefix+':job:'+str(task['id'])+':task', dumps(task))
            except KeyboardInterrupt:
                self.logger.warn('Interrupt received, exiting after cleanup')
                self.r.rpush(self.cfg.redis_prefix+':jobs:running', task['id'])
                sys.exit(0)
            if nb_elt < self.cfg.max_job_pop:
                task_id = self.r.lpop(self.cfg.redis_prefix+':jobs:running')
                if not task_id:
                    return
                elt = self.r.get(self.cfg.redis_prefix+':job:'+str(task_id)+':task')
                nb_elt += 1
            else:
                break



    def manage_tasks(self):
        '''
        Schedule and run tasks / kill tasks

        '''
        print "Get tasks to kill"
        kill_task_list = []
        kill_task_length = self.r.llen(self.cfg.redis_prefix+':jobs:kill')
        for i in range(min(kill_task_length, self.cfg.max_job_pop)):
            kill_task_list.append(json.loads(self.r.lpop(self.cfg.redis_prefix+':jobs:kill')))

        #kill_task_list = self.db_jobs.find({'status.primary': 'kill'})
        #task_list = []
        #for p in kill_task_list:
        #    task_list.append(p)
        self.kill_tasks(kill_task_list)

        print 'Get tasks to suspend'
        #suspend_task_list = []
        #suspend_task_length = self.r.llen(self.cfg.redis_prefix+':jobs:suspend')
        #for i in range(min(suspend_task_length, self.cfg.max_job_pop)):
        #    suspend_task_list.append(self.r.lpop(self.cfg.redis_prefix+':jobs:suspend'))

        suspend_task_list = self.db_jobs.find({'status.primary': 'suspend'})
        task_list = []
        for p in suspend_task_list:
            task_list.append(p)
        self.suspend_tasks(task_list)

        print 'Get tasks to resume'
        #resume_task_list = []
        #resume_task_length = self.r.llen(self.cfg.redis_prefix+':jobs:resume')
        #for i in range(min(resume_task_length, self.cfg.max_job_pop)):
        #    resume_task_list.append(self.r.lpop(self.cfg.redis_prefix+':jobs:resume'))

        resume_task_list = self.db_jobs.find({'status.primary': 'resume'})
        task_list = []
        for p in resume_task_list:
            task_list.append(p)
        self.resume_tasks(task_list)

        print 'Look for terminated jobs'
        self.check_running_jobs()

    def signal_handler(self, signum, frame):
        GoDWatcher.SIGINT = True
        self.logger.warn('User request to exit')

    def run(self, loop=True):
        '''
        Main executor loop

        '''
        infinite = True
        while infinite and True and not GoDWatcher.SIGINT:
            # Schedule timer
            self.manage_tasks()
            time.sleep(2)
            if not loop:
                infinite = False
