from godocker.daemon import Daemon
from config import Config
import time, sys
import redis
import json
import logging
import signal

from yapsy.PluginManager import PluginManager
from godocker.iSchedulerPlugin import ISchedulerPlugin
from godocker.iExecutorPlugin import IExecutorPlugin


class GoDScheduler(Daemon):

    SIGINT = False

    def load_config(self, f):
        '''
        Load configuration from file path
        '''
        cfg_file = file(f)
        self.cfg = Config(cfg_file)
        self.r = redis.StrictRedis(host=self.cfg.redis_host, port=self.cfg.redis_port, db=0)

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

    def run_tasks(self, queued_list):
        '''
        Execute tasks on Docker scheduler in order
        '''
        rejected_tasks = self.executor.run_tasks(queued_list)
        #TODO reinject rejected_tasks

    def manage_tasks(self):
        '''
        Schedule and run tasks / kill tasks

        '''
        print "Get tasks to kill"
        kill_task_list = []
        kill_task_length = self.r.llen('jobs:kill')
        for i in range(min(kill_task_length, self.cfg.max_job_pop)):
            kill_task_list.append(self.r.lpop('jobs:kill'))
        self.kill_tasks(kill_task_list)

        print "Get pending task"
        pending_tasks = []
        pending_tasks_length = self.r.llen('jobs:pending')
        for i in range(min(pending_tasks_length, self.cfg.max_job_pop)):
            pending_tasks.append(self.r.lpop('jobs:pending'))


        queued_tasks = self.schedule_tasks(pending_tasks)
        self.run_tasks(queued_tasks)

        print 'Get tasks to suspend'
        #TODO
        print 'Get tasks to resume'
        #TODO
        print 'Get tasks to reschedule'
        #TODO


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
                else:
                        print "Unknown command"
                        sys.exit(2)
                sys.exit(0)
        else:
                print "usage: %s start|stop|restart" % sys.argv[0]
                sys.exit(2)
