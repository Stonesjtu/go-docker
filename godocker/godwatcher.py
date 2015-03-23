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
from influxdb import client as influxdb

from yapsy.PluginManager import PluginManager
from godocker.iSchedulerPlugin import ISchedulerPlugin
from godocker.iExecutorPlugin import IExecutorPlugin
from godocker.iAuthPlugin import IAuthPlugin
from godocker.utils import is_array_task, is_array_child_task



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

        self.db_influx = None
        if self.cfg.influxdb_host:
            host = self.cfg.influxdb_host
            port = self.cfg.influxdb_port
            username = self.cfg.influxdb_user
            password = self.cfg.influxdb_password
            database = self.cfg.influxdb_db
            self.db_influx = influxdb.InfluxDBClient(host, port, username, password, database)

        self.logger = logging.getLogger('godocker')
        self.logger.setLevel(logging.DEBUG)
        fh = logging.FileHandler('god_watcher.log')
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
             self.scheduler.set_redis_handler(self.r)
             self.scheduler.set_jobs_handler(self.db_jobs)
             self.scheduler.set_users_handler(self.db_users)
             print "Loading scheduler: "+self.scheduler.get_name()
        self.executor = None
        for pluginInfo in simplePluginManager.getPluginsOfCategory("Executor"):
           #simplePluginManager.activatePluginByName(pluginInfo.name)
           if pluginInfo.plugin_object.get_name() == self.cfg.executor:
             self.executor = pluginInfo.plugin_object
             self.executor.set_config(self.cfg)
             self.executor.set_logger(self.logger)
             self.executor.set_redis_handler(self.r)
             self.executor.set_jobs_handler(self.db_jobs)
             self.executor.set_users_handler(self.db_users)
             print "Loading executor: "+self.executor.get_name()


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
                return
            if task['status']['primary'] == 'over':
                continue
            if task['status']['primary'] != 'pending':

                if is_array_task(task):
                    # If an array parent, only checks if some child tasks are still running
                    nb_subtasks_running = int(self.r.get(self.cfg.redis_prefix+':job:'+str(task['id'])+':subtaskrunning'))
                    if nb_subtasks_running > 0:
                        over = False
                        # kill sub tasks
                        for subtask_id in task['requirements']['array']['tasks']:
                            task_to_kill = self.r.get(self.cfg.redis_prefix+':job:'+str(task['id']))
                            self.r.rpush(self.cfg.redis_prefix+':jobs:kill', task_to_kill)
                    else:
                        over = True
                else:
                    (task, over) = self.executor.kill_task(task)

                self._set_task_exitcode(task, 137)
            else:

                if is_array_task(task):
                    # If an array parent, only checks if some child tasks are still running
                    nb_subtasks_running = int(self.r.get(self.cfg.redis_prefix+':job:'+str(task['id'])+':subtaskrunning'))
                    if nb_subtasks_running > 0:
                        over = False
                        # kill sub tasks
                        for subtask_id in task['requirements']['array']['tasks']:
                            task_to_kill = self.r.get(self.cfg.redis_prefix+':job:'+str(task['id']))
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
                for port in task['container']['ports']:
                    host = task['container']['meta']['Node']['Name']
                    self.logger.debug('Port:Back:'+host+':'+str(port))
                    self.r.rpush(self.cfg.redis_prefix+':ports:'+host, port)
                task['container']['ports'] = []
                self.db_jobs.remove({'id': task['id']})
                task['status']['primary'] = 'over'
                task['status']['secondary'] = 'killed'
                dt = datetime.datetime.now()
                task['status']['date_over'] = time.mktime(dt.timetuple())
                del task['_id']
                self.db_jobsover.insert(task)
                self.r.delete(self.cfg.redis_prefix+':job:'+str(task['id'])+':task')
                if is_array_task(task):
                    self.r.delete(self.cfg.redis_prefix+':job:'+str(task['id'])+':subtaskrunning')
                if is_array_child_task(task):
                    self.r.decr(self.cfg.redis_prefix+':job:'+str(task['parent_task_id'])+':subtaskrunning')
                    self.db_jobs.update({'id': task['parent_task_id']}, {'$inc': {'requirements.array.nb_tasks_over': 1}})
                    task['requirements']['array']['nb_tasks_over']
                self.update_user_usage(task)

                if not is_array_child_task(task):
                    self.notify_msg(task)
            else:
                # Could not kill, put back in queue
                self.logger.warn('Executor:Kill:Error:'+str(task['id']))
                self.r.rpush(self.cfg.redis_prefix+':jobs:kill',dumps(task))

    def suspend_tasks(self, suspend_list):
        '''
        Suspend/pause tasks in list
        '''
        if self.stop_daemon:
            return
        for task in suspend_list:
            if self.stop_daemon:
                return

            status = None
            over = False
            if task['status']['primary'] == 'pending' or task['status']['primary'] == 'over':
                status = "suspend rejected"
                over = True
            elif is_array_task(task):
                # suspend not supported for array_tasks
                status = "suspend rejected"
                over = True
            else:
                (task, over) = self.executor.suspend_task(task)
                status = "suspended"
            if over:
                task['status']['secondary'] = status
                self.r.set(self.cfg.redis_prefix+':job:'+str(task['id'])+':task', dumps(task))
                if task['status']['primary'] != 'over':
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
            return
        for task in resume_list:
            if self.stop_daemon:
                return
            status = None
            over = False
            if task['status']['primary'] == 'pending' or task['status']['primary'] == 'over' or task['status']['secondary'] != 'resume requested':
                status = "resume rejected"
                over = True
            else:
                (task, over) = self.executor.resume_task(task)
                status = "resumed"
            if over:
                task['status']['secondary'] = status
                self.r.set(self.cfg.redis_prefix+':job:'+str(task['id'])+':task', dumps(task))
                if task['status']['primary'] != 'over':
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
        task_user = self.db_users.find_one({'id': task['user']['id']})
        last_update = datetime.datetime.now()
        if not 'usage' in task_user:
            task_user['usage'] = {}
        if 'last' not in task_user['usage'] or not task_user['usage']['last']:
            last_delta = 0
        else:
            last_delta = (last_update - task_user['usage']['last']).days

        task_duration = 0
        if 'date_running' in task['status'] and task['status']['date_running'] and task['status']['date_over']:
            task_duration = task['status']['date_over'] - task['status']['date_running']

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

    def notify_msg(self, task):
        if not self.cfg.live_events:
            return
        status = task['status']['primary']
        if task['status']['secondary'] == 'killed':
            status = 'killed'
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
                    # Put back mapping allocated ports
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
                    task['status']['primary'] = 'over'
                    task['status']['secondary'] = ''
                    dt = datetime.datetime.now()
                    task['status']['date_over'] = time.mktime(dt.timetuple())
                    #task['_id'] = ObjectId(task['_id']['$oid'])
                    del task['_id']
                    self.db_jobsover.insert(task)
                    #self.r.del('god:job:'+str(task['id'])+':container'
                    self.r.delete(self.cfg.redis_prefix+':job:'+str(task['id'])+':task')
                    self.update_user_usage(task)
                    self._add_to_stats(task)
                    if not is_array_child_task(task):
                        self.notify_msg(task)
                else:
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
        print "Get tasks to kill"
        if self.stop_daemon:
            return
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
        if self.stop_daemon:
            return
        suspend_task_list = []
        suspend_task_length = self.r.llen(self.cfg.redis_prefix+':jobs:suspend')
        for i in range(min(suspend_task_length, self.cfg.max_job_pop)):
            suspend_task_list.append(json.loads(self.r.lpop(self.cfg.redis_prefix+':jobs:suspend')))

        #suspend_task_list = self.db_jobs.find({'status.primary': 'suspend'})
        #task_list = []
        #for p in suspend_task_list:
        #    task_list.append(p)
        self.suspend_tasks(suspend_task_list)

        print 'Get tasks to resume'
        if self.stop_daemon:
            return
        resume_task_list = []
        resume_task_length = self.r.llen(self.cfg.redis_prefix+':jobs:resume')
        for i in range(min(resume_task_length, self.cfg.max_job_pop)):
            resume_task_list.append(json.loads(self.r.lpop(self.cfg.redis_prefix+':jobs:resume')))

        #resume_task_list = self.db_jobs.find({'status.primary': 'resume'})
        #task_list = []
        #for p in resume_task_list:
        #    task_list.append(p)
        self.resume_tasks(resume_task_list)

        print 'Look for terminated jobs'
        if self.stop_daemon:
            return
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
