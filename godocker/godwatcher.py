from godocker.daemon import Daemon
from config import Config
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

from gelfHandler import gelfHandler
import logstash

from pymongo import MongoClient
from bson.json_util import dumps
from bson.objectid import ObjectId
from influxdb import client as influxdb
from logging.handlers import RotatingFileHandler

from yapsy.PluginManager import PluginManager
from godocker.iSchedulerPlugin import ISchedulerPlugin
from godocker.iExecutorPlugin import IExecutorPlugin
from godocker.iAuthPlugin import IAuthPlugin
from godocker.iWatcherPlugin import IWatcherPlugin
from godocker.utils import is_array_task, is_array_child_task
import godocker.utils as godutils
from godocker.notify import Notify



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
        self.db_projects = self.db.projects

        self.db_influx = None
        if self.cfg.influxdb_host:
            host = self.cfg.influxdb_host
            port = self.cfg.influxdb_port
            username = self.cfg.influxdb_user
            password = self.cfg.influxdb_password
            database = self.cfg.influxdb_db
            self.db_influx = influxdb.InfluxDBClient(host, port, username, password, database)


        self.logger = logging.getLogger('godocker')
        loglevel = logging.ERROR
        if 'log_level' in self.cfg:
            loglevel = self.cfg['log_level']
            if loglevel == 'DEBUG':
                loglevel = logging.DEBUG
            if loglevel == 'INFO':
                loglevel = logging.INFO
            if loglevel == 'ERROR':
                loglevel = logging.ERROR
        if os.getenv('GOD_LOGLEVEL'):
            loglevel = os.environ['GOD_LOGLEVEL']
            if loglevel == 'DEBUG':
                loglevel = logging.DEBUG
            if loglevel == 'INFO':
                loglevel = logging.INFO
            if loglevel == 'ERROR':
                loglevel = logging.ERROR
        self.logger.setLevel(loglevel)
        #fh = logging.FileHandler('god_scheduler.log')
        log_file_path = 'god_watcher.log'
        if 'log_location' in self.cfg:
            log_file_path = os.path.join(self.cfg['log_location'], log_file_path)

        fh = RotatingFileHandler(log_file_path, maxBytes=10000000,
                                      backupCount=5)
        fh.setLevel(loglevel)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)

        if 'log_graylog_host' in self.cfg and self.cfg['log_graylog_host']:
            graypy_handler = gelfHandler(host=self.cfg['log_graylog_host'],port=self.cfg['log_graylog_port'], proto='UDP')
            graypy_handler.setLevel(loglevel)
            self.logger.addHandler(graypy_handler)

        if 'log_logstash_host' in self.cfg and self.cfg['log_logstash_host']:
            self.logger.addHandler(logstash.LogstashHandler(self.cfg['log_logstash_host'], self.cfg['log_logstash_port'], version=1))

        if not self.cfg.plugins_dir:
            dirname, filename = os.path.split(os.path.abspath(__file__))
            self.cfg.plugins_dir = os.path.join(dirname, '..', 'plugins')


        Notify.set_config(self.cfg)
        Notify.set_logger(self.logger)

        # Build the manager
        simplePluginManager = PluginManager()
        # Tell it the default place(s) where to find plugins
        simplePluginManager.setPluginPlaces([self.cfg.plugins_dir])
        simplePluginManager.setCategoriesFilter({
           "Scheduler": ISchedulerPlugin,
           "Executor": IExecutorPlugin,
           "Auth": IAuthPlugin,
           "Watcher": IWatcherPlugin
         })
        # Load all plugins
        simplePluginManager.collectPlugins()

        # Activate plugins
        self.scheduler = None
        for pluginInfo in simplePluginManager.getPluginsOfCategory("Scheduler"):
           #simplePluginManager.activatePluginByName(pluginInfo.name)
           if pluginInfo.plugin_object.get_name() == self.cfg.scheduler_policy:
             self.scheduler = pluginInfo.plugin_object
             self.scheduler.set_logger(self.logger)
             self.scheduler.set_config(self.cfg)
             self.scheduler.set_redis_handler(self.r)
             self.scheduler.set_jobs_handler(self.db_jobs)
             self.scheduler.set_users_handler(self.db_users)
             self.scheduler.set_projects_handler(self.db_projects)
             print "Loading scheduler: "+self.scheduler.get_name()
        self.executor = None
        for pluginInfo in simplePluginManager.getPluginsOfCategory("Executor"):
           #simplePluginManager.activatePluginByName(pluginInfo.name)
           if pluginInfo.plugin_object.get_name() == self.cfg.executor:
             self.executor = pluginInfo.plugin_object
             self.executor.set_logger(self.logger)
             self.executor.set_config(self.cfg)
             self.executor.set_redis_handler(self.r)
             self.executor.set_jobs_handler(self.db_jobs)
             self.executor.set_users_handler(self.db_users)
             self.executor.set_projects_handler(self.db_projects)
             print "Loading executor: "+self.executor.get_name()

        self.watchers = []
        if 'watchers' in self.cfg and self.cfg.watchers is not None:
            watchers = self.cfg.watchers.split(',')
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
             print "Add watcher: "+watcher.get_name()



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
                    #nb_subtasks_running = self.r.get(self.cfg.redis_prefix+':job:'+str(task['id'])+':subtaskrunning')
                    nb_subtasks_running = self.r.get(self.cfg.redis_prefix+':job:'+str(task['id'])+':subtask')
                    if nb_subtasks_running and int(nb_subtasks_running) > 0:
                        over = False
                        # kill sub tasks
                        for subtask_id in task['requirements']['array']['tasks']:
                            task_to_kill = self.r.get(self.cfg.redis_prefix+':job:'+str(subtask_id))
                            self.r.rpush(self.cfg.redis_prefix+':jobs:kill', task_to_kill)
                    else:
                        over = True
                else:
                    (task, over) = self.executor.kill_task(task)

                self._set_task_exitcode(task, 137)
            else:
                if is_array_task(task):
                    # If an array parent, only checks if some child tasks are still running
                    nb_subtasks_running = int(self.r.get(self.cfg.redis_prefix+':job:'+str(task['id'])+':subtask'))
                    if nb_subtasks_running > 0:
                        over = False
                        # kill sub tasks
                        for subtask_id in task['requirements']['array']['tasks']:
                            task_to_kill = self.r.get(self.cfg.redis_prefix+':job:'+str(subtask_id))
                            if task_to_kill is None:
                                task_to_kill = dumps(self.db_jobs.find_one({'id': subtask_id}))
                                self.r.set(self.cfg.redis_prefix+':job:'+str(subtask_id)+':task', task_to_kill)
                            self.r.rpush(self.cfg.redis_prefix+':jobs:kill', task_to_kill)
                    else:
                        over = True
                        self._set_task_exitcode(task, 137)
                        self.r.decr(self.cfg.redis_prefix+':jobs:queued')
                else:
                    over = True
                    self._set_task_exitcode(task, 137)
                    self.r.decr(self.cfg.redis_prefix+':jobs:queued')
            # If not over, executor could not kill the task
            if over:
                self.logger.debug('Executor:Kill:Success:'+str(task['id']))

                original_task = self.db_jobs.find_one({'id': task['id']})
                if 'resources.port' not in self.executor.features():
                    for port in original_task['container']['ports']:
                        host = original_task['container']['meta']['Node']['Name']
                        self.logger.debug('Port:Back:'+host+':'+str(port))
                        self.r.rpush(self.cfg.redis_prefix+':ports:'+host, port)

                task['container']['ports'] = []

                # Check for reschedule request
                if original_task and original_task['status']['secondary'] == godutils.STATUS_SECONDARY_RESCHEDULE_REQUESTED:
                    self.r.delete(self.cfg.redis_prefix+':job:'+str(task['id'])+':task')
                    self.r.incr(self.cfg.redis_prefix+':jobs:queued')
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
                dt = datetime.datetime.now()
                task['status']['date_over'] = time.mktime(dt.timetuple())
                del task['_id']
                self.db_jobsover.insert(task)
                self.r.delete(self.cfg.redis_prefix+':job:'+str(task['id'])+':task')
                if is_array_task(task):
                    self.r.delete(self.cfg.redis_prefix+':job:'+str(task['id'])+':subtaskrunning')
                    self.r.delete(self.cfg.redis_prefix+':job:'+str(task['id'])+':subtask')
                if is_array_child_task(task):
                    self.r.decr(self.cfg.redis_prefix+':job:'+str(task['parent_task_id'])+':subtaskrunning')
                    self.r.decr(self.cfg.redis_prefix+':job:'+str(task['parent_task_id'])+':subtask')
                    self.db_jobs.update({'id': task['parent_task_id']}, {'$inc': {'requirements.array.nb_tasks_over': 1}})

                if not is_array_task(task):
                    self.update_user_usage(task)

                if not is_array_child_task(task):
                    self.notify_msg(task)
                    Notify.notify_email(task)
            else:
                # Could not kill, put back in queue
                self.logger.warn('Executor:Kill:Error:'+str(task['id']))
                self.r.rpush(self.cfg.redis_prefix+':jobs:kill',dumps(task))

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
                self.r.set(self.cfg.redis_prefix+':job:'+str(task['id'])+':task', dumps(task))
                if task['status']['primary'] != godutils.STATUS_OVER:
                    self.db_jobs.update({'id' : task['id']},{'$set': {'status.secondary': status}})
            else:
                # Could not kill, put back in queue
                self.logger.warn('Executor:Suspend:Error:'+str(task['id']))
                self.r.rpush(self.cfg.redis_prefix+':jobs:suspend',dumps(task))



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
                self.r.set(self.cfg.redis_prefix+':job:'+str(task['id'])+':task', dumps(task))
                if task['status']['primary'] != godutils.STATUS_OVER:
                    self.db_jobs.update({'id' : task['id']},{'$set': {'status.secondary': status}})
            else:
                # Could not resumed, put back in queue
                self.logger.warn('Executor:Resume:Error:'+str(task['id']))
                self.r.rpush(self.cfg.redis_prefix+':jobs:resume',dumps(task))



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
                task_waiting
            ]],
            'name':'god_task_usage',
            'columns': ["user", "cpu", "ram", "durationtime", "waitingtime"]
        }]
        try:
            self.db_influx.write_points(data)
        except Exception as e:
            # Do not fail on stat writing
            self.logger.error('Stat:Error:'+str(e))

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


        if last_delta > self.cfg.user_reset_usage_duration:
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
        group_last = self.r.get(self.cfg.redis_prefix+':group:'+str(task['user']['project'])+':last')
        if group_last is None:
            group_last = timestamp
        else:
            group_last = float(group_last)
        last_delta = (timestamp - group_last) / (3600 * 24) # In days
        if last_delta > self.cfg.user_reset_usage_duration:
            self.r.set(self.cfg.redis_prefix+':group:'+str(task['user']['project'])+':cpu', task['requirements']['cpu'])
            self.r.set(self.cfg.redis_prefix+':group:'+str(task['user']['project'])+':ram', task['requirements']['ram'])
            self.r.set(self.cfg.redis_prefix+':group:'+str(task['user']['project'])+':time', task_duration)
        else:
            self.r.incr(self.cfg.redis_prefix+':group:'+str(task['user']['project'])+':cpu', task['requirements']['cpu'])
            self.r.incr(self.cfg.redis_prefix+':group:'+str(task['user']['project'])+':ram', task['requirements']['ram'])
            self.r.incrbyfloat(self.cfg.redis_prefix+':group:'+str(task['user']['project'])+':time', task_duration)
        group_last = self.r.set(self.cfg.redis_prefix+':group:'+str(task['user']['project'])+':last', timestamp)
        '''
        # Set an RDD like over a time window of self.cfg.user_reset_usage_duration days
        dt = datetime.datetime.now()
        date_key = str(dt.year)+'_'+str(dt.month)+'_'+str(dt.day)
        set_expire = True
        if self.r.exists(self.cfg.redis_prefix+':user:'+str(task['user']['id'])+':cpu:'+date_key):
            set_expire = False
        self.r.incr(self.cfg.redis_prefix+':user:'+str(task['user']['id'])+':cpu:'+date_key, task['requirements']['cpu'])
        self.r.incr(self.cfg.redis_prefix+':user:'+str(task['user']['id'])+':ram:'+date_key, task['requirements']['ram'])
        self.r.incrbyfloat(self.cfg.redis_prefix+':user:'+str(task['user']['id'])+':time:'+date_key, task_duration)
        if set_expire:
            expiration_time = self.cfg.user_reset_usage_duration * 24 * 3600
            self.r.expire(self.cfg.redis_prefix+':user:'+str(task['user']['id'])+':cpu:'+date_key, expiration_time)
            self.r.expire(self.cfg.redis_prefix+':user:'+str(task['user']['id'])+':ram:'+date_key, expiration_time)
            self.r.expire(self.cfg.redis_prefix+':user:'+str(task['user']['id'])+':time:'+date_key, expiration_time)

        set_expire = True
        if self.r.exists(self.cfg.redis_prefix+':group:'+str(task['user']['project'])+':cpu:'+date_key):
            set_expire = False
        self.r.incr(self.cfg.redis_prefix+':group:'+str(task['user']['project'])+':cpu:'+date_key, task['requirements']['cpu'])
        self.r.incr(self.cfg.redis_prefix+':group:'+str(task['user']['project'])+':ram:'+date_key, task['requirements']['ram'])
        self.r.incrbyfloat(self.cfg.redis_prefix+':group:'+str(task['user']['project'])+':time:'+date_key, task_duration)
        if set_expire:
            expiration_time = self.cfg.user_reset_usage_duration * 24 * 3600
            self.r.expire(self.cfg.redis_prefix+':group:'+str(task['user']['project'])+':cpu:'+date_key, expiration_time)
            self.r.expire(self.cfg.redis_prefix+':group:'+str(task['user']['project'])+':ram:'+date_key, expiration_time)
            self.r.expire(self.cfg.redis_prefix+':group:'+str(task['user']['project'])+':time:'+date_key, expiration_time)

    def notify_msg(self, task):
        if not self.cfg.live_events:
            return
        status = task['status']['primary']
        if task['status']['secondary'] == godutils.STATUS_SECONDARY_KILLED:
            status = godutils.STATUS_SECONDARY_KILLED
        self.r.publish(self.cfg.redis_prefix+':jobs:pubsub', dumps({
            'user': task['user']['id'],
            'id': task['id'],
            'status': status,
            'name': task['meta']['name']
        }))


    def check_running_jobs(self):
        '''
        Checks if running jobs are over
        '''
        print "Check running jobs"
        nb_elt = 1
        #elts  = self.r.lrange('jobs:running', lmin, lmin+lrange)
        nb_running_jobs = self.r.llen(self.cfg.redis_prefix+':jobs:running')
        task_id = self.r.lpop(self.cfg.redis_prefix+':jobs:running')
        if not task_id:
            return
        elt = self.r.get(self.cfg.redis_prefix+':job:'+str(task_id)+':task')
        while True and not self.stop_daemon:
            #elts = self.db_jobs.find({'status.primary': 'running'}, limit=self.cfg.max_job_pop)
            try:
                if not elt:
                    return
                task = json.loads(elt)
                # Has been killed in the meanwhile, already managed
                if not self.r.get(self.cfg.redis_prefix+':job:'+str(task['id'])+':task'):
                    continue
                if is_array_task(task):
                    # If an array parent, only checks if some child tasks are still running
                    nb_subtasks_running = int(self.r.get(self.cfg.redis_prefix+':job:'+str(task['id'])+':subtaskrunning'))
                    if nb_subtasks_running > 0:
                        over = False
                    else:
                        over = True
                else:
                    (task, over) = self.executor.watch_tasks(task)
                self.logger.debug("TASK:"+str(task['id'])+":"+str(over))
                if over:
                    # Free ports
                    # Put back mapping allocated ports if not managed by executor
                    if 'resources.port' not in self.executor.features():
                        for port in task['container']['ports']:
                            host = task['container']['meta']['Node']['Name']
                            self.logger.debug('Port:Back:'+host+':'+str(port))
                            self.r.rpush(self.cfg.redis_prefix+':ports:'+host, port)
                    task['container']['ports'] = []

                    if is_array_task(task):
                        self.r.delete(self.cfg.redis_prefix+':job:'+str(task['id'])+':subtaskrunning')
                        task['requirements']['array']['nb_tasks_over'] = task['requirements']['array']['nb_tasks']
                    if is_array_child_task(task):
                        self.r.decr(self.cfg.redis_prefix+':job:'+str(task['parent_task_id'])+':subtaskrunning')
                        self.db_jobs.update({'id': task['parent_task_id']}, {'$inc': {'requirements.array.nb_tasks_over': 1}})

                    remove_result = self.db_jobs.remove({'id': task['id']})
                    if remove_result['n'] == 0:
                        # Not present anymore, may have been removed already
                        # Remove from jobs over to replace it
                        self.db_jobsover.remove({'id': task['id']})
                    task['status']['primary'] = godutils.STATUS_OVER
                    task['status']['secondary'] = ''
                    dt = datetime.datetime.now()
                    task['status']['date_over'] = time.mktime(dt.timetuple())
                    #task['_id'] = ObjectId(task['_id']['$oid'])
                    del task['_id']
                    self.db_jobsover.insert(task)
                    #self.r.del('god:job:'+str(task['id'])+':container'
                    self.r.delete(self.cfg.redis_prefix+':job:'+str(task['id'])+':task')
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
                        self.r.rpush(self.cfg.redis_prefix+':jobs:running', task['id'])
                        self.r.set(self.cfg.redis_prefix+':job:'+str(task['id'])+':task', dumps(task))
            except KeyboardInterrupt:
                self.logger.warn('Interrupt received, exiting after cleanup')
                self.r.rpush(self.cfg.redis_prefix+':jobs:running', task['id'])
                sys.exit(0)
            if nb_elt < self.cfg.max_job_pop and nb_elt < nb_running_jobs:
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
        self.logger.debug('Watcher:'+str(self.hostname)+':Run')
        print "Get tasks to kill"
        if self.stop_daemon:
            self.executor.close()
            return
        kill_task_list = []
        kill_task_length = self.r.llen(self.cfg.redis_prefix+':jobs:kill')
        for i in range(min(kill_task_length, self.cfg.max_job_pop)):
            task = self.r.lpop(self.cfg.redis_prefix+':jobs:kill')
            if task and task != 'None':
                kill_task_list.append(json.loads(task))

        #kill_task_list = self.db_jobs.find({'status.primary': 'kill'})
        #task_list = []
        #for p in kill_task_list:
        #    task_list.append(p)
        if 'kill' in self.executor.features():
            self.kill_tasks(kill_task_list)

        print 'Get tasks to suspend'
        if self.stop_daemon:
            self.executor.close()
            return
        suspend_task_list = []
        suspend_task_length = self.r.llen(self.cfg.redis_prefix+':jobs:suspend')
        for i in range(min(suspend_task_length, self.cfg.max_job_pop)):
            task = self.r.lpop(self.cfg.redis_prefix+':jobs:suspend')
            if task:
                suspend_task_list.append(json.loads(task))

        #suspend_task_list = self.db_jobs.find({'status.primary': 'suspend'})
        #task_list = []
        #for p in suspend_task_list:
        #    task_list.append(p)
        if 'pause' in self.executor.features():
            self.suspend_tasks(suspend_task_list)

        print 'Get tasks to resume'
        if self.stop_daemon:
            self.executor.close()
            return
        resume_task_list = []
        resume_task_length = self.r.llen(self.cfg.redis_prefix+':jobs:resume')
        for i in range(min(resume_task_length, self.cfg.max_job_pop)):
            task = self.r.lpop(self.cfg.redis_prefix+':jobs:resume')
            if task:
                resume_task_list.append(json.loads(task))

        #resume_task_list = self.db_jobs.find({'status.primary': 'resume'})
        #task_list = []
        #for p in resume_task_list:
        #    task_list.append(p)
        if 'pause' in self.executor.features():
            self.resume_tasks(resume_task_list)

        print 'Look for terminated jobs'
        if self.stop_daemon:
            self.executor.close()
            return
        self.check_running_jobs()

    def signal_handler(self, signum, frame):
        GoDWatcher.SIGINT = True
        self.logger.warn('User request to exit')
        self.executor.close()

    def update_status(self):
        dt = datetime.datetime.now()
        timestamp = time.mktime(dt.timetuple())
        if not self.hostname:
            hostname = socket.gethostbyaddr(socket.gethostname())[0]
            host_exists = True
            index = 1
            if os.getenv('GOD_PROCID'):
                index = os.environ['GOD_PROCID']
            else:
                while host_exists:
                    if self.r.get(self.cfg.redis_prefix+':procs:'+hostname+'-'+str(index)) is not None:
                        index += 1
                    else:
                        host_exists = False
            self.hostname = hostname + '-' + str(index)
        self.r.hset(self.cfg.redis_prefix+':procs', self.hostname, 'watcher')
        self.r.set(self.cfg.redis_prefix+':procs:'+self.hostname, timestamp)

    def run(self, loop=True):
        '''
        Main executor loop

        '''
        self.hostname = None
        infinite = True
        self.executor.open(1)
        while infinite and True and not GoDWatcher.SIGINT:
            # Schedule timer
            self.update_status()
            self.manage_tasks()
            time.sleep(2)
            if not loop:
                infinite = False
        self.executor.close()
