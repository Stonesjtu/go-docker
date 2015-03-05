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

#from mock import patch

from optparse import OptionParser

from godocker.godscheduler import GoDScheduler
from godocker.godwatcher import GoDWatcher

import unittest

class SchedulerTest(unittest.TestCase):
    '''
    Copy properties files to a temp directory and update properties to
    use a temp directory
    '''

    def setUp(self):
        curdir = os.path.dirname(os.path.abspath(__file__))
        self.cfg =os.path.join(curdir,'go-d.ini')
        self.test_dir = tempfile.mkdtemp('god')
        self.scheduler = GoDScheduler(os.path.join(self.test_dir,'godsched.pid'))
        self.scheduler.load_config(self.cfg)
        self.scheduler.init()
        self.watcher = GoDWatcher(os.path.join(self.test_dir,'godwatcher.pid'))
        self.watcher.load_config(self.cfg)
        self.watcher.init()
        self.sample_task = {
            'id': None,
            'user': {
                'id': 'osallou',
                'uid': 1001,
                'gid': 1001
            },
            'date': datetime.datetime.now().isoformat(),
            'meta': {
                'name': 'samplejob',
                'description': 'blabla'
            },
            'requirements': {
                'cpu': 1,
                'ram': 1
            },
            'container': {
                'image': 'centos:latest',
                'volumes': [],
                'network': True,
                'id': None,
                'meta': None,
                'stats': None,
                'ports': []
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
        self.scheduler.r.flushdb()

    def tearDown(self):
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
        queued_tasks = self.scheduler.schedule_tasks(pending_tasks)
        self.assertTrue(queued_tasks.count() == 1)
        return queued_tasks

    def test_run_task(self):
        queued_tasks = self.test_schedule_task()
        self.scheduler.run_tasks(queued_tasks)
        running_tasks = self.scheduler.db_jobs.find({'status.primary': 'running'})
        self.assertTrue(running_tasks.count() == 1)

    def test_watch_task_over(self):
        self.test_run_task()
        self.watcher.check_running_jobs()
        over_tasks = self.watcher.db_jobsover.find()
        self.assertTrue(over_tasks.count() == 1)
