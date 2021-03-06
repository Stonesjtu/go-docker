from nose.tools import *
from nose.plugins.attrib import attr

import json
import shutil
import os
import tempfile
import logging
import copy
import stat
import datetime
from datetime import date, timedelta
import time
import string
import random
from bson.json_util import dumps


#from mock import patch

from optparse import OptionParser

import godocker.utils as godutils
from godocker.godscheduler import GoDScheduler
from godocker.godwatcher import GoDWatcher
from godocker.pairtreeStorage import PairtreeStorage

import unittest

class FairShareSchedulerTest(unittest.TestCase):
    '''
    Copy properties files to a temp directory and update properties to
    use a temp directory
    '''

    def set_user_usage(self, identifier):
        dt = datetime.datetime.now()

        total_time = 0.0
        total_cpu = 0
        total_ram = 0

        for i in range(0, 1):
            previous = dt - timedelta(days=i)
            date_key = str(previous.year)+'_'+str(previous.month)+'_'+str(previous.day)
            self.scheduler.r.set(self.scheduler.cfg['redis_prefix']+':user:'+identifier+':cpu:'+date_key, 1)
            self.scheduler.r.set(self.scheduler.cfg['redis_prefix']+':user:'+identifier+':ram:'+date_key, 1)
            self.scheduler.r.set(self.scheduler.cfg['redis_prefix']+':user:'+identifier+':time:'+date_key, 1)

    def add_project(self, prio):
            self.scheduler.r.delete(self.scheduler.cfg['redis_prefix']+':project:test:prio')
            self.scheduler.db.drop_collection('projects')
            project = {
                'id': 'test',
                'prio': prio
            }
            self.scheduler.db_projects.insert(project)

    def add_users(self, prio1, prio2):
            self.scheduler.r.delete(self.scheduler.cfg['redis_prefix']+':user:user1:prio')
            self.scheduler.r.delete(self.scheduler.cfg['redis_prefix']+':user:user2:prio')
            self.scheduler.db.drop_collection('users')
            user1 = {
                'id': 'user1',
                'last': datetime.datetime.now(),
                'apikey': '1234',
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
                    'prio': prio1
                }
            }
            self.scheduler.db_users.insert(user1)
            user2 = {
                'id': 'user2',
                'last': datetime.datetime.now(),
                'apikey': '1234',
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
                    'prio': prio2
                }
            }
            self.scheduler.db_users.insert(user2)

    def setUp(self):
        # pairtree cleanup
        dirname, filename = os.path.split(os.path.abspath(__file__))
        shared_dir = tempfile.mkdtemp('godshared')
        # shared_dir = os.path.join(dirname, '..', 'godshared')
        os.environ['GODOCKER_SHARED_DIR'] = shared_dir
        if os.path.exists(os.path.join(shared_dir,'tasks')):
            shutil.rmtree(os.path.join(shared_dir,'tasks'))

        curdir = os.path.dirname(os.path.abspath(__file__))
        self.cfg = os.path.join(curdir,'fairshare.ini')
        self.test_dir = tempfile.mkdtemp('god')
        self.scheduler = GoDScheduler(os.path.join(self.test_dir,'godsched.pid'))
        self.scheduler.load_config(self.cfg)
        self.scheduler.stop_daemon = False
        self.scheduler.init()
        self.watcher = GoDWatcher(os.path.join(self.test_dir,'godwatcher.pid'))
        self.watcher.load_config(self.cfg)
        self.watcher.stop_daemon = False
        dt = datetime.datetime.now()
        self.sample_user = {
            'id': 'osallou',
            'last': datetime.datetime.now(),
            'apikey': '1234',
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
        self.sample_task = {
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
        self.scheduler.db.drop_collection('jobs')
        self.scheduler.db.drop_collection('jobsover')
        self.scheduler.db.drop_collection('users')
        self.scheduler.db_users.insert(self.sample_user)
        self.scheduler.r.flushdb()

        self.scheduler.cfg['shared_dir'] = tempfile.mkdtemp('godshared')
        self.scheduler.store = PairtreeStorage(self.scheduler.cfg)

    def tearDown(self):
        if os.path.exists(self.scheduler.cfg['shared_dir']):
            shutil.rmtree(self.scheduler.cfg['shared_dir'])
        pass

    def test_task_create(self):
        task = copy.deepcopy(self.sample_task)
        task_id = self.scheduler.add_task(task)
        self.assertTrue(task_id > 0)
        new_task = self.scheduler.db_jobs.find_one({'id': task_id})
        self.assertTrue(new_task is not None)
        self.assertTrue(new_task['status']['primary'] == 'pending')
        return task_id

    def test_schedule_task(self):
        task_id = self.test_task_create()
        pending_tasks = self.scheduler.db_jobs.find({'status.primary': 'pending'})
        task_list = []
        for p in pending_tasks:
            task_list.append(p)
        queued_tasks = self.scheduler.schedule_tasks(task_list)
        self.assertTrue(len(queued_tasks) == 1)
        return queued_tasks

    def test_scheduler_methods(self):
        dt = datetime.datetime.now()
        key = 'user'

        self.scheduler.scheduler.load()
        usages = []
        for u in range (0,3):
            identifier = 'sample'+str(u)
            for i in range(0, 10):
                previous = dt - timedelta(days=i)
                date_key = str(previous.year)+'_'+str(previous.month)+'_'+str(previous.day)
                self.scheduler.r.set(self.scheduler.cfg['redis_prefix']+':'+key+':'+identifier+':cpu:'+date_key, random.randint(1,12))
                self.scheduler.r.set(self.scheduler.cfg['redis_prefix']+':'+key+':'+identifier+':ram:'+date_key, random.randint(8,20))
                self.scheduler.r.set(self.scheduler.cfg['redis_prefix']+':'+key+':'+identifier+':time:'+date_key, random.random()*10)

            usage = self.scheduler.scheduler.get_user_usage(identifier, key)
            usages.append(usage)
        bounds = self.scheduler.scheduler.get_bounds_usage(usages)
        self.assertTrue(bounds['max_cpu'] >= bounds['min_cpu'])
        self.assertTrue(bounds['max_ram'] >= bounds['min_ram'])
        self.assertTrue(bounds['max_time'] >= bounds['min_time'])

    def test_schedule_shares(self):
        dt = datetime.datetime.now()
        key = 'user'
        for u in range (0,3):
            identifier = 'sample'+str(u)
            for i in range(0, 10):
                previous = dt - timedelta(days=i)
                date_key = str(previous.year)+'_'+str(previous.month)+'_'+str(previous.day)
                self.scheduler.r.set(self.scheduler.cfg['redis_prefix']+':'+key+':'+identifier+':cpu:'+date_key, random.randint(1,12))
                self.scheduler.r.set(self.scheduler.cfg['redis_prefix']+':'+key+':'+identifier+':ram:'+date_key, random.randint(8,20))
                self.scheduler.r.set(self.scheduler.cfg['redis_prefix']+':'+key+':'+identifier+':time:'+date_key, random.random()*10)
        self.sample_task['user']['id'] = 'sample0'
        task_id = self.test_task_create()
        self.sample_task['user']['id'] = 'sample1'
        task_id = self.test_task_create()
        self.sample_task['user']['id'] = 'sample2'
        task_id = self.test_task_create()
        pending_tasks = self.scheduler.db_jobs.find({'status.primary': 'pending'})
        task_list = []
        for p in pending_tasks:
            task_list.append(p)
        queued_tasks = self.scheduler.schedule_tasks(task_list)
        self.assertTrue(len(queued_tasks) == 3)
        return queued_tasks


    def test_schedule_equal(self):
        self.add_users(50, 50)
        task = copy.deepcopy(self.sample_task)
        task['user']['id'] = 'user1'
        task_id = self.scheduler.add_task(task)
        task2 = copy.deepcopy(self.sample_task)
        task2['user']['id'] = 'user2'
        task2_id = self.scheduler.add_task(task2)
        pending_tasks = self.scheduler.db_jobs.find({'status.primary': godutils.STATUS_PENDING})
        task_list = []
        for p in pending_tasks:
            task_list.append(p)
        queued_tasks = self.scheduler.schedule_tasks(task_list)
        self.assertTrue(queued_tasks[0]['id'] == task_id)

    def test_schedule_user_prio(self):
        self.add_users(50, 60)
        task = copy.deepcopy(self.sample_task)
        task['user']['id'] = 'user1'
        task_id = self.scheduler.add_task(task)
        task2 = copy.deepcopy(self.sample_task)
        task2['user']['id'] = 'user2'
        task2_id = self.scheduler.add_task(task2)
        pending_tasks = self.scheduler.db_jobs.find({'status.primary': godutils.STATUS_PENDING})
        task_list = []
        for p in pending_tasks:
            task_list.append(p)
        queued_tasks = self.scheduler.schedule_tasks(task_list)
        self.assertTrue(queued_tasks[0]['id'] == task2_id)

    def test_schedule_project_prio(self):
        self.add_users(50, 60)
        self.add_project(80)
        task = copy.deepcopy(self.sample_task)
        task['user']['id'] = 'user1'
        task_id = self.scheduler.add_task(task)
        task2 = copy.deepcopy(self.sample_task)
        task2['user']['id'] = 'user2'
        task2['user']['project'] = 'test'
        task2_id = self.scheduler.add_task(task2)
        pending_tasks = self.scheduler.db_jobs.find({'status.primary': godutils.STATUS_PENDING})
        task_list = []
        for p in pending_tasks:
            task_list.append(p)
        queued_tasks = self.scheduler.schedule_tasks(task_list)
        self.assertTrue(queued_tasks[0]['id'] == task2_id)

    def test_schedule_project_prio_inverse(self):
        self.add_users(50, 60)
        self.add_project(20)
        task = copy.deepcopy(self.sample_task)
        task['user']['id'] = 'user1'
        task_id = self.scheduler.add_task(task)
        task2 = copy.deepcopy(self.sample_task)
        task2['user']['id'] = 'user2'
        task2['user']['project'] = 'test'
        task2_id = self.scheduler.add_task(task2)
        pending_tasks = self.scheduler.db_jobs.find({'status.primary': godutils.STATUS_PENDING})
        task_list = []
        for p in pending_tasks:
            task_list.append(p)
        queued_tasks = self.scheduler.schedule_tasks(task_list)
        self.assertTrue(queued_tasks[0]['id'] == task_id)

    def test_schedule_user_usage(self):
        self.add_users(50, 50)
        task = copy.deepcopy(self.sample_task)
        task['user']['id'] = 'user1'
        task_id = self.scheduler.add_task(task)
        task2 = copy.deepcopy(self.sample_task)
        task2['user']['id'] = 'user2'
        task2['user']['project'] = 'test'
        task2_id = self.scheduler.add_task(task2)
        pending_tasks = self.scheduler.db_jobs.find({'status.primary': godutils.STATUS_PENDING})
        task_list = []
        for p in pending_tasks:
            task_list.append(p)
        self.set_user_usage('user1')
        queued_tasks = self.scheduler.schedule_tasks(task_list)
        self.assertTrue(queued_tasks[0]['id'] == task2_id)
