import redis
from pymongo import MongoClient

import os
import json
import datetime
import time
import logging
from config import Config

config_file = 'go-d.ini'
if 'GOD_CONFIG' in os.environ:
    config_file = os.environ['GOD_CONFIG']
cfg = Config(config_file)

mongo = MongoClient(cfg.mongo_url)
db = mongo.god
db_jobs = db.jobs
db_users = db.users

r = redis.StrictRedis(host=cfg.redis_host, port=cfg.redis_port, db=cfg.redis_db)

tasks = []
interactive = False
for i in range(10):
    dt = datetime.datetime.now()
    task_id = r.incr(cfg.redis_prefix+':jobs')
    task = {
        'id': task_id,
        # id of the parent task
        'parent_task_id': None,
        'user': {
            'id': 'osallou',
            'uid': 1001,
            'gid': 1001,
            'sgids': []
            'project': 'default'
        },
        'date': time.mktime(dt.timetuple()),
        'meta': {
            'name': 'samplejob'+str(i),
            'description': 'blabla',
            'tags': []
        },
        'requirements': {
            'cpu': 1,
            # In Gb
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
            # List of task id the task depends on
            # Task will not start before the end of those tasks
            'tasks': []
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
            'interactive': interactive,
            #'cmd': '/bin/ls -l'
            'cmd': '/bin/sleep 30'
        },
        'status': {
            'primary': 'pending',
            'secondary': None
        }
    }
    tasks.append(task)
    logging.debug('add '+str(task))
    #r.rpush('jobs:pending', json.dumps(task))
    db_jobs.insert(task)
    interactive = not interactive

users = []

user = {
    'id': 'osallou',
    'last': datetime.datetime.now(),
    'credentials': {
        'apikey': ''.join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(10)),
        'private': '',
        'public': ''
    },
    'uidNumber': 1001,
    'uidNumber': 1001,
    'homeDirectory': '/home/osallou',
    'email': 'fakeemail@no.mail',
    'usage':
    {
        'prio': 50
    }
}

users.append(user)
for user in users:
    db_users.insert(user)
    #r.set('user:'+user['id'], json.dumps(user['quota']))
    #r.set('user:'+user['id']+':usage:time', user['usage']['time'])
    #r.set('user:'+user['id']+':usage:cpu', user['usage']['cpu'])
    #r.set('user:'+user['id']+':usage:ram', user['usage']['ram'])
