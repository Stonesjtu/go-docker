from godocker.daemon import Daemon

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

import graypy
import logstash



from pymongo import MongoClient
from pymongo import DESCENDING as pyDESCENDING
from bson.json_util import dumps
from yapsy.PluginManager import PluginManager
from influxdb import client as influxdb
from logging.handlers import RotatingFileHandler

from godocker.iSchedulerPlugin import ISchedulerPlugin
from godocker.iExecutorPlugin import IExecutorPlugin
from godocker.iAuthPlugin import IAuthPlugin
from godocker.iWatcherPlugin import IWatcherPlugin
from godocker.iStatusPlugin import IStatusPlugin


#from godocker.pairtreeStorage import PairtreeStorage
from godocker.storageManager import StorageManager
from godocker.utils import is_array_child_task, is_array_task
import godocker.utils as godutils
from godocker.notify import Notify

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

    def check_redis(self):
        jobs_mongo = self.db_jobs.find()
        nb_jobs_mongo = jobs_mongo.count()
        nb_jobs_over_mongo = self.db_jobsover.find().count()
        #nb_running_redis = self.r.llen(self.cfg['redis_prefix']+':jobs:running')
        if nb_jobs_mongo == 0:
            # Nothing running, reset redis some init values just in case
            self.r.set(self.cfg['redis_prefix']+':jobs:queued', 0)
            self.r.delete(self.cfg['redis_prefix']+':jobs:running')
        if nb_jobs_mongo >0 or nb_jobs_over_mongo >0:
            # Not the first run
            jobs_counter = self.r.get(self.cfg['redis_prefix']+':jobs')
            if jobs_counter and int(jobs_counter) > 0:
                self.logger.info("Redis database looks ok")
                return
            else:
                # Redis lost its data
                self.logger.warn("Redis database looks empty, syncing data....")
                # Get Max id
                max_task_id = 0
                if nb_jobs_mongo > 0:
                    max_task = self.db_jobs.find().sort("id", pyDESCENDING).limit(1)
                    max_task_id = max_task[0]['id']
                else:
                    max_task = self.db_jobsover.find().sort("id", pyDESCENDING).limit(1)
                    max_task_id = max_task[0]['id']
                self.r.set(self.cfg['redis_prefix']+':jobs', max_task_id)
                # Set running and kill tasks
                for task in jobs_mongo:
                    if task['status']['secondary'] == godutils.STATUS_SECONDARY_KILL_REQUESTED:
                        self.r.rpush(cfg['redis_prefix']+':jobs:kill', dumps(task))
                    if task['status']['secondary'] == godutils.STATUS_SECONDARY_SUSPEND_REQUESTED:
                        self.r.rpush(cfg['redis_prefix']+':jobs:suspend', dumps(task))
                    if task['status']['secondary'] == godutils.STATUS_SECONDARY_RESUME_REQUESTED:
                        self.r.rpush(cfg['redis_prefix']+':jobs:resume', dumps(task))

                    if task['status']['primary'] == godutils.STATUS_PENDING:
                        self.r.incr(self.cfg['redis_prefix']+':jobs:queued')
                        continue
                    if task['status']['primary'] == godutils.STATUS_RUNNING:
                        self.r.rpush(self.cfg['redis_prefix']+':jobs:running', task['id'])
                        self.r.set(self.cfg['redis_prefix']+':job:'+str(task['id'])+':task', dumps(task))
                        continue
                self.logger.warn("Redis database has been synced, continuing.")
        else:
            self.logger.info("No task found in database, looks like a first run")

    def load_config(self, f):
        '''
        Load configuration from file path
        '''
        self.cfg= None
        with open(f, 'r') as ymlfile:
            self.cfg = yaml.load(ymlfile)


        self.hostname = socket.gethostbyaddr(socket.gethostname())[0]
        self.proc_name = 'scheduler-'+self.hostname
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
        self.logger = logging.getLogger('godocker-scheduler')

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
            watchers = self.cfg['watchers'].split(',')
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

        self.auth_policy = None
        for pluginInfo in simplePluginManager.getPluginsOfCategory("Auth"):
            if pluginInfo.plugin_object.get_name() == self.cfg['auth_policy']:
                 self.auth_policy = pluginInfo.plugin_object
                 self.auth_policy.set_logger(self.logger)
                 self.auth_policy.set_config(self.cfg)
                 print("Loading auth policy: "+self.auth_policy.get_name())

        self.check_redis()


    def add_task(self, task):
        '''
        Add a new task, if status not set, set it to pending

        Automatically atribute an id to the task

        :param task: Task to insert
        :type task: dict
        :return: task id
        '''
        if 'rate_limit' in self.cfg and self.cfg['rate_limit'] is not None:
            current_rate = self.r.get(self.cfg['redis_prefix'] +
                                   ':user:' + str(task['user']['id'])+ ':rate')
            if current_rate is not None and int(current_rate) >= self.cfg['rate_limit']:
                return None

        if 'rate_limit_all' in self.cfg and self.cfg['rate_limit_all'] is not None:
            current_rate = self.r.get(self.cfg['redis_prefix'] +
                                   ':jobs:queued')
            if current_rate is not None and int(current_rate) >= self.cfg['rate_limit_all']:
                return None


        task_id = self.r.incr(self.cfg['redis_prefix']+':jobs')
        self.r.incr(self.cfg['redis_prefix']+':jobs:queued')
        self.r.incr(self.cfg['redis_prefix'] + ':user:' + str(task['user']['id'])+ ':rate')
        task['id'] = task_id
        if not task['status']['primary']:
            task['status']['primary'] = godutils.STATUS_PENDING

        dt = datetime.datetime.now()
        if 'date' not in task:
            task['date'] = time.mktime(dt.timetuple())
        if 'project' not in task['user']:
            task['user']['project'] = 'default'


        if is_array_task(task):
            task['requirements']['array']['nb_tasks'] = 0
            task['requirements']['array']['nb_tasks_over'] = 0
            task['requirements']['array']['tasks'] = []
            array_req = task['requirements']['array']['values'].split(':')
            array_first = 0
            array_last = 0
            array_step = 1
            if len(array_req) == 1:
                array_first = 1
                array_last = int(array_req[0])
                array_step = 1
            else:
                array_first = int(array_req[0])
                array_last = int(array_req[1])
                if len(array_req) == 3:
                    array_step = int(array_req[2])
            for i in range(array_first, array_last + array_step, array_step):
                subtask = deepcopy(task)
                subtask['requirements']['array']['nb_tasks'] = 0
                subtask['requirements']['array']['tasks'] = []
                subtask['requirements']['array']['task_id'] = i
                subtask['parent_task_id'] = task['id']
                subtask['requirements']['array']['values'] = None
                subtask_id = self.add_task(subtask)
                task['requirements']['array']['nb_tasks'] += 1
                task['requirements']['array']['tasks'].append(subtask_id)
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
        dt = datetime.datetime.now()
        start_time = time.mktime(dt.timetuple())
        tasks = self.scheduler.schedule(pending_list)
        dt = datetime.datetime.now()
        end_time = time.mktime(dt.timetuple())
        nb_pending = self.r.get(self.cfg['redis_prefix']+':jobs:queued')
        if nb_pending is None:
            nb_pending = 0
        else:
            nb_pending = int(nb_pending)
        nb_running = self.r.llen(self.cfg['redis_prefix']+':jobs:running')
        if nb_running is None:
            nb_running = 0
        else:
            nb_running = int(nb_running)
        self._add_to_stats(nb_pending, nb_running, end_time - start_time)
        self._prometheus_stats('god_scheduler_sched_duration', end_time - start_time)
        return tasks


    def _update_scheduled_task_status(self, running_tasks, rejected_tasks):
        if running_tasks:
            for r in running_tasks:
                if 'ticket_share' not in r['requirements']:
                    r['requirements']['ticket_share'] = 0
                if is_array_child_task(r):
                    self.r.incr(self.cfg['redis_prefix']+':job:'+str(r['parent_task_id'])+':subtaskrunning')
                self.r.rpush(self.cfg['redis_prefix']+':jobs:running', r['id'])
                #self.r.set('god:job:'+str(r['id'])+':container', r['container']['id'])
                r['status']['primary'] = godutils.STATUS_RUNNING
                if 'override' not in r['status'] or not r['status']['override']:
                    r['status']['secondary'] = None
                    r['status']['reason'] = ''
                dt = datetime.datetime.now()
                r['status']['date_running'] = time.mktime(dt.timetuple())
                self.r.set(self.cfg['redis_prefix']+':job:'+str(r['id'])+':task', dumps(r))
                self.r.decr(self.cfg['redis_prefix']+':jobs:queued')
                self.r.decr(self.cfg['redis_prefix'] + ':user:' + str(r['user']['id'])+ ':rate')
                self.db_jobs.update({'id': r['id']},
                                    {'$set': {
                                        'requirements.ticket_share': r['requirements']['ticket_share'],
                                        'status.primary': r['status']['primary'],
                                        'status.secondary': r['status']['secondary'],
                                        'status.reason': '',
                                        'status.date_running': r['status']['date_running'],
                                        'container': r['container']}})
                Notify.notify_email(r)
        if rejected_tasks:
            for r in rejected_tasks:
                if 'ticket_share' not in r['requirements']:
                    r['requirements']['ticket_share'] = 0
                # Put back mapping allocated ports
                if 'resources.port' not in self.executor.features():
                    if r['container']['meta'] and 'Node' in r['container']['meta'] and 'Name' in r['container']['meta']['Node']:
                        host = r['container']['meta']['Node']['Name']
                        for port in r['container']['ports']:
                            self.r.rpush(self.cfg['redis_prefix']+':ports:'+host, port)
                r['status']['reason'] = 'Not enough resources available'
                self.db_jobs.update({'id': r['id']},
                                    {'$set': {
                                        'requirements.ticket_share': r['requirements']['ticket_share'],
                                        'status.reason': r['status']['reason'],
                                        'status.secondary': godutils.STATUS_SECONDARY_SCHEDULER_REJECTED,
                                        'container.ports': []
                                        }
                                    })


    def _create_command(self, task):
        '''
        Write command script on disk
        '''
        if 'guest' in task['user'] and task['user']['guest']:
            home_requested = False
            for volume in task['container']['volumes']:
                if volume['name'] == 'home':
                    home_requested = True
                    if not os.path.exists(volume['path']):
                        self.logger.debug("Create home dir for guest:" + volume['path'])
                        os.makedirs(volume['path'])
                        os.chmod(volume['path'], 0o777)
                    break
        # Add task directory
        task_dir = self.store.get_task_dir(task)
        parent_task = None
        task_cmd = task['command']['cmd']
        if sys.version_info.major == 2:
            task_cmd = task_cmd.encode('utf-8')
        if is_array_child_task(task):
            parent_task = self.db_jobs.find_one({'id': task['parent_task_id']})
            task_dir = self.store.get_task_dir(parent_task)
            task_dir = os.path.join(task_dir, str(task['requirements']['array']['task_id']))
            if not os.path.exists(task_dir):
                os.makedirs(task_dir)
                os.chmod(task_dir, 0o777)
            script_file = self.store.add_file(parent_task, 'cmd.sh',
                                              task_cmd,
                                              str(task['requirements']['array']['task_id']))
            os.chmod(script_file, 0o755)
            task['command']['script'] = os.path.join('/mnt/go-docker',os.path.basename(script_file))
        else:
            script_file = self.store.add_file(task, 'cmd.sh',
                                              task_cmd)
            os.chmod(script_file, 0o755)
            task['command']['script'] = os.path.join('/mnt/go-docker',os.path.basename(script_file))

        task['container']['volumes'].append({
            'name': 'go-docker',
            'acl': 'rw',
            'path': task_dir,
            'mount': '/mnt/go-docker'
        })
        # Write wrapper script to run script with user uidNumber/guidNumber
        # Chown files in shared dir to gives files ACLs to user at the end
        # Exit with code of executed cmd.sh
        user_id = task['user']['id']
        cmd = "#!/bin/bash\n"
        cmd += "groupadd --gid "+str(task['user']['gid'])+" "+user_id
        cmd += " ; useradd --uid "+str(task['user']['uid'])+" --gid "+str(task['user']['gid'])+" "+user_id+"\n"
        cmd += "usermod -p"+task['user']['credentials']['apikey']+"  "+user_id+"\n"
        # Create secondary groups
        if 'sgids' in task['user']:
            for sgid in task['user']['sgids']:
                cmd += "groupadd --gid "+str(sgid)+" group"+str(sgid)+"\n"
                cmd += "usermod -a -G group"+str(sgid)+" "+user_id+"\n"

        # docker-plugin-zfs
        if 'plugin_zfs' in self.cfg and self.cfg['plugin_zfs']:
            cmd += "if [ -e /tmp-data ]; then\n"
            cmd += "    chown -R "+user_id+" /tmp-data\n"
            cmd += "fi\n"

        cmd += "cd /mnt/go-docker\n"
        array_cmd = ""
        if parent_task:
            array_req = parent_task['requirements']['array']['values'].split(':')
            array_first = 0
            array_last = 0
            array_step = 1
            if len(array_req) == 1:
                array_first = 1
                array_last = int(array_req[0])
                array_step = 1
            else:
                array_first = int(array_req[0])
                array_last = int(array_req[1])
                if len(array_req) == 3:
                    array_step = int(array_req[2])
            cmd += "export GOGOCKER_TASK_ID="+str(task['requirements']['array']['task_id'])
            array_cmd += " ; export GOGOCKER_TASK_ID="+str(task['requirements']['array']['task_id'])
            cmd += "export GOGOCKER_TASK_FIRST="+str(array_first)
            array_cmd += " ; export GOGOCKER_TASK_FIRST="+str(array_first)
            cmd += "export GOGOCKER_TASK_LAST="+str(array_last)
            array_cmd += " ; export GOGOCKER_TASK_LAST="+str(array_last)
            cmd += "export GOGOCKER_TASK_STEP="+str(array_step)
            array_cmd += " ; export GOGOCKER_TASK_STEP="+str(array_step)

        cmd += "export GODOCKER_JID="+str(task['id'])+"\n"
        cmd += "export GODOCKER_PWD=/mnt/go-docker\n"
        vol_home = "export GODOCKER_HOME=/mnt/go-docker"
        for v in task['container']['volumes']:
            if v['name'] == 'home':
                vol_home = "export GODOCKER_HOME=" + v['mount']
                break
        cmd += vol_home+"\n"
        cmd += "startprocess=`date +%s`\n"

        cmd += str(self.store.get_pre_command())+"\n"

        if not task['container']['root']:
            cmd += "su - "+user_id+" -c \""+vol_home + array_cmd + " ; export GODOCKER_JID="+str(task['id'])+" ; export GODOCKER_PWD=/mnt/go-docker ; cd /mnt/go-docker ; /mnt/go-docker/cmd.sh 2> /mnt/go-docker/god.err 1> /mnt/go-docker/god.log\"\n"
        else:
            cmd += "/mnt/go-docker/cmd.sh 2> /mnt/go-docker/god.err 1> /mnt/go-docker/god.log\n"

        if task['command']['interactive']:
            # should execute ssh, copy user ssh key from home in /root/.ssh/authorized_keys or /home/gocker/.ssh/authorized_keys
            # Need to create .ssh dir
            # sshd MUST be installed in container
            ssh_dir = ""
            if task['container']['root']:
                ssh_dir = "/root/.ssh"
                cmd += "echo 'root:"+task['user']['credentials']['apikey']+"' | chpasswd\n"
            else:
                ssh_dir = "/home/"+user_id+"/.ssh"
                cmd += "echo '"+user_id+":"+task['user']['credentials']['apikey']+"' | chpasswd\n"
            cmd +="mkdir -p "+ssh_dir+"\n"
            cmd +="echo \"" + task['user']['credentials']['public'] + "\" > "+ssh_dir+"/authorized_keys\n"
            cmd +="chmod 600 " + ssh_dir +"/authorized_keys\n"
            if not task['container']['root']:
                cmd +="chown -R "+user_id+":"+user_id+" /home/"+user_id+"\n"
                cmd +="chmod 644 /home/"+user_id+"/.ssh/authorized_keys\n"

            cmd += "\nif hash sshd 2>/dev/null; then\n"
            cmd += "    echo \"ssh server installed\"\n"
            cmd += "else\n"
            cmd += "    echo \"ssh server not installed\"\n"
            cmd += "if [ -n \"$(command -v yum)\" ]; then\n"
            cmd += "     yum -y install openssh-server\n"
            cmd += "     ssh-keygen -f /etc/ssh/ssh_host_rsa_key -N '' -t rsa\n"
            cmd += "fi\n"
            cmd += "if [ -n \"$(command -v apk)\" ]; then\n"
            cmd += "     apk add openssh\n"
            cmd += "     ssh-keygen -f /etc/ssh/ssh_host_rsa_key -N '' -t rsa\n"
            cmd += "fi\n"
            cmd += "if [ -n \"$(command -v apt-get)\" ]; then\n"
            cmd += "    apt-get update\n"
            cmd += "    apt-get install -y openssh-server\n"
            cmd += "    mkdir /var/run/sshd\n"
            cmd += "fi\n"
            cmd += "sed -ri 's/^PermitRootLogin\s+.*/PermitRootLogin yes/' /etc/ssh/sshd_config\n"
            cmd += "fi\n"

            cmd +="/usr/sbin/sshd -f /etc/ssh/sshd_config -D\n"

        cmd += "ret_code=$?\n"
        cmd += "echo $startprocess > /mnt/go-docker/god.info\n"
        cmd += "date +%s >> /mnt/go-docker/god.info\n"
        cmd += "chown -R "+user_id+":"+user_id+" /mnt/go-docker/*\n"
        cmd += str(self.store.get_post_command())+"\n"
        cmd += "exit $ret_code\n"

        wrapper = "#!/bin/sh\n"
        wrapper += "if hash bash 2>/dev/null; then\n"
        wrapper += "    echo OK\n"
        wrapper += "else\n"
        wrapper += "    if hash apk 2>/dev/null; then\n"
        wrapper += "        apk --update add bash\n"
        wrapper += "        apk --update --repository http://dl-4.alpinelinux.org/alpine/edge/testing add shadow\n"
        wrapper += "        echo \"auth       sufficient pam_rootok.so\" > /etc/pam.d/su\n"
        wrapper += "        if [ ! -e /home/" + user_id + " ]; then"
        wrapper += "            mkdir -p /home/" + user_id + "\n"
        wrapper += "        fi\n"
        wrapper += "    fi\n"
        wrapper += "fi\n"

        if is_array_child_task(task):
            script_file = self.store.add_file(parent_task, 'godocker.sh', cmd, str(task['requirements']['array']['task_id']))
            os.chmod(script_file, 0o755)
            wrapper += os.path.join('/mnt/go-docker',os.path.basename(script_file))
            wrapper_file = self.store.add_file(parent_task, 'wrapper.sh', wrapper, str(task['requirements']['array']['task_id']))
            os.chmod(wrapper_file, 0o755)
            task['command']['script'] = os.path.join('/mnt/go-docker',os.path.basename(wrapper_file))
        else:
            script_file = self.store.add_file(task, 'godocker.sh', cmd)
            os.chmod(script_file, 0o755)
            wrapper += os.path.join('/mnt/go-docker',os.path.basename(script_file))
            wrapper_file = self.store.add_file(task, 'wrapper.sh', wrapper)
            os.chmod(wrapper_file, 0o755)
            task['command']['script'] = os.path.join('/mnt/go-docker',os.path.basename(wrapper_file))

    def run_tasks(self, queued_list):
        '''
        Execute tasks on Docker scheduler in order
        '''
        users_usage = {}
        projects_usage = {}
        filtered_list = []
        for task in queued_list:
            can_run = True
            for watcher in self.watchers:
                if not watcher.can_start(task) :
                    can_run = False
                    break
            if 'tasks' in task['requirements'] and task['requirements']['tasks']:
                for parent_task_id in task['requirements']['tasks']:
                    parent_task = self.db_jobsover.find_one({'id': int(parent_task_id)})
                    if parent_task is None:
                        can_run = False
                        break

            if not can_run:
                continue

            reject =  False
            quota = True
            if 'disk_default_quota' not in self.cfg or self.cfg['disk_default_quota'] is None:
                quota = False
            if quota:
                user = self.db_users.find_one({'id': task['user']['id']})
                if 'disk' in user['usage'] and user['usage']['disk'] > godutils.convert_size_to_int(self.cfg['disk_default_quota']):
                    reject = True
                    self.reject_quota(task)
                    continue
            if task['requirements']['user_quota_time'] > 0 or task['requirements']['user_quota_cpu'] > 0 or task['requirements']['user_quota_ram'] > 0:
                user_usage = None
                if task['user']['id'] not in users_usage:
                    user_usage = self.scheduler.get_user_usage(task['user']['id'], 'user')
                else:
                    user_usage = users_usage[task['user']['id']]
                if (not reject) and (task['requirements']['user_quota_time'] > 0 and task['requirements']['user_quota_time'] < user_usage['total_time']):
                    reject = True
                if (not reject) and (task['requirements']['user_quota_cpu'] > 0 and task['requirements']['user_quota_cpu'] < user_usage['total_cpu']+task['requirements']['cpu']):
                    reject = True
                if (not reject) and (task['requirements']['user_quota_ram'] > 0 and task['requirements']['user_quota_ram'] < user_usage['total_ram']+task['requirements']['ram']):
                    reject = True
            if (not reject) and task['user']['project'] != 'default' and (task['requirements']['project_quota_time'] > 0 or task['requirements']['project_quota_cpu'] > 0 or task['requirements']['project_quota_ram'] > 0):
                project_usage = None
                if task['user']['project'] not in projects_usage:
                    project_usage = self.scheduler.get_user_usage(task['user']['project'], 'group')
                else:
                    project_usage = users_usage[task['user']['project']]
                if (not reject) and (task['requirements']['project_quota_time'] > 0 and task['requirements']['project_quota_time'] < project_usage['total_time']):
                    reject = True
                if (not reject) and (task['requirements']['project_quota_cpu'] > 0 and task['requirements']['project_quota_cpu'] < project_usage['total_cpu']+task['requirements']['cpu']):
                    reject = True
                if (not reject) and (task['requirements']['project_quota_ram'] > 0 and task['requirements']['project_quota_ram'] < project_usage['total_ram']+task['requirements']['ram']):
                    reject = True
            if reject:
                self.reject_quota(task)
            else:
                # Create run script
                if 'use_private_registry' in self.cfg and self.cfg['use_private_registry'] is not None:
                    task['container']['image'] = self.cfg['use_private_registry'] + '/' + task['container']['image']
                try:
                    self._create_command(task)
                except Exception as e:
                    logging.error("Failed to create cmd: "+str(e))
                    continue
                filtered_list.append(task)

        dt = datetime.datetime.now()
        start_time = time.mktime(dt.timetuple())
        (running_tasks, rejected_tasks) = self.executor.run_tasks(filtered_list, self._update_scheduled_task_status)
        dt = datetime.datetime.now()
        end_time = time.mktime(dt.timetuple())
        self._prometheus_stats('god_scheduler_run_duration', end_time - start_time)
        self._update_scheduled_task_status(running_tasks, rejected_tasks)

    def reject_quota(self, task):
        '''
        Reject a task because user or project reached quota limits
        '''
        remove_result = self.db_jobs.remove({'id': task['id']})
        if remove_result['n'] == 0:
            # Not present anymore, may have been removed already
            # Remove from jobs over to replace it
            self.db_jobsover.remove({'id': task['id']})
        task['status']['primary'] = godutils.STATUS_OVER
        task['status']['secondary'] = godutils.STATUS_SECONDARY_QUOTA_REACHED
        dt = datetime.datetime.now()
        task['status']['date_over'] = time.mktime(dt.timetuple())
        del task['_id']
        self.db_jobsover.insert(task)
        self.r.delete(self.cfg['redis_prefix']+':job:'+str(task['id'])+':task')

    def reschedule_tasks(self, resched_list):
        '''
        Restart/reschedule running tasks in list
        '''
        for task in resched_list:
            self.db_jobs.update({'id': task['id']},
                {'$set': {
                        'status.secondary': godutils.STATUS_SECONDARY_RESCHEDULE_REQUESTED
                        }
            })
            self.r.rpush(self.cfg['redis_prefix']+':jobs:kill',dumps(task))


    def _prometheus_stats(self, stat, duration):
        if 'prometheus_key' in self.cfg and self.cfg['prometheus_exporter'] is not None and self.cfg['prometheus_key'] is not None:
            try:
                http = urllib3.PoolManager()
                r = http.request('POST',
                    self.cfg['prometheus_exporter']+'/api/1.0/prometheus',
                    headers={'Content-Type':'application/json'},
                    body=json.dumps({ 'key': self.cfg['prometheus_key'],
                                      'stat': [{'name': stat, 'value': duration}]}))
                if r.status != 200:
                    logging.warn('Prometheus:Failed to send stats')
            except Exception as e:
                logging.warn("Prometheus:Failed to send stats: "+str(e))

    def _add_to_stats(self, nb_pending, nb_running, duration_scheduler):
        '''
        Add scheduler stats
        '''

        if self.db_influx is None:
            return

        #dt = datetime.datetime.now()
        #current_timestamp = time.mktime(dt.timetuple())
        data = [{
            'points': [[
                nb_pending,
                nb_running,
                duration_scheduler
            ]],
            'name':'god_scheduler',
            'columns': ["nb_pending", "nb_running", "duration_scheduler"]
        }]
        try:
            self.db_influx.write_points(data)
        except Exception as e:
            # Do not fail on stat writing
            self.logger.error('Stat:Error:'+str(e))


    def manage_tasks(self):
        '''
        Schedule and run tasks

        '''

        self.logger.debug("Get pending task")
        #pending_tasks = []
        #pending_tasks_length = self.r.llen('jobs:pending')
        #for i in range(min(pending_tasks_length, self.cfg['max_job_pop'])):
        #    pending_tasks.append(self.r.lpop('jobs:pending'))

        pending_tasks = self.db_jobs.find({'status.primary': godutils.STATUS_PENDING})
        task_list = []
        for p in pending_tasks:
            if self.stop_daemon:
                self.executor.close()
                return
            if not self.auth_policy.can_run(p):
                self.db_jobs.update({'id': p['id']}, {'status.primary': godutils.STATUS_OVER,
                                                     'status.secondary': STATUS_SECONDARY_SCHEDULER_REJECTED,
                                                     'status.reason': 'Not authorized'})
                continue
            task_list.append(p)
        queued_tasks = self.schedule_tasks(task_list)
        if queued_tasks:
            self.run_tasks(queued_tasks)

        self.logger.debug('Get tasks to reschedule')
        if self.stop_daemon:
            return
        reschedule_task_list = []
        reschedule_task_length = self.r.llen(self.cfg['redis_prefix']+':jobs:reschedule')
        for i in range(min(reschedule_task_length, self.cfg['max_job_pop'])):
            task = self.r.lpop(self.cfg['redis_prefix']+':jobs:reschedule')
            if task:
                reschedule_task_list.append(json.loads(task))
        self.reschedule_tasks(reschedule_task_list)

    def signal_handler(self, signum, frame):
        GoDScheduler.SIGINT = True
        self.logger.warn('User request to exit')
        self.executor.close()

    def update_status(self):
        if self.status_manager is None:
            return
        if self.status_manager is not None:
            res = self.status_manager.keep_alive(self.proc_name, 'scheduler')
            if not res:
                self.logger.error('Watcher:UpdateStatus:Error')
        return

    def _in_maintenance(self):
        '''
        checks if system is in maintenance
        '''
        maintenance = self.r.get(self.cfg['redis_prefix']+':maintenance')
        if maintenance is not None and maintenance == 'on':
            return True
        return False


    def is_master(self, random_key):
        timeout = 600
        try:
            if 'master_timeout' in self.cfg and int(self.cfg['master_timeout']) > 0:
                timeout = int(self.cfg['master_timeout'])
        except Exception as e:
            self.logger.error('invalid master_timeout config parameter')
        self.r.setnx(self.cfg['redis_prefix']+':master', random_key)
        master_key = self.r.get(self.cfg['redis_prefix']+':master')
        if master_key == random_key:
            self.r.expire(self.cfg['redis_prefix']+':master', 600)
            return True
        else:
            return False

    def run(self, loop=True):
        '''
        Main executor loop

        '''
        self.hostname = None
        infinite = True
        is_master = False
        was_master = is_master
        random_key = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(10))
        is_master = self.is_master(random_key)
        while not is_master:
            if is_master != was_master:
                self.logger.debug('Switching status: master='+str(is_master))
            self.logger.debug('Not master, waiting...')
            time.sleep(2)
            is_master = self.is_master(random_key)

        self.executor.open(0)
        self.logger.warn('Start scheduler')

        try:
            while infinite and True and not GoDScheduler.SIGINT:
                # Schedule timer
                if not self._in_maintenance():
                    self.update_status()
                    self.manage_tasks()
                else:
                    self.logger.debug('In maintenance, waiting...')

                time.sleep(2)
                if not loop:
                    infinite = False
        except Exception as e:
            self.logger.error('Scheduler:'+str(self.hostname)+':'+str(e))
            traceback_msg = traceback.format_exc()
            self.logger.error(traceback_msg)
        self.executor.close()
        if is_master:
            self.r.delete(self.cfg['redis_prefix']+':master')
