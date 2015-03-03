from godocker.daemon import Daemon
from config import Config
import time, sys
import redis
import json
import logging
import signal
from pymongo import MongoClient

from yapsy.PluginManager import PluginManager
from godocker.iSchedulerPlugin import ISchedulerPlugin
from godocker.iExecutorPlugin import IExecutorPlugin


class GoDScheduler(Daemon):

    SIGINT = False

    def init(self):
        '''
        Database initialization
        '''
        self.db_jobs.ensure_index('user.id')
        self.db_jobs.ensure_index('status.primary')
        self.db_users.ensure_index('id')

    def load_config(self, f):
        '''
        Load configuration from file path
        '''
        cfg_file = file(f)
        self.cfg = Config(cfg_file)
        #self.r = redis.StrictRedis(host=self.cfg.redis_host, port=self.cfg.redis_port, db=self.cfg.db)
        self.mongo = MongoClient(self.cfg.mongo_url)
        self.db = self.mongo.god
        self.db_jobs = self.db.jobs
        self.db_users = self.db.users

        self.logger = logging.getLogger('godocker')
        self.logger.setLevel(logging.DEBUG)
        fh = logging.FileHandler('go.log')
        fh.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)


        # Build the manager
        simplePluginManager = PluginManager()
        # Tell it the default place(s) where to find plugins
        simplePluginManager.setPluginPlaces(["plugins"])
        simplePluginManager.setCategoriesFilter({
           "Scheduler": ISchedulerPlugin,
           "Executor": IExecutorPlugin
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
        #TODO
        pass

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

    def reschedule_tasks(self, resched_list):
        '''
        Restart/reschedule running tasks in list
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


    def _update_scheduled_task_status(self, running_tasks, rejected_tasks):
        if running_tasks:
            for r in running_tasks:
                #self.r.rpush('jobs:running', r)
                self.db_jobs.update({'_id': r['_id']}, {'$set': {'status.primary': 'running', 'container': r['container']}})
        if rejected_tasks:
            for r in rejected_tasks:
                #self.r.lpush('jobs:pending', r)
                self.db_jobs.update({'_id': r['_id']}, {'$set': {'status.secondary': 'rejected'}})

    def run_tasks(self, queued_list):
        '''
        Execute tasks on Docker scheduler in order
        '''
        (running_tasks, rejected_tasks) = self.executor.run_tasks(queued_list, self._update_scheduled_task_status)
        self._update_scheduled_task_status(running_tasks, rejected_tasks)

    def check_running_jobs(self):
        '''
        Checks if running jobs are over
        '''
        lmin = 0
        lrange = self.cfg.max_job_pop
        #elts  = self.r.lrange('jobs:running', lmin, lmin+lrange)
        elts = self.db_jobs.find({'status.primary': 'running'}, limit=self.cfg.max_job_pop, skip=lmin)
        while elts.count()>0:
            finished_tasks = self.executor.get_finished_tasks(elts)
            for f in finished_tasks:
                self.db_jobs.update({'_id': f['_id']}, {'$set': {'status.primary': 'over', 'container': f['container']}})
                #self.r.lrem('jobs:running', 0, f)
                #self.r.lpush('jobs:over', f)
            lmin += lrange
            elts = self.db_jobs.find({'status.primary': 'running'}, limit=self.cfg.max_job_pop, skip=lmin)
            #elts  = self.r.lrange('jobs:running', lmin, lmin+lrange)

    def manage_tasks(self):
        '''
        Schedule and run tasks / kill tasks

        '''
        print "Get tasks to kill"
        #kill_task_list = []
        #kill_task_length = self.r.llen('jobs:kill')
        #for i in range(min(kill_task_length, self.cfg.max_job_pop)):
        #    kill_task_list.append(self.r.lpop('jobs:kill'))

        kill_task_list = self.db_jobs.find({'status.primary': 'kill'})
        self.kill_tasks(kill_task_list)

        print "Get pending task"
        #pending_tasks = []
        #pending_tasks_length = self.r.llen('jobs:pending')
        #for i in range(min(pending_tasks_length, self.cfg.max_job_pop)):
        #    pending_tasks.append(self.r.lpop('jobs:pending'))

        pending_tasks = self.db_jobs.find({'status.primary': 'pending'})
        queued_tasks = self.schedule_tasks(pending_tasks)
        self.run_tasks(queued_tasks)

        print 'Get tasks to suspend'
        #suspend_task_list = []
        #suspend_task_length = self.r.llen('jobs:suspend')
        #for i in range(min(suspend_task_length, self.cfg.max_job_pop)):
        #    suspend_task_list.append(self.r.lpop('jobs:suspend'))

        suspend_task_list = self.db_jobs.find({'status.primary': 'suspend'})
        self.suspend_tasks(suspend_task_list)

        print 'Get tasks to resume'
        #resume_task_list = []
        #resume_task_length = self.r.llen('jobs:resume')
        #for i in range(min(resume_task_length, self.cfg.max_job_pop)):
        #    resume_task_list.append(self.r.lpop('jobs:resume'))

        resume_task_list = self.db_jobs.find({'status.primary': 'resume'})
        self.resume_tasks(resume_task_list)

        print 'Get tasks to reschedule'
        #reschedule_task_list = []
        #reschedule_task_length = self.r.llen('jobs:reschedule')
        #for i in range(min(reschedule_task_length, self.cfg.max_job_pop)):
        #    reschedule_task_list.append(self.r.lpop('jobs:rechedule'))

        reschedule_task_list = self.db_jobs.find({'status.primary': 'reschedule'})
        self.reschedule_tasks(reschedule_task_list)

        print 'Look for terminated jobs'
        self.check_running_jobs()

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


if __name__ == "__main__":
        daemon = GoDScheduler('/tmp/godsched.pid')
        daemon.load_config('go-d.ini')
        signal.signal(signal.SIGINT, daemon.signal_handler)

        if len(sys.argv) == 2:
                if 'start' == sys.argv[1]:
                        daemon.start()
                elif 'stop' == sys.argv[1]:
                        daemon.stop()
                elif 'restart' == sys.argv[1]:
                        daemon.restart()
                elif 'run' == sys.argv[1]:
                        daemon.run()
                elif 'init' == sys.argv[1]:
                        daemon.init()
                else:
                        print "Unknown command"
                        sys.exit(2)
                sys.exit(0)
        else:
                print "usage: %s start|stop|restart" % sys.argv[0]
                sys.exit(2)
