#import redis
from pymongo import MongoClient

import json
import datetime
import logging
from config import Config

#r = redis.StrictRedis(host='localhost', port=6379, db=0)
cfg = Config('go-d.ini')
mongo = MongoClient(cfg.mongo_url)
db = mongo.god
db_jobs = db.jobs
db_users = db.users

tasks = []
for i in range(10):
    task = {
        'id': i,
        'user': {
            'id': 'osallou',
            'uid': 1001,
            'gid': 1001
        },
        'date': datetime.datetime.now().isoformat(),
        'meta': {
            'name': 'samplejob'+str(i),
            'description': 'blabla'
        },
        'requirements': {
            'cpu': 1,
            # In Gb
            'ram': 1
        },
        'container': {
            'image': 'centos:latest',
            'volumes': [],
            'network': True,
            'id': None,
            'meta': None,
            'stats': None
        },
        'command': {
            'cmd': '/bin/ls -l'
            #'cmd': '/bin/sleep 30'
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

users = []

user = {
    'id': 'osallou',
    'quota': {
        'cpu': 100,
        'ram': 100,
        'time': -1
    },
    'usage':
    {
        'time': 0,
        'cpu': 0,
        'ram': 0
    }
}

users.append(user)
for user in users:
    db_users.insert(user)
    #r.set('user:'+user['id'], json.dumps(user['quota']))
    #r.set('user:'+user['id']+':usage:time', user['usage']['time'])
    #r.set('user:'+user['id']+':usage:cpu', user['usage']['cpu'])
    #r.set('user:'+user['id']+':usage:ram', user['usage']['ram'])
