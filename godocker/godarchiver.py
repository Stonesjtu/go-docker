from godocker.daemon import Daemon

import time
import redis
import json
import logging
import logging.config
import os
import yaml
import traceback
import datetime

from pymongo import MongoClient
from yapsy.PluginManager import PluginManager
from godocker.iStatusPlugin import IStatusPlugin

from godocker.storageManager import StorageManager
import godocker.utils as godutils
from godocker.notify import Notify


class GoDArchiver(Daemon):
    '''
    Archive old jobs
    '''
    SIGINT = False

    def signal_handler(self, signum, frame):
        GoDArchiver.SIGINT = True
        self.logger.warn('User request to exit')

    def status(self):
        '''
        Get process status

        :return: last timestamp of keep alive for current process, else None
        '''
        if self.status_manager is None:
            return None
        status = self.status_manager.status()
        for s in status:
            if s['name'] == self.proc_name:
                return s['timestamp']
        return None

    def reload_config(self):
        '''
        Reload config if last reload command if recent
        '''
        config_last_update = self.r.get(self.cfg['redis_prefix'] + ':config:last')
        if config_last_update is not None:
            config_last_update = float(config_last_update)
            if config_last_update > self.config_last_loaded:
                self.logger.warn('Reloading configuration')
                with open(self.config_file, 'r') as ymlfile:
                    self.cfg = yaml.load(ymlfile)
                    config_warnings = godutils.config_backward_compatibility(self.cfg)
                    if config_warnings:
                        self.logger.warn(config_warnings)
                    dt = datetime.datetime.now()
                    self.config_last_loaded = time.mktime(dt.timetuple())

    def ask_reload_config(self):
        dt = datetime.datetime.now()
        config_last_loaded = time.mktime(dt.timetuple())
        self.r.set(self.cfg['redis_prefix'] + ':config:last', config_last_loaded)

    def load_config(self, f):
        '''
        Load configuration from file path
        '''
        self.config_file = f
        dt = datetime.datetime.now()
        self.config_last_loaded = time.mktime(dt.timetuple())

        self.quota = False

        self.cfg = None
        with open(f, 'r') as ymlfile:
            self.cfg = yaml.load(ymlfile)

        config_warnings = godutils.config_backward_compatibility(self.cfg)

        self.hostname = godutils.get_hostname()
        self.proc_name = 'archiver-' + self.hostname
        if os.getenv('GOD_PROCID'):
            self.proc_name += os.getenv('GOD_PROCID')

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
        self.logger = logging.getLogger('godocker-archiver')

        if config_warnings:
            self.logger.warn(config_warnings)

        if not self.cfg['plugins_dir']:
            dirname, filename = os.path.split(os.path.abspath(__file__))
            self.cfg['plugins_dir'] = os.path.join(dirname, '..', 'plugins')

        self.store = StorageManager.get_storage(self.cfg)

        Notify.set_config(self.cfg)
        Notify.set_logger(self.logger)

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
                print("Loading status manager: " + self.status_manager.get_name())

    def update_status(self):
        if self.status_manager is None:
            return
        if self.status_manager is not None:
            res = self.status_manager.keep_alive(self.proc_name, 'archiver')
            if not res:
                self.logger.error('Archiver:UpdateStatus:Error')
        return

    def archive_task(self, job):
        self.logger.debug('Archive task %s' % (str(job['id'])))
        job_db = self.db_jobsover.find_one({'id': job['id']})
        if not job_db:
            self.logger.error('Job %s does not exists' % (str(job['id'])))
            return
        if job_db['status']['primary'] == godutils.STATUS_ARCHIVED:
            self.logger.info("%s already archived, skipping" % (str(job['id'])))
            return
        # job_dir = self.store.get_task_dir(job)
        self.store.clean(job)
        self.db_jobsover.update({'id': job['id']}, {'$set': {'status.primary': godutils.STATUS_ARCHIVED}})
        if self.quota and 'disk_size' in job['container']['meta']:
            self.db_users.update({'id': job['user']['id']},
                                {'$inc': {
                                    'usage.disk':
                                        job['container']['meta']['disk_size'] * -1}})

    def archive_tasks(self):
        arhive_task_length = self.r.llen(self.cfg['redis_prefix'] + ':jobs:archive')
        for i in range(min(arhive_task_length, self.cfg['max_job_pop'])):
            task = self.r.lpop(self.cfg['redis_prefix'] + ':jobs:archive')
            if task and task != 'None':
                self.archive_task(json.loads(task))

    def run(self, loop=True):
        '''
        Main executor loop

        '''
        self.logger.warn('Start archiver')
        self.quota = True
        if 'disk_default_quota' not in self.cfg or self.cfg['disk_default_quota'] is None:
            self.quota = False
        infinite = True
        while infinite and True and not GoDArchiver.SIGINT:
                # Archiver timer
            try:
                self.update_status()
            except Exception as e:
                self.logger.error('Archiver:' + str(self.hostname) + ':' + str(e))
                traceback_msg = traceback.format_exc()
                self.logger.error(traceback_msg)
            try:
                self.archive_tasks()
            except Exception as e:
                self.logger.error('Archiver:' + str(self.hostname) + ':' + str(e))
                traceback_msg = traceback.format_exc()
                self.logger.error(traceback_msg)
            self.reload_config()
            time.sleep(2)
            if not loop:
                infinite = False
