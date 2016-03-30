import time, sys
import redis
import json
import logging
import logging.config
import signal
import os
import datetime
import time
import socket
import random
import string
import urllib3
import traceback
from copy import deepcopy
import yaml



from pymongo import MongoClient
from pymongo import DESCENDING as pyDESCENDING
from bson.json_util import dumps
from yapsy.PluginManager import PluginManager

from godocker.iSchedulerPlugin import ISchedulerPlugin
from godocker.iExecutorPlugin import IExecutorPlugin
from godocker.iAuthPlugin import IAuthPlugin
from godocker.iWatcherPlugin import IWatcherPlugin
from godocker.iStatusPlugin import IStatusPlugin



class GoDStatus():

    def load_config(self, f):
        '''
        Load configuration from file path
        '''
        self.cfg= None
        with open(f, 'r') as ymlfile:
            self.cfg = yaml.load(ymlfile)


        self.hostname = socket.gethostbyaddr(socket.gethostname())[0]


        self.r = redis.StrictRedis(host=self.cfg['redis_host'], port=self.cfg['redis_port'], db=self.cfg['redis_db'], decode_responses=True)
        self.mongo = MongoClient(self.cfg['mongo_url'])
        self.db = self.mongo[self.cfg['mongo_db']]
        self.db_jobs = self.db.jobs
        self.db_jobsover = self.db.jobsover
        self.db_users = self.db.users
        self.db_projects = self.db.projects

        if self.cfg['log_config'] is not None:
            for handler in list(self.cfg['log_config']['handlers'].keys()):
                self.cfg['log_config']['handlers'][handler] = dict(self.cfg['log_config']['handlers'][handler])
            logging.config.dictConfig(self.cfg['log_config'])
        self.logger = logging.getLogger('godocker-scheduler')

        if not self.cfg['plugins_dir']:
            dirname, filename = os.path.split(os.path.abspath(__file__))
            self.cfg['plugins_dir'] = os.path.join(dirname, '..', 'plugins')


        # Build the manager
        simplePluginManager = PluginManager()
        # Tell it the default place(s) where to find plugins
        simplePluginManager.setPluginPlaces([self.cfg['plugins_dir']])
        simplePluginManager.setCategoriesFilter({
           "Status": IStatusPlugin
         })
        # Load all plugins
        simplePluginManager.collectPlugins()

        # Activate plugins
        self.status_manager = None
        for pluginInfo in simplePluginManager.getPluginsOfCategory("Status"):
           if 'status_policy' not in self.cfg or not self.cfg['status_policy']:
               print("No status manager in configuration")
               break
           if pluginInfo.plugin_object.get_name() == self.cfg['status_policy']:
             self.status_manager = pluginInfo.plugin_object
             self.status_manager.set_logger(self.logger)
             self.status_manager.set_redis_handler(self.r)
             self.status_manager.set_jobs_handler(self.db_jobs)
             self.status_manager.set_users_handler(self.db_users)
             self.status_manager.set_projects_handler(self.db_projects)
             self.status_manager.set_config(self.cfg)
             print("Loading status manager: "+self.status_manager.get_name())


if __name__ == "__main__":
        status = GoDStatus()
        config_file = 'go-d.ini'
        if 'GOD_CONFIG' in os.environ:
            config_file = os.environ['GOD_CONFIG']
        status.load_config(config_file)
        if len(sys.argv) == 2:
                if 'status' == sys.argv[1]:
                        status = status.status_manager.status()
                        global_status = True
                        scheduler_status = 0
                        watcher_status = 0
                        web_status = 0
                        for proc_state in status:
                            print "Status:\n"
                            print "\t - "+proc_state['name']+'[' + str(proc_state['type']) + ']: '+str(proc_state['status'])+"\n"
                            if not proc_state['status']:
                                global_status = False
                            if proc_state['type'] == 'scheduler' and proc_state['status']:
                                scheduler_status += 1
                            if proc_state['type'] == 'watcher' and proc_state['status']:
                                watcher_status += 1
                            if proc_state['type'] == 'web' and proc_state['status']:
                                web_status += 1
                        if scheduler_status == 0:
                            print "Error: no scheduler running"
                            global_status = False
                        if watcher_status == 0:
                            print "Error: no watcher running"
                            global_status = False
                        if web_status == 0:
                            print "Warning: no web server running or monitored"
                        if global_status:
                            sys.exit(0)
                        else:
                            sys.exit(1)
                else:
                        print("Unknown command")
                        sys.exit(2)
                sys.exit(0)
        else:
                print("usage: %s status" % sys.argv[0])
                sys.exit(2)
