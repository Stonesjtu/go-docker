from godocker.daemon import Daemon
import time, sys
import redis
import json
import logging
import logging.config
import signal
import datetime
import time
import os
import socket
import traceback
import yaml

import graypy
import logstash

from pymongo import MongoClient
from bson.json_util import dumps
from bson.objectid import ObjectId
from influxdb import client as influxdb
from logging.handlers import RotatingFileHandler

from yapsy.PluginManager import PluginManager
#from godocker.pairtreeStorage import PairtreeStorage
from godocker.storageManager import StorageManager
from godocker.iSchedulerPlugin import ISchedulerPlugin
from godocker.iExecutorPlugin import IExecutorPlugin
from godocker.iAuthPlugin import IAuthPlugin
from godocker.iWatcherPlugin import IWatcherPlugin
from godocker.iStatusPlugin import IStatusPlugin
from godocker.utils import is_array_task, is_array_child_task
import godocker.utils as godutils
from godocker.notify import Notify



class GoDWatcher(Daemon):
    '''
    Can be horizontally scaled
    '''

    SIGINT = False

    def reload_config(self):
        '''
        Reload config if last reload command if recent
        '''
        config_last_update = self.r.get(self.cfg['redis_prefix']+':config:last')
        if config_last_update is not None:
            config_last_update = float(config_last_update)
            if config_last_update > self.config_last_loaded:
                self.logger.warn('Reloading configuration')
                with open(self.config_file, 'r') as ymlfile:
                    self.cfg = yaml.load(ymlfile)
                    dt = datetime.datetime.now()
                    self.config_last_loaded = time.mktime(dt.timetuple())

    def ask_reload_config(self):
        dt = datetime.datetime.now()
        config_last_loaded = time.mktime(dt.timetuple())
        self.r.set(self.cfg['redis_prefix']+':config:last', config_last_loaded)

    def load_config(self, f):
        '''
        Load configuration from file path
        '''
        self.config_file = f
        dt = datetime.datetime.now()
        self.config_last_loaded = time.mktime(dt.timetuple())


        self.cfg= None
        with open(f, 'r') as ymlfile:
            self.cfg = yaml.load(ymlfile)

        self.hostname = socket.gethostbyaddr(socket.gethostname())[0]
        self.proc_name = 'watcher-'+self.hostname
        if os.getenv('GOD_PROCID'):
            self.proc_name += os.getenv('GOD_PROCID')

        self.r = redis.StrictRedis(host=self.cfg['redis_host'], port=self.cfg['redis_port'], db=self.cfg['redis_db'], decode_responses=True)
        self.mongo = MongoClient(self.cfg['mongo_url'])
        self.db = self.mongo[self.cfg['mongo_db']]
        self.db_jobs = self.db.jobs
        self.db_jobsover = self.db.jobsover
        self.db_users = self.db.users
        self.db_projects = self.db.projects

        self.db_influx = None
        if self.cfg['influxdb_host']:
            host = self.cfg['influxdb_host']
            port = self.cfg['influxdb_port']
            username = self.cfg['influxdb_user']
            password = self.cfg['influxdb_password']
            database = self.cfg['influxdb_db']
            self.db_influx = influxdb.InfluxDBClient(host, port, username, password, database)

        if self.cfg['log_config'] is not None:
            for handler in list(self.cfg['log_config']['handlers'].keys()):
                self.cfg['log_config']['handlers'][handler] = dict(self.cfg['log_config']['handlers'][handler])
            logging.config.dictConfig(self.cfg['log_config'])
        self.logger = logging.getLogger('godocker-watcher')


        if not self.cfg['plugins_dir']:
            dirname, filename = os.path.split(os.path.abspath(__file__))
            self.cfg['plugins_dir'] = os.path.join(dirname, '..', 'plugins')

        #self.store = PairtreeStorage(self.cfg)
        self.store = StorageManager.get_storage(self.cfg)

        Notify.set_config(self.cfg)
        Notify.set_logger(self.logger)

        # Build the manager
        simplePluginManager = PluginManager()
        # Tell it the default place(s) where to find plugins
        simplePluginManager.setPluginPlaces([self.cfg['plugins_dir']])
        simplePluginManager.setCategoriesFilter({
           "Scheduler": ISchedulerPlugin,
           "Executor": IExecutorPlugin,
           "Auth": IAuthPlugin,
           "Watcher": IWatcherPlugin,
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

        self.scheduler = None
        for pluginInfo in simplePluginManager.getPluginsOfCategory("Scheduler"):
           #simplePluginManager.activatePluginByName(pluginInfo.name)
           if pluginInfo.plugin_object.get_name() == self.cfg['scheduler_policy']:
             self.scheduler = pluginInfo.plugin_object
             self.scheduler.set_logger(self.logger)
             self.scheduler.set_redis_handler(self.r)
             self.scheduler.set_jobs_handler(self.db_jobs)
             self.scheduler.set_users_handler(self.db_users)
             self.scheduler.set_projects_handler(self.db_projects)
             self.scheduler.set_config(self.cfg)
             print("Loading scheduler: "+self.scheduler.get_name())
        self.executor = None
        for pluginInfo in simplePluginManager.getPluginsOfCategory("Executor"):
           #simplePluginManager.activatePluginByName(pluginInfo.name)
           if pluginInfo.plugin_object.get_name() == self.cfg['executor']:
             self.executor = pluginInfo.plugin_object
             self.executor.set_logger(self.logger)
             self.executor.set_redis_handler(self.r)
             self.executor.set_jobs_handler(self.db_jobs)
             self.executor.set_users_handler(self.db_users)
             self.executor.set_projects_handler(self.db_projects)
             self.executor.set_config(self.cfg)
             print("Loading executor: "+self.executor.get_name())

        self.watchers = []
        if 'watchers' in self.cfg and self.cfg['watchers'] is not None:
            watchers = self.cfg['watchers']
        else:
            watchers = []
        for pluginInfo in simplePluginManager.getPluginsOfCategory("Watcher"):
           #simplePluginManager.activatePluginByName(pluginInfo.name)
           if pluginInfo.plugin_object.get_name() in watchers:
             watcher = pluginInfo.plugin_object
             watcher.set_logger(self.logger)
             watcher.set_config(self.cfg)
             watcher.set_redis_handler(self.r)
             watcher.set_jobs_handler(self.db_jobs)
             watcher.set_users_handler(self.db_users)
             watcher.set_projects_handler(self.db_projects)
             self.watchers.append(watcher)
             print("Add watcher: "+watcher.get_name())

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

    def _set_task_exitcode(self, task, exitcode):
        '''
        Sets exit code in input task
        '''
        if task['container']['meta'] is None:
            task['container']['meta'] = {}
        if 'State' in task['container']['meta']:
            task['container']['meta']['State']['ExitCode'] = 137
        else:
            task['container']['meta'] = {
                'State': {'ExitCode': 137}
            }

    def kill_tasks(self, task_list):
        '''
        Kill tasks in list
        '''
        for task in task_list:
            if self.stop_daemon:
                self.executor.close()
                return
            if task['status']['primary'] == godutils.STATUS_OVER:
                continue
            if task['status']['primary'] != godutils.STATUS_PENDING:
                if is_array_task(task):
                    # If an array parent, only checks if some child tasks are still running
                    #nb_subtasks_running = self.r.get(self.cfg['redis_prefix']+':job:'+str(task['id'])+':subtaskrunning')
                    nb_subtasks_running = self.r.get(self.cfg['redis_prefix']+':job:'+str(task['id'])+':subtask')
                    if nb_subtasks_running and int(nb_subtasks_running) > 0:
                        over = False
                        # kill sub tasks
                        for subtask_id in task['requirements']['array']['tasks']:
                            task_to_kill = self.r.get(self.cfg['redis_prefix']+':job:'+str(subtask_id))
                            self.r.rpush(self.cfg['redis_prefix']+':jobs:kill', task_to_kill)
                    else:
                        over = True
                else:
                    (task, over) = self.executor.kill_task(task)

                self._set_task_exitcode(task, 137)
            else:
                if is_array_task(task):
                    # If an array parent, only checks if some child tasks are still running
                    nb_subtasks_running = self.r.get(self.cfg['redis_prefix']+':job:'+str(task['id'])+':subtask')
                    if nb_subtasks_running and int(nb_subtasks_running) > 0:
                        over = False
                        # kill sub tasks
                        for subtask_id in task['requirements']['array']['tasks']:
                            task_to_kill = self.r.get(self.cfg['redis_prefix']+':job:'+str(subtask_id))
                            if task_to_kill is None:
                                task_to_kill = dumps(self.db_jobs.find_one({'id': subtask_id}))
                                self.r.set(self.cfg['redis_prefix']+':job:'+str(subtask_id)+':task', task_to_kill)
                            self.r.rpush(self.cfg['redis_prefix']+':jobs:kill', task_to_kill)
                            self.r.decr(self.cfg['redis_prefix'] + ':user:' + str(task['user']['id'])+ ':rate')
                    else:
                        over = True
                        self._set_task_exitcode(task, 137)
                        self.r.decr(self.cfg['redis_prefix']+':jobs:queued')
                        self.r.decr(self.cfg['redis_prefix'] + ':user:' + str(task['user']['id'])+ ':rate')
                else:
                    over = True
                    self._set_task_exitcode(task, 137)
                    self.r.decr(self.cfg['redis_prefix']+':jobs:queued')
                    self.r.decr(self.cfg['redis_prefix'] + ':user:' + str(task['user']['id'])+ ':rate')
            # If not over, executor could not kill the task
            if 'tentative' in task['status'] and task['status']['kill_tentative'] > 10:
                over = True
                task['status']['reason'] = 'Failed to kill task nicely, kill forced'
                self.logger.error('Kill:Force:'+str(task['id']))

            if over:
                self.logger.debug('Executor:Kill:Success:'+str(task['id']))

                original_task = self.db_jobs.find_one({'id': task['id']})
                if original_task is None:
                    continue
                if 'resources.port' not in self.executor.features():
                    self.executor.release_port(original_task)
                    '''
                    for port in original_task['container']['ports']:
                        host = original_task['container']['meta']['Node']['Name']
                        self.logger.debug('Port:Back:'+host+':'+str(port))
                        self.r.rpush(self.cfg['redis_prefix']+':ports:'+host, port)
                    '''

                task['container']['ports'] = []
                task['container']['port_mapping'] = []
                # If private registry was used, revert to original name without server address
                task['container']['image'] = original_task['container']['image']

                # Check for reschedule request
                if original_task and original_task['status']['secondary'] == godutils.STATUS_SECONDARY_RESCHEDULE_REQUESTED:
                    self.r.delete(self.cfg['redis_prefix']+':job:'+str(task['id'])+':task')
                    self.r.incr(self.cfg['redis_prefix']+':jobs:queued')
                    self.r.incr(self.cfg['redis_prefix'] + ':user:' + str(task['user']['id'])+ ':rate')
                    reason = ''
                    if 'reason' in task['status']:
                        reason = task['status']['reason']
                    self.db_jobs.update({'id': task['id']}, {'$set': {
                        'status.primary' : godutils.STATUS_PENDING,
                        'status.secondary': godutils.STATUS_SECONDARY_RESCHEDULED,
                        'status.reason': reason

                    }})
                    continue
                remove_result = self.db_jobs.remove({'id': task['id']})
                if remove_result['n'] == 0:
                    # Not present anymore, may have been removed already
                    # Remove from jobs over to replace it
                    self.db_jobsover.remove({'id': task['id']})
                task['status']['primary'] = godutils.STATUS_OVER
                task['status']['secondary'] = godutils.STATUS_SECONDARY_KILLED
                try:
                    task['status']['exitcode'] = task['container']['meta']['State']['ExitCode']
                except Exception:
                    self.logger.warn('No exit code: '+str(task['id']))
                dt = datetime.datetime.now()
                task['status']['date_over'] = time.mktime(dt.timetuple())

                task['status']['duration'] = 0
                if 'date_running' in task['status'] and task['status']['date_running'] is not None:
                    task['status']['duration'] = task['status']['date_over'] - task['status']['date_running']

                del task['_id']
                task = self.terminate_task(task)
                self.db_jobsover.insert(task)
                self.r.delete(self.cfg['redis_prefix']+':job:'+str(task['id'])+':task')
                if is_array_task(task):
                    self.r.delete(self.cfg['redis_prefix']+':job:'+str(task['id'])+':subtaskrunning')
                    self.r.delete(self.cfg['redis_prefix']+':job:'+str(task['id'])+':subtask')
                if is_array_child_task(task):
                    self.r.decr(self.cfg['redis_prefix']+':job:'+str(task['parent_task_id'])+':subtaskrunning')
                    self.r.decr(self.cfg['redis_prefix']+':job:'+str(task['parent_task_id'])+':subtask')
                    self.db_jobs.update({'id': task['parent_task_id']}, {'$inc': {'requirements.array.nb_tasks_over': 1}})

                if not is_array_task(task):
                    self.update_user_usage(task)

                if not is_array_child_task(task):
                    self.notify_msg(task)
                    Notify.notify_email(task)
            else:
                if 'kill_tentative' not in task['status']:
                    task['status']['kill_tentative'] = 0
                task['status']['kill_tentative'] += 1
                # Could not kill, put back in queue
                if over is not None:
                    # async case like mesos, kill is not immediate
                    self.logger.warn('Executor:Kill:Error:'+str(task['id']))
                if task['status']['kill_tentative'] > 10:
                    # Failed to kill after 10 tentatives
                    # Remove kill status
                    self.logger.error('Executor:Kill:Error:'+str(task['id']))
                    self.db_jobs.update({'id': task['id']},
                                        {'$set': {
                                            'status.secondary': godutils.STATUS_SECONDARY_UNKNOWN,
                                            'status.reason': 'Failure to kill job'

                                        }})
                else:
                    self.r.rpush(self.cfg['redis_prefix']+':jobs:kill',dumps(task))

    def suspend_tasks(self, suspend_list):
        '''
        Suspend/pause tasks in list
        '''
        if self.stop_daemon:
            self.executor.close()
            return

        for task in suspend_list:
            if self.stop_daemon:
                self.executor.close()
                return

            status = None
            over = False

            if task['status']['primary'] == godutils.STATUS_PENDING or task['status']['primary'] == godutils.STATUS_OVER:
                status = godutils.STATUS_SECONDARY_SUSPEND_REJECTED
                over = True
            elif is_array_task(task):
                # suspend not supported for array_tasks
                status = godutils.STATUS_SECONDARY_SUSPEND_REJECTED
                over = True
            else:
                (task, over) = self.executor.suspend_task(task)
                status = godutils.STATUS_SECONDARY_SUSPENDED
                Notify.notify_email(task)
            if over:
                task['status']['secondary'] = status
                self.r.set(self.cfg['redis_prefix']+':job:'+str(task['id'])+':task', dumps(task))
                if task['status']['primary'] != godutils.STATUS_OVER:
                    self.db_jobs.update({'id' : task['id']},{'$set': {'status.secondary': status}})
            else:
                # Could not kill, put back in queue
                self.logger.warn('Executor:Suspend:Error:'+str(task['id']))
                self.r.rpush(self.cfg['redis_prefix']+':jobs:suspend',dumps(task))



    def resume_tasks(self, resume_list):
        '''
        Resume tasks in list
        '''
        if self.stop_daemon:
            self.executor.close()
            return
        for task in resume_list:
            if self.stop_daemon:
                self.executor.close()
                return
            status = None
            over = False

            if task['status']['primary'] == godutils.STATUS_PENDING or task['status']['primary'] == godutils.STATUS_OVER or task['status']['secondary'] != 'resume requested':
                status = godutils.STATUS_SECONDARY_RESUME_REJECTED
                over = True
            else:
                (task, over) = self.executor.resume_task(task)
                status = godutils.STATUS_SECONDARY_RESUMED
                Notify.notify_email(task)
            if over:
                task['status']['secondary'] = status
                self.r.set(self.cfg['redis_prefix']+':job:'+str(task['id'])+':task', dumps(task))
                if task['status']['primary'] != godutils.STATUS_OVER:
                    self.db_jobs.update({'id' : task['id']},{'$set': {'status.secondary': status}})
            else:
                # Could not resumed, put back in queue
                self.logger.warn('Executor:Resume:Error:'+str(task['id']))
                self.r.rpush(self.cfg['redis_prefix']+':jobs:resume',dumps(task))



    def schedule_tasks(self, pending_list):
        '''
        Schedule tasks according to pending list

        :return: list of tasks ordered
        '''
        if self.stop_daemon:
            self.executor.close()
            return
        #for pending_job in pending_list:
        #  job  = json.loads(pending_job)
        #return None
        return self.scheduler.schedule(pending_list, None)

    def _add_to_stats(self, task):
        '''
        Add task to stats db
        '''
        if self.db_influx is None:
            return
        task_duration = 0
        if task['status']['date_running'] and task['status']['date_over']:
            task_duration = task['status']['date_over'] - task['status']['date_running']
        task_waiting = 0
        if task['status']['date_running']:
            task_waiting = task['status']['date_running'] - task['date']
        #dt = datetime.datetime.now()
        #current_timestamp = time.mktime(dt.timetuple())
        data = [{
            'points': [[
                task['user']['id'],
                task['requirements']['cpu'],
                task['requirements']['ram'],
                task_duration,
                task_waiting,
                task['container']['image']
            ]],
            'name':'god_task_usage',
            'columns': ["user", "cpu", "ram", "durationtime", "waitingtime","image"]
        }]
        try:
            self.db_influx.write_points(data)
        except Exception as e:
            # Do not fail on stat writing
            self.logger.error('Stat:Error:'+str(e))


    def terminate_task(self, task):
        '''
        Checks and updates on finished task (ok or killed)

        :param task: current task
        :type task: Task
        :return: updated task
        '''
        if 'disk_default_quota' in self.cfg and self.cfg['disk_default_quota'] is not None:
            folder_size = 0
            if not is_array_task(task):
                task_dir = self.store.get_task_dir(task)
                folder_size = godutils.get_folder_size(task_dir)
            if 'meta' not in task['container'] or task['container']['meta'] is None:
                task['container']['meta'] = {}
            task['container']['meta']['disk_size'] = folder_size
            self.db_users.update({'id': task['user']['id']}, {'$inc': {'usage.disk': folder_size}})
        if 'guest' in task['user'] and task['user']['guest']:
            # Calculate pseudo home dir size
            for volume in task['container']['volumes']:
                if volume['name'] == 'home':
                    print("Calculate for "+volume['path'])
                    folder_size = godutils.get_folder_size(volume['path'])
                    self.db_users.update({'id': task['user']['id']}, {'$set': {'usage.guest_home': folder_size}})
                    break
        # Increment image usage
        self.r.hincrby(self.cfg['redis_prefix']+':images', task['container']['image'], 1)
                    
        for watcher in self.watchers:
            watcher.done(task)
        return task

    def update_user_usage(self, task):
        '''
        Add to user usage task consumption (cpu,ram,time)
        '''
        task_duration = 0
        if 'date_running' in task['status'] and task['status']['date_running'] and task['status']['date_over']:
            task_duration = task['status']['date_over'] - task['status']['date_running']
        '''
        task_user = self.db_users.find_one({'id': task['user']['id']})
        last_update = datetime.datetime.now()
        if not 'usage' in task_user:
            task_user['usage'] = {}
        if 'last' not in task_user['usage'] or not task_user['usage']['last']:
            last_delta = 0
        else:
            last_delta = (last_update - task_user['usage']['last']).days


        if last_delta > self.cfg['user_reset_usage_duration']:
            self.db_users.update({'id': task['user']['id']},{
                '$set': {
                    'usage.cpu': task['requirements']['cpu'],
                    'usage.ram': task['requirements']['ram'],
                    'usage.time': task_duration
                },
                '$set': {
                    'last': last_update
                }

            })
        else:
            self.db_users.update({'id': task['user']['id']},{
                '$inc': {
                    'usage.cpu': task['requirements']['cpu'],
                    'usage.ram': task['requirements']['ram'],
                    'usage.time': task_duration
                },
                '$set': {
                    'last': last_update
                }

            })

        dt = datetime.datetime.now()
        timestamp = time.mktime(dt.timetuple())
        group_last = self.r.get(self.cfg['redis_prefix']+':group:'+str(task['user']['project'])+':last')
        if group_last is None:
            group_last = timestamp
        else:
            group_last = float(group_last)
        last_delta = (timestamp - group_last) / (3600 * 24) # In days
        if last_delta > self.cfg['user_reset_usage_duration']:
            self.r.set(self.cfg['redis_prefix']+':group:'+str(task['user']['project'])+':cpu', task['requirements']['cpu'])
            self.r.set(self.cfg['redis_prefix']+':group:'+str(task['user']['project'])+':ram', task['requirements']['ram'])
            self.r.set(self.cfg['redis_prefix']+':group:'+str(task['user']['project'])+':time', task_duration)
        else:
            self.r.incr(self.cfg['redis_prefix']+':group:'+str(task['user']['project'])+':cpu', task['requirements']['cpu'])
            self.r.incr(self.cfg['redis_prefix']+':group:'+str(task['user']['project'])+':ram', task['requirements']['ram'])
            self.r.incrbyfloat(self.cfg['redis_prefix']+':group:'+str(task['user']['project'])+':time', task_duration)
        group_last = self.r.set(self.cfg['redis_prefix']+':group:'+str(task['user']['project'])+':last', timestamp)
        '''
        # Set an RDD like over a time window of self.cfg['user_reset_usage_duration'] days
        dt = datetime.datetime.now()
        date_key = str(dt.year)+'_'+str(dt.month)+'_'+str(dt.day)
        set_expire = True
        if self.r.exists(self.cfg['redis_prefix']+':user:'+str(task['user']['id'])+':cpu:'+date_key):
            set_expire = False
        self.r.incr(self.cfg['redis_prefix']+':user:'+str(task['user']['id'])+':cpu:'+date_key, task['requirements']['cpu'])
        self.r.incr(self.cfg['redis_prefix']+':user:'+str(task['user']['id'])+':ram:'+date_key, task['requirements']['ram'])
        self.r.incrbyfloat(self.cfg['redis_prefix']+':user:'+str(task['user']['id'])+':time:'+date_key, task_duration)
        if set_expire:
            expiration_time = self.cfg['user_reset_usage_duration'] * 24 * 3600
            self.r.expire(self.cfg['redis_prefix']+':user:'+str(task['user']['id'])+':cpu:'+date_key, expiration_time)
            self.r.expire(self.cfg['redis_prefix']+':user:'+str(task['user']['id'])+':ram:'+date_key, expiration_time)
            self.r.expire(self.cfg['redis_prefix']+':user:'+str(task['user']['id'])+':time:'+date_key, expiration_time)

        set_expire = True
        if self.r.exists(self.cfg['redis_prefix']+':group:'+str(task['user']['project'])+':cpu:'+date_key):
            set_expire = False
        self.r.incr(self.cfg['redis_prefix']+':group:'+str(task['user']['project'])+':cpu:'+date_key, task['requirements']['cpu'])
        self.r.incr(self.cfg['redis_prefix']+':group:'+str(task['user']['project'])+':ram:'+date_key, task['requirements']['ram'])
        self.r.incrbyfloat(self.cfg['redis_prefix']+':group:'+str(task['user']['project'])+':time:'+date_key, task_duration)
        if set_expire:
            expiration_time = self.cfg['user_reset_usage_duration'] * 24 * 3600
            self.r.expire(self.cfg['redis_prefix']+':group:'+str(task['user']['project'])+':cpu:'+date_key, expiration_time)
            self.r.expire(self.cfg['redis_prefix']+':group:'+str(task['user']['project'])+':ram:'+date_key, expiration_time)
            self.r.expire(self.cfg['redis_prefix']+':group:'+str(task['user']['project'])+':time:'+date_key, expiration_time)

    def notify_msg(self, task):
        if not self.cfg['live_events']:
            return
        status = task['status']['primary']
        if task['status']['secondary'] == godutils.STATUS_SECONDARY_KILLED:
            status = godutils.STATUS_SECONDARY_KILLED
        self.r.publish(self.cfg['redis_prefix']+':jobs:pubsub', dumps({
            'user': task['user']['id'],
            'id': task['id'],
            'status': status,
            'name': task['meta']['name']
        }))


    def check_running_jobs(self):
        '''
        Checks if running jobs are over
        '''
        self.logger.debug("Check running jobs")

        nb_running_jobs = self.r.llen(self.cfg['redis_prefix']+':jobs:running')

        nb_elt = 0
        while True and not self.stop_daemon:
            #elts = self.db_jobs.find({'status.primary': 'running'}, limit=self.cfg['max_job_pop'])
            try:
                task_id = None
                elt = None
                if nb_elt < self.cfg['max_job_pop'] and nb_elt < nb_running_jobs:
                    task_id = self.r.lpop(self.cfg['redis_prefix']+':jobs:running')
                    if not task_id:
                        return
                    elt = self.r.get(self.cfg['redis_prefix']+':job:'+str(task_id)+':task')
                    nb_elt += 1
                else:
                    break

                if not elt:
                    return
                task = json.loads(elt)
                # Has been killed in the meanwhile, already managed
                if not self.r.get(self.cfg['redis_prefix']+':job:'+str(task['id'])+':task'):
                    continue

                # If some dynamic fields are present, check for changes
                if 'dynamic_fields' in self.cfg and self.cfg['dynamic_fields']:
                    mongo_task = self.db_jobs.find_one({'id': task['id']})
                    if mongo_task:
                        for dynamic_field in self.cfg['dynamic_fields']:
                            if dynamic_field['name'] in mongo_task['requirements']:
                                task['requirements'][dynamic_field['name']] = mongo_task['requirements'][dynamic_field['name']]

                if is_array_task(task):
                    # If an array parent, only checks if some child tasks are still running
                    nb_subtasks_running = self.r.get(self.cfg['redis_prefix']+':job:'+str(task['id'])+':subtaskrunning')
                    if nb_subtasks_running and int(nb_subtasks_running) > 0:
                        over = False
                    else:
                        over = True
                else:
                    (task, over) = self.executor.watch_tasks(task)
                    if task is None:
                        self.logger.debug('TASK:'+str(task_id)+':Cleaned by executor')
                        continue
                self.logger.debug("TASK:"+str(task['id'])+":"+str(over))
                if over:
                    original_task = self.db_jobs.find_one({'id': task['id']})
                    # If private registry was used, revert to original name without server address
                    task['container']['image'] = original_task['container']['image']
                    # Id, with mesos, is set after task submission, so not present in runtime task
                    # We need to get it from database metadata
                    if 'id' in original_task['container'] and original_task['container']['id']:
                        task['container']['id'] = original_task['container']['id']

                    # Free ports
                    # Put back mapping allocated ports if not managed by executor
                    if 'resources.port' not in self.executor.features():
                        self.executor.release_port(original_task)
                        '''
                        for port in original_task['container']['ports']:
                            host = original_task['container']['meta']['Node']['Name']
                            self.logger.debug('Port:Back:'+host+':'+str(port))
                            self.r.rpush(self.cfg['redis_prefix']+':ports:'+host, port)
                        '''
                    task['container']['ports'] = []

                    if 'failure_policy' not in self.cfg:
                        self.cfg['failure_policy'] = {'strategy': 0, 'skip_failed_nodes': False}

                    if 'failure_policy' not in task['requirements'] or task['requirements']['failure_policy'] > self.cfg['failure_policy']['strategy']:
                        task['requirements']['failure_policy'] = self.cfg['failure_policy']['strategy']
                    # Should it be rescheduled ni case of node crash/error?
                    if  task['requirements']['failure_policy'] > 0 and original_task['status']['secondary'] != godutils.STATUS_SECONDARY_KILL_REQUESTED:
                        # We have a reason failure and not reached max number of restart
                        if 'failure' in task['status'] and task['status']['failure']['reason'] is not None:
                            if 'failure' not in original_task['status']:
                                original_task['status']['failure'] = {'nodes': [], 'reason': None, 'count': 0}

                            task['status']['failure']['count'] = original_task['status']['failure']['count'] + 1
                            task['status']['failure']['nodes'] += original_task['status']['failure']['nodes']

                            if original_task['status']['failure']['count'] <  task['requirements']['failure_policy']:

                                self.logger.debug('Error:Reschedule:' + str(task['id']) + ":" + str(task['status']['failure']['count']))
                                self.r.delete(self.cfg['redis_prefix'] + ':job:' + str(task['id'])+':task')
                                self.r.incr(self.cfg['redis_prefix'] + ':jobs:queued')
                                self.r.incr(self.cfg['redis_prefix'] + ':user:' + str(task['user']['id'])+ ':rate')
                                reason = ''
                                if 'reason' in task['status']:
                                    reason = task['status']['reason']
                                self.db_jobs.update({'id': task['id']}, {'$set': {
                                    'status.primary' : godutils.STATUS_PENDING,
                                    'status.secondary': godutils.STATUS_SECONDARY_RESCHEDULED,
                                    'status.reason': reason,
                                    'status.failure': task['status']['failure']
                                }})
                                self.r.delete(self.cfg['redis_prefix']+':job:'+str(task['id'])+':task')
                                continue

                    if is_array_task(task):
                        self.r.delete(self.cfg['redis_prefix']+':job:'+str(task['id'])+':subtaskrunning')
                        task['requirements']['array']['nb_tasks_over'] = task['requirements']['array']['nb_tasks']
                    if is_array_child_task(task):
                        self.r.decr(self.cfg['redis_prefix']+':job:'+str(task['parent_task_id'])+':subtaskrunning')
                        self.db_jobs.update({'id': task['parent_task_id']}, {'$inc': {'requirements.array.nb_tasks_over': 1}})

                    remove_result = self.db_jobs.remove({'id': task['id']})
                    if remove_result['n'] == 0:
                        # Not present anymore, may have been removed already
                        # Remove from jobs over to replace it
                        self.db_jobsover.remove({'id': task['id']})
                    task['status']['primary'] = godutils.STATUS_OVER
                    task['status']['secondary'] = ''

                    if 'failure' in original_task['status']:
                        task['status']['failure'] = original_task['status']['failure']

                    try:
                        task['status']['exitcode'] = task['container']['meta']['State']['ExitCode']
                    except Exception:
                        self.logger.warn('No exit code: '+str(task['id']))
                    dt = datetime.datetime.now()
                    task['status']['date_over'] = time.mktime(dt.timetuple())

                    task['status']['duration'] = task['status']['date_over'] - task['status']['date_running']
                    task_dir = self.store.get_task_dir(task)
                    god_info_file = os.path.join(task_dir, 'god.info')
                    if os.path.exists(god_info_file):
                        with open(god_info_file) as f:
                            content = f.read().splitlines()
                        try:
                            task['status']['duration'] = int(content[1]) - int(content[0])
                        except Exception as e:
                            self.logger.warn('Failed to read god.info data: '+god_info_file)

                    #task['_id'] = ObjectId(task['_id']['$oid'])
                    del task['_id']
                    task = self.terminate_task(task)
                    self.db_jobsover.insert(task)
                    #self.r.del('god:job:'+str(task['id'])+':container'
                    self.r.delete(self.cfg['redis_prefix']+':job:'+str(task['id'])+':task')
                    if not is_array_task(task):
                        self.update_user_usage(task)
                        self._add_to_stats(task)
                    if not is_array_child_task(task):
                        self.notify_msg(task)
                        Notify.notify_email(task)
                else:
                    can_run = True
                    for watcher in self.watchers:
                        if watcher.can_run(task) is None:
                            can_run = False
                            break
                    if can_run:
                        self.r.rpush(self.cfg['redis_prefix']+':jobs:running', task['id'])
                        self.r.set(self.cfg['redis_prefix']+':job:'+str(task['id'])+':task', dumps(task))
            except KeyboardInterrupt:
                self.logger.warn('Interrupt received, exiting after cleanup')
                self.r.rpush(self.cfg['redis_prefix']+':jobs:running', task['id'])
                sys.exit(0)



    def manage_tasks(self):
        '''
        Schedule and run tasks / kill tasks

        '''
        self.logger.debug('Watcher:'+str(self.hostname)+':Run')
        self.logger.debug("Get tasks to kill")
        if self.stop_daemon:
            self.executor.close()
            return
        kill_task_list = []
        kill_task_length = self.r.llen(self.cfg['redis_prefix']+':jobs:kill')
        for i in range(min(kill_task_length, self.cfg['max_job_pop'])):
            task = self.r.lpop(self.cfg['redis_prefix']+':jobs:kill')
            if task and task != 'None':
                kill_task_list.append(json.loads(task))

        #kill_task_list = self.db_jobs.find({'status.primary': 'kill'})
        #task_list = []
        #for p in kill_task_list:
        #    task_list.append(p)
        if 'kill' in self.executor.features():
            self.kill_tasks(kill_task_list)

        self.logger.debug('Get tasks to suspend')
        if self.stop_daemon:
            self.executor.close()
            return
        suspend_task_list = []
        suspend_task_length = self.r.llen(self.cfg['redis_prefix']+':jobs:suspend')
        for i in range(min(suspend_task_length, self.cfg['max_job_pop'])):
            task = self.r.lpop(self.cfg['redis_prefix']+':jobs:suspend')
            if task:
                suspend_task_list.append(json.loads(task))

        #suspend_task_list = self.db_jobs.find({'status.primary': 'suspend'})
        #task_list = []
        #for p in suspend_task_list:
        #    task_list.append(p)
        if 'pause' in self.executor.features():
            self.suspend_tasks(suspend_task_list)

        self.logger.debug('Get tasks to resume')
        if self.stop_daemon:
            self.executor.close()
            return
        resume_task_list = []
        resume_task_length = self.r.llen(self.cfg['redis_prefix']+':jobs:resume')
        for i in range(min(resume_task_length, self.cfg['max_job_pop'])):
            task = self.r.lpop(self.cfg['redis_prefix']+':jobs:resume')
            if task:
                resume_task_list.append(json.loads(task))

        #resume_task_list = self.db_jobs.find({'status.primary': 'resume'})
        #task_list = []
        #for p in resume_task_list:
        #    task_list.append(p)
        if 'pause' in self.executor.features():
            self.resume_tasks(resume_task_list)

        self.logger.debug('Look for terminated jobs')
        if self.stop_daemon:
            self.executor.close()
            return
        self.check_running_jobs()

    def signal_handler(self, signum, frame):
        GoDWatcher.SIGINT = True
        self.logger.warn('User request to exit')
        self.executor.close()

    def update_status(self):
        if self.status_manager is None:
            return
        if self.status_manager is not None:
            res = self.status_manager.keep_alive(self.proc_name, 'watcher')
            if not res:
                self.logger.error('Watcher:UpdateStatus:Error')
        return

    def run(self, loop=True):
        '''
        Main executor loop

        '''
        self.hostname = None
        infinite = True
        self.executor.open(1)
        self.logger.warn('Start watcher')
        while infinite and True and not GoDWatcher.SIGINT:
                # Schedule timer
            try:
                self.update_status()
            except Exception as e:
                self.logger.error('Watcher:'+str(self.hostname)+':'+str(e))
                traceback_msg = traceback.format_exc()
                self.logger.error(traceback_msg)
            try:
                self.manage_tasks()
            except Exception as e:
                self.logger.error('Watcher:'+str(self.hostname)+':'+str(e))
                traceback_msg = traceback.format_exc()
                self.logger.error(traceback_msg)
            self.reload_config()
            time.sleep(2)
            if not loop:
                infinite = False


        self.executor.close()
