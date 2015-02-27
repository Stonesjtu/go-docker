import redis
import json
import datetime
import logging

r = redis.StrictRedis(host='localhost', port=6379, db=0)

tasks = []
for i in range(10):
    task = {
        'id': i,
        'user': 'osallou',
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
            'id': 'centos:latest'
        }
        'command': {
            'cmd': 'ls -l'
        }
    }
    tasks.append(task)
    logging.debug('add '+str(task))
    r.rpush('jobs:pending', json.dumps(task))

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
    r.set('user:'+user['id'], json.dumps(user['quota']))
    r.set('user:'+user['id']+':usage:time', user['usage']['time'])
    r.set('user:'+user['id']+':usage:cpu', user['usage']['cpu'])
    r.set('user:'+user['id']+':usage:ram', user['usage']['ram'])
