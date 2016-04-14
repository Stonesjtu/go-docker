import json
import shutil
import os
import sys
import tempfile
import logging
import copy
import stat
import datetime
import time
import string
import random
import yaml
import argparse
from bson.json_util import dumps

#from mock import patch

from optparse import OptionParser

from godocker.godscheduler import GoDScheduler
from godocker.godwatcher import GoDWatcher
from godocker.pairtreeStorage import PairtreeStorage
from godocker.storageManager import StorageManager
import godocker.utils as godutils

def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('-c', '--config', dest="config", help="Configuration file")
    parser.add_argument('-u', '--users', dest="users", help="number of users (default 10)")
    parser.add_argument('-n', '--nb', dest="nb", help="number of jobs to execute at each run (default 100)")
    parser.add_argument('-l', '--loop', dest="loop", help="number of run (default 10)")
    parser.add_argument('-r', '--remove', dest="remove", help="Clean database at startup", action='store_true')

    args = parser.parse_args()

    config_file = 'go-d-test.ini'
    if args.config:
        config_file = args.config
    if not os.path.exists(config_file):
        logging.error("Configuration file not found")
        sys.exit(1)
    cfg= None
    with open(config_file, 'r') as ymlfile:
        cfg = yaml.load(ymlfile)


    if cfg['log_config'] is not None:
        for handler in list(cfg['log_config']['handlers'].keys()):
            cfg['log_config']['handlers'][handler] = dict(cfg['log_config']['handlers'][handler])
        logging.config.dictConfig(cfg['log_config'])
    logger = logging.getLogger('root')


    if cfg['auth_policy'] != 'local':
        logger.error('Only local auth policy is authorized')
        sys.exit(1)

    if cfg['executor'] != 'fake':
        logger.error('Only lfake executor is authorized')
        sys.exit(1)


    curdir = os.path.dirname(os.path.abspath(__file__))
    test_dir = tempfile.mkdtemp('god')
    scheduler = GoDScheduler(os.path.join(test_dir,'godsched.pid'))
    scheduler.load_config(config_file)
    scheduler.stop_daemon = False
    scheduler.init()
    watcher = GoDWatcher(os.path.join(test_dir,'godwatcher.pid'))
    watcher.load_config(config_file)
    watcher.stop_daemon = False

    scheduler.cfg['shared_dir'] = tempfile.mkdtemp('godshared')
    watcher.cfg['shared_dir'] = scheduler.cfg['shared_dir']
    cfg['shared_dir'] = scheduler.cfg['shared_dir']
    scheduler.store = StorageManager.get_storage(scheduler.cfg)

    db_users = scheduler.db_users.find().count()
    db_jobs = scheduler.db_jobs.find().count()

    if (db_users > 0 or db_jobs > 0) and not args.remove:
        logger.error('database is not empty, use --remove if you want to clean it')
        sys.exit(1)

    if args.remove:
        logging.info("Reset mongodb test database")
        scheduler.db.drop_collection('jobs')
        scheduler.db.drop_collection('jobsover')
        scheduler.db.drop_collection('users')
        scheduler.db.drop_collection('projects')

    sample_user = {
                'id': 'test',
                'last': datetime.datetime.now(),
                'apikey': '1234',
                'credentials': {
                    'apikey': ''.join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(10)),
                    'private': '',
                    'public': ''
                },
                'uidNumber': 1001,
                'gidNumber': 1001,
                'homeDirectory': '/home/osallou',
                'email': 'fakeemail@no.mail',
                'usage':
                {
                    'prio': 50
                }
            }

    nb_users = 10
    if args.users:
        nb_users = int(args.users)

    users = []
    for i in range(nb_users):
        user = copy.deepcopy(sample_user)
        user['id'] = user['id'] + str(i)
        user = scheduler.auth_policy.create_user(user['id'], 'test', user['email'], user['homeDirectory'], user['uidNumber'], user['gidNumber'], [])
        logger.debug('Created user: '+str(user))
        users.append(user)

    dt = datetime.datetime.now()

    sample_task = {
                'id': None,
                'parent_task_id': None,
                'user': {
                    'id': 'osallou',
                    'uid': 1001,
                    'gid': 1001,
                    'credentials': {
                        'apikey': '123',
                        'public': ''
                    },
                    'project': 'default'
                },
                'date': time.mktime(dt.timetuple()),
                'meta': {
                    'name': 'samplejob',
                    'description': 'blabla',
                    'tags': []
                },
                'requirements': {
                    'cpu': 1,
                    'ram': 1,
                    'array': {
                        # begin:end:step, example: 5:20:1
                        'values': None,
                        # task id value according to above definition
                        'task_id': None,
                        'nb_tasks': 0,
                        'nb_tasks_over': 0,
                        'tasks': []
                    },
                    'label': None,
                    'user_quota_time': 0,
                    'user_quota_cpu': 0,
                    'user_quota_ram': 0,
                    'project_quota_time': 0,
                    'project_quota_cpu': 0,
                    'project_quota_ram': 0
                },
                'container': {
                    'image': 'centos:latest',
                    'volumes': [],
                    'network': True,
                    'id': None,
                    'meta': None,
                    'stats': None,
                    'ports': [],
                    'root': False
                },
                'command': {
                    'interactive': False,
                    'cmd': '/bin/ls -l'
                },
                'status': {
                    'primary': None,
                    'secondary': None
                }
            }

    nb_jobs = 100
    if args.nb:
        nb_jobs = int(args.nb)

    scheduler.executor.fail_on = nb_jobs + 1

    nb_loop = 10
    if args.loop:
        nb_loop = int(args.loop)

    stats = []

    global_dt = datetime.datetime.now()
    for l in range(nb_loop):
        stat = {}
        loop_dt = datetime.datetime.now()
        for t in range(nb_jobs):
            # Create tasks
            task = copy.deepcopy(sample_task)
            user = random.choice(users)
            task['user']['id'] = user['id']
            task['user']['uid'] = user['uid']
            task['user']['gid'] = user['gid']
            task_id = scheduler.add_task(task)
        # Schedule tasks
        pending_tasks = scheduler.db_jobs.find({'status.primary': 'pending'})
        task_list = []
        for p in pending_tasks:
            task_list.append(p)
        schedule_dt = datetime.datetime.now()
        queued_tasks = scheduler.schedule_tasks(task_list)
        schedule_time = datetime.datetime.now() - schedule_dt
        stat['schedule_time'] =  schedule_time
        # Run tasks in fake env
        scheduler.run_tasks(queued_tasks)
        watch_dt = datetime.datetime.now()
        running_tasks = scheduler.db_jobs.find({'status.primary': 'running'}).count()
        while running_tasks > 0:
            watcher.check_running_jobs()
            running_tasks = scheduler.db_jobs.find({'status.primary': 'running'}).count()
            logger.info("Nb tasks running: "+str(running_tasks))
        watch_time = datetime.datetime.now() - watch_dt
        stat['watch_time'] =  watch_time

        logger.info(stat)
        stats.append(stat)

    logging.info("Cleanup mongodb test database")
    scheduler.db.drop_collection('jobs')
    scheduler.db.drop_collection('jobsover')
    scheduler.db.drop_collection('users')
    scheduler.db.drop_collection('projects')
    return stats

if __name__ == '__main__':
    stats = main()
    logging.warn(stats)
