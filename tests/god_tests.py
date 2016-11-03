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
import time
import string
import random
import yaml
from bson.json_util import dumps
from yapsy.PluginManager import PluginManager

#from mock import patch

from optparse import OptionParser

from godocker.godscheduler import GoDScheduler
from godocker.godwatcher import GoDWatcher
from godocker.godarchiver import GoDArchiver
from godocker.pairtreeStorage import PairtreeStorage
from godocker.storageManager import StorageManager
from godocker.iNetworkPlugin import INetworkPlugin
import godocker.utils as godutils


import unittest

class UtilsTest(unittest.TestCase):

    def test_convert_size_to_int(self):
        val = godutils.convert_size_to_int('10')
        self.assertEqual(val, 10)
        val = godutils.convert_size_to_int('10k')
        self.assertEqual(val, 10000)
        val = godutils.convert_size_to_int('10K')
        self.assertEqual(val, 10000)
        val = godutils.convert_size_to_int('20M')
        self.assertEqual(val, 20000000)
        val = godutils.convert_size_to_int('30g')
        self.assertEqual(val, 30000000000)
        val = godutils.convert_size_to_int('30T')
        self.assertEqual(val, 30000000000000)
        try:
            val = godutils.convert_size_to_int('giga')
            self.assertFalse(1==0)
        except ValueError:
            # An error should be raised
            self.assertTrue(1==1)
        try:
            val = godutils.convert_size_to_int('10s')
            self.assertFalse(1==0)
        except ValueError:
            # An error should be raised
            self.assertTrue(1==1)

class StorageTests(unittest.TestCase):

    def setUp(self):
        curdir = os.path.dirname(os.path.abspath(__file__))
        cfg_file =os.path.join(curdir,'go-d.ini')
        self.cfg= None
        with open(cfg_file, 'r') as ymlfile:
            self.cfg = yaml.load(ymlfile)

    def test_handler_default(self):
        from godocker.pairtreeStorage import PairtreeStorage
        handler = StorageManager.get_storage(self.cfg)
        self.assertTrue(isinstance(handler, PairtreeStorage))

    def test_handler_default(self):
        from godocker.pairtreeStorage import PairtreeStorage
        self.cfg['storage'] = 'fail'
        handler = StorageManager.get_storage(self.cfg)
        self.assertTrue(handler is None)

class PairtreeTests(unittest.TestCase):

    def setUp(self):
        curdir = os.path.dirname(os.path.abspath(__file__))
        cfg_file =os.path.join(curdir,'go-d.ini')
        self.cfg= None
        with open(cfg_file, 'r') as ymlfile:
            self.cfg = yaml.load(ymlfile)
        self.cfg['shared_dir'] = tempfile.mkdtemp('godshared')

    def test_storage_init(self):
        storage = PairtreeStorage(self.cfg)
        self.assertTrue(os.path.exists(os.path.join(self.cfg['shared_dir'],'tasks')))

    def test_manage_object(self):
        storage = PairtreeStorage(self.cfg)
        task = { 'id': 1234 }
        storage.add_file(task, "sample1.txt", "hello world")
        storage.add_file(task, "sample1.txt", "hello world","subtest")
        task_dir = storage.get_task_dir(task)
        self.assertTrue(os.path.exists(task_dir))
        self.assertTrue(os.path.exists(os.path.join(task_dir,'sample1.txt')))
        self.assertTrue(os.path.exists(os.path.join(task_dir,'subtest','sample1.txt')))
        storage.clean(task)
        self.assertFalse(os.path.exists(task_dir))


class CNINetworkTest(unittest.TestCase):
    '''
    network:
        use_cni: True
        # weave, calico, etc.: a plugin extending INetworkPlugin
        cni_plugin: 'calico'
        # Default name of the cni plugin network
        cni_public_network_name: 'calico-net-1'
    '''
    def setUp(self):
        # pairtree cleanup
        dirname, filename = os.path.split(os.path.abspath(__file__))
        shared_dir = tempfile.mkdtemp('godshared')
        if os.path.exists(os.path.join(shared_dir,'tasks')):
            shutil.rmtree(os.path.join(shared_dir,'tasks'))
        os.environ['GODOCKER_SHARED_DIR'] = shared_dir
        curdir = os.path.dirname(os.path.abspath(__file__))
        self.cfg =os.path.join(curdir,'go-d.ini')
        self.test_dir = tempfile.mkdtemp('god')

    def test_weave(self):
        self.scheduler = GoDScheduler(os.path.join(self.test_dir,'godsched.pid'))
        self.scheduler.load_config(self.cfg)
        self.scheduler.cfg['network'] = {
            'use_cni': True,
            'cni_plugin': 'weave',
            'cni_public_network_name': 'weave'
        }

        self.scheduler.stop_daemon = False
        self.scheduler.init()
        # Build the manager
        simplePluginManager = PluginManager()
        # Tell it the default place(s) where to find plugins
        simplePluginManager.setPluginPlaces([self.scheduler.cfg['plugins_dir']])
        simplePluginManager.setCategoriesFilter({
           "Network": INetworkPlugin
         })
        # Load all plugins
        simplePluginManager.collectPlugins()
        self.scheduler.network_plugin = None
        if 'network' in self.scheduler.cfg and self.scheduler.cfg['network']['use_cni']:
            for pluginInfo in simplePluginManager.getPluginsOfCategory("Network"):
                if pluginInfo.plugin_object.get_name() == self.scheduler.cfg['network']['cni_plugin']:
                    self.scheduler.network_plugin = pluginInfo.plugin_object
                    self.scheduler.network_plugin.set_config(self.scheduler.cfg)
        self.assertTrue('public' in self.scheduler.network_plugin.networks())
        self.assertTrue(self.scheduler.network_plugin.network('public') == 'weave')

    def test_calico(self):
        self.scheduler = GoDScheduler(os.path.join(self.test_dir,'godsched.pid'))
        self.scheduler.load_config(self.cfg)
        self.scheduler.cfg['network'] = {
            'use_cni': True,
            'cni_plugin': 'calico',
            'cni_public_network_name': 'calico-test'
        }

        self.scheduler.stop_daemon = False
        self.scheduler.init()
        # Build the manager
        simplePluginManager = PluginManager()
        # Tell it the default place(s) where to find plugins
        simplePluginManager.setPluginPlaces([self.scheduler.cfg['plugins_dir']])
        simplePluginManager.setCategoriesFilter({
           "Network": INetworkPlugin
         })
        # Load all plugins
        simplePluginManager.collectPlugins()
        self.scheduler.network_plugin = None
        if 'network' in self.scheduler.cfg and self.scheduler.cfg['network']['use_cni']:
            for pluginInfo in simplePluginManager.getPluginsOfCategory("Network"):
                if pluginInfo.plugin_object.get_name() == self.scheduler.cfg['network']['cni_plugin']:
                    self.scheduler.network_plugin = pluginInfo.plugin_object
                    self.scheduler.network_plugin.set_config(self.scheduler.cfg)
        self.assertTrue('public' in self.scheduler.network_plugin.networks())
        self.assertTrue(self.scheduler.network_plugin.network('public') == 'calico-test')


class SchedulerTest(unittest.TestCase):
    '''
    Copy properties files to a temp directory and update properties to
    use a temp directory
    '''

    def setUp(self):
        # pairtree cleanup
        dirname, filename = os.path.split(os.path.abspath(__file__))
        shared_dir = os.path.join(dirname, '..', 'godshared')
        if os.path.exists(os.path.join(shared_dir,'tasks')):
            shutil.rmtree(os.path.join(shared_dir,'tasks'))

        curdir = os.path.dirname(os.path.abspath(__file__))
        self.cfg =os.path.join(curdir,'go-d.ini')
        self.test_dir = tempfile.mkdtemp('god')
        god_shared = tempfile.mkdtemp('godshared')
        os.environ['GODOCKER_SHARED_DIR'] = god_shared

        self.scheduler = GoDScheduler(os.path.join(self.test_dir,'godsched.pid'))
        self.scheduler.load_config(self.cfg)
        self.scheduler.stop_daemon = False
        self.scheduler.init()
        self.watcher = GoDWatcher(os.path.join(self.test_dir,'godwatcher.pid'))
        self.watcher.load_config(self.cfg)
        self.watcher.stop_daemon = False
        self.archiver = GoDArchiver(os.path.join(self.test_dir,'godarchiverr.pid'))
        self.archiver.load_config(self.cfg)
        self.archiver.stop_daemon = False
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
            'gidNumber': 1001,
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
        self.scheduler.db.drop_collection('projects')
        self.scheduler.db_users.insert(self.sample_user)
        self.scheduler.r.flushdb()

        '''
        self.scheduler.cfg['shared_dir'] = tempfile.mkdtemp('godshared')
        self.watcher.cfg['shared_dir'] = self.scheduler.cfg['shared_dir']
        self.archiver.cfg['shared_dir'] = self.scheduler.cfg['shared_dir']
        '''
        #self.scheduler.store = PairtreeStorage(self.scheduler.cfg)
        self.scheduler.store = StorageManager.get_storage(self.scheduler.cfg)

    def tearDown(self):
        if os.path.exists(self.scheduler.cfg['shared_dir']):
            shutil.rmtree(self.scheduler.cfg['shared_dir'])
        pass

    def test_auth_volumes(self):
        self.scheduler.cfg['volumes'].append({
            'name': 'test',
             'acl': 'ro',
             'path': '/fakefalsedir'
        })
        vols = self.scheduler.auth_policy.get_volumes({'id': 'test'},[{'name': 'test'}])
        found = False
        for vol in vols:
            if vol['name'] == 'test':
                found = True
        self.assertFalse(found)
        self.scheduler.cfg['volumes'].append({
            'name': 'test2',
             'acl': 'ro',
             'path': '/tmp'
        })
        vols = self.scheduler.auth_policy.get_volumes({'id': 'test'},[{'name': 'test2'}])
        found = False
        for vol in vols:
            if vol['name'] == 'test2':
                found = True
        self.assertTrue(found)


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

    def test_run_task(self):
        queued_tasks = self.test_schedule_task()
        self.scheduler.run_tasks(queued_tasks)
        running_tasks = self.scheduler.db_jobs.find({'status.primary': 'running'})
        self.assertTrue(running_tasks.count() == 1)
        return running_tasks

    def test_run_task_watcher_reject(self):
        self.sample_task['meta']['name'] = 'norun'
        queued_tasks = self.test_schedule_task()
        self.scheduler.run_tasks(queued_tasks)
        running_tasks = self.scheduler.db_jobs.find({'status.primary': 'running'})
        self.assertTrue(running_tasks.count() == 0)
        pending_tasks = self.scheduler.db_jobs.find({'status.primary': 'pending'})
        self.assertTrue(pending_tasks.count() == 1)

    def test_check_redis_restore(self):
        running_tasks = self.test_run_task()
        nb_running_redis = self.scheduler.r.llen(self.watcher.cfg['redis_prefix']+':jobs:running')
        total_redis = int(self.scheduler.r.get(self.watcher.cfg['redis_prefix']+':jobs'))
        self.assertTrue(nb_running_redis > 0)
        self.scheduler.r.flushdb()
        self.assertTrue(self.scheduler.r.llen(self.watcher.cfg['redis_prefix']+':jobs:running') == 0)
        self.scheduler.check_redis()
        nb_running_redis_after_restore = self.scheduler.r.llen(self.watcher.cfg['redis_prefix']+':jobs:running')
        self.assertTrue(nb_running_redis == nb_running_redis_after_restore)
        total_redis_after_restore = int(self.scheduler.r.get(self.watcher.cfg['redis_prefix']+':jobs'))
        self.assertTrue(total_redis == total_redis_after_restore)

    @attr('test')
    def test_watch_task_over(self):
        self.test_run_task()
        self.watcher.check_running_jobs()
        over_tasks = self.watcher.db_jobsover.find()
        self.assertTrue(over_tasks.count() == 1)
        for task in over_tasks:
            self.assertTrue(task['container']['meta']['disk_size'] > 0)
        return over_tasks

    def test_archive(self):
        self.test_watch_task_over()
        over_tasks = self.watcher.db_jobsover.find()
        for task in over_tasks:
            self.archiver.archive_task(task)
        over_tasks = self.watcher.db_jobsover.find()
        for task in over_tasks:
            self.assertTrue(task['status']['primary'] == godutils.STATUS_ARCHIVED)

    def test_dependent_tasks(self):
        running = self.test_run_task()
        self.sample_task['requirements']['tasks'] = [running[0]['id']]
        running = self.test_run_task()
        # Parent is running, task should have been kept in pending
        self.assertTrue(running.count() == 1)
        # Finish parent job
        self.watcher.check_running_jobs()
        # Reschedule
        pending_tasks = self.scheduler.db_jobs.find({'status.primary': 'pending'})
        task_list = []
        for p in pending_tasks:
            task_list.append(p)
        queued_tasks = self.scheduler.schedule_tasks(task_list)
        self.scheduler.run_tasks(queued_tasks)
        running_tasks = self.scheduler.db_jobs.find({'status.primary': 'running'})
        self.assertTrue(running_tasks.count() == 1)

    def test_dependent_tasks_ids_are_str(self):
        running = self.test_run_task()
        self.sample_task['requirements']['tasks'] = [str(running[0]['id'])]
        running = self.test_run_task()
        # Parent is running, task should have been kept in pending
        self.assertTrue(running.count() == 1)
        # Finish parent job
        self.watcher.check_running_jobs()
        # Reschedule
        pending_tasks = self.scheduler.db_jobs.find({'status.primary': 'pending'})
        task_list = []
        for p in pending_tasks:
            task_list.append(p)
        queued_tasks = self.scheduler.schedule_tasks(task_list)
        self.scheduler.run_tasks(queued_tasks)
        running_tasks = self.scheduler.db_jobs.find({'status.primary': 'running'})
        self.assertTrue(running_tasks.count() == 1)

    def test_kill_task_running(self):
        running_tasks = self.test_run_task()
        task_to_kill = running_tasks[0]
        self.watcher.r.rpush(self.watcher.cfg['redis_prefix']+':jobs:kill', dumps(task_to_kill))
        self.watcher.kill_tasks([task_to_kill])
        running_tasks = self.scheduler.db_jobs.find({'status.primary': 'running'})
        self.assertTrue(running_tasks.count() == 0)
        over_tasks = self.scheduler.db_jobsover.find()
        self.assertTrue(over_tasks.count() == 1)

    def test_kill_task_pending(self):
        pending_tasks = self.test_schedule_task()
        task_to_kill = pending_tasks[0]
        self.watcher.r.rpush(self.watcher.cfg['redis_prefix']+':jobs:kill', dumps(task_to_kill))
        self.watcher.kill_tasks([task_to_kill])
        running_tasks = self.scheduler.db_jobs.find({'status.primary': 'running'})
        self.assertTrue(running_tasks.count() == 0)
        over_tasks = self.scheduler.db_jobsover.find()
        self.assertTrue(over_tasks.count() == 1)

    def test_reschedule(self):
        running_tasks = self.test_run_task()
        task_to_reschedule = running_tasks[0]
        pending_tasks = self.scheduler.db_jobs.find({'status.primary': 'pending'})
        self.assertTrue(pending_tasks.count() == 0)
        self.scheduler.reschedule_tasks([task_to_reschedule])
        self.watcher.kill_tasks([task_to_reschedule])
        pending_tasks = self.scheduler.db_jobs.find({'status.primary': 'pending'})
        self.assertTrue(pending_tasks.count() == 1)
        running_tasks = self.scheduler.db_jobs.find({'status.primary': 'running'})
        self.assertTrue(running_tasks.count() == 0)
        over_tasks = self.scheduler.db_jobsover.find()
        self.assertTrue(over_tasks.count() == 0)

    def test_suspend_task_running(self):
        running_tasks = self.test_run_task()
        task_to_suspend = running_tasks[0]
        self.watcher.r.rpush(self.watcher.cfg['redis_prefix']+':jobs:suspend', dumps(task_to_suspend))
        self.watcher.suspend_tasks([task_to_suspend])
        suspended_task = self.scheduler.db_jobs.find_one({'id': task_to_suspend['id']})
        self.assertTrue(suspended_task['status']['secondary'] == 'suspended')
        return suspended_task

    def test_suspend_task_pending(self):
        pending_tasks = self.test_schedule_task()
        task_to_suspend = pending_tasks[0]
        self.watcher.r.rpush(self.watcher.cfg['redis_prefix']+':jobs:suspend', dumps(task_to_suspend))
        self.watcher.suspend_tasks([task_to_suspend])
        suspended_task = self.scheduler.db_jobs.find_one({'id': task_to_suspend['id']})
        self.assertTrue(suspended_task['status']['secondary'] == 'suspend rejected')
        return task_to_suspend

    def test_resume_task_suspended(self):
        suspended_task = self.test_suspend_task_running()
        suspended_task['status']['secondary'] = 'resume requested'
        self.watcher.r.rpush(self.watcher.cfg['redis_prefix']+':jobs:resume', dumps(suspended_task))
        self.watcher.resume_tasks([suspended_task])
        resumed_task = self.scheduler.db_jobs.find_one({'id': suspended_task['id']})
        self.assertTrue(resumed_task['status']['secondary'] == 'resumed')
        return resumed_task

    def test_resume_task_pending(self):
        pending_tasks = self.test_schedule_task()
        task_to_resume = pending_tasks[0]
        self.watcher.r.rpush(self.watcher.cfg['redis_prefix']+':jobs:resume', dumps(task_to_resume))
        self.watcher.resume_tasks([task_to_resume])
        resumed_task = self.scheduler.db_jobs.find_one({'id': task_to_resume['id']})
        self.assertTrue(resumed_task['status']['secondary'] == 'resume rejected')


    def test_resume_task_running(self):
        running_tasks = self.test_run_task()
        task_to_resume = running_tasks[0]
        self.watcher.r.rpush(self.watcher.cfg['redis_prefix']+':jobs:resume', dumps(task_to_resume))
        self.watcher.resume_tasks([task_to_resume])
        resumed_task = self.scheduler.db_jobs.find_one({'id': task_to_resume['id']})
        self.assertTrue(resumed_task['status']['secondary'] == 'resume rejected')

    def test_rejected_task(self):
        queued_tasks = []
        # Queue 6 tasks
        for i in range(6):
            task_id = self.test_task_create()
            pending_task = self.scheduler.db_jobs.find_one({'id': task_id})
            queued_tasks.append(pending_task)
        # Run tasks
        self.scheduler.run_tasks(queued_tasks)
        running_tasks = self.scheduler.db_jobs.find({'status.primary': 'running'})
        self.assertTrue(running_tasks.count() == 5)
        # 1 task should have been rejected and set back as pending
        pending_tasks = self.scheduler.db_jobs.find({'status.primary': 'pending'})
        self.assertTrue(pending_tasks.count() == 1)

    def test_reschedule_rejected_task(self):
        self.test_rejected_task()
        # Now, we have 1 left in pending
        pending_tasks = self.scheduler.db_jobs.find({'status.primary': 'pending'})
        task_list = []
        for p in pending_tasks:
            task_list.append(p)
        queued_tasks = self.scheduler.schedule_tasks(task_list)
        self.scheduler.run_tasks(queued_tasks)
        pending_tasks = self.scheduler.db_jobs.find({'status.primary': 'pending'})
        self.assertTrue(pending_tasks.count() == 0)


    def test_run_interactive_task(self):
        task = copy.deepcopy(self.sample_task)
        task['command']['interactive'] = True
        task_id = self.scheduler.add_task(task)
        pending_task = self.scheduler.db_jobs.find_one({'id': task_id})
        queued_tasks = [pending_task]
        self.scheduler.run_tasks(queued_tasks)
        ports_allocated = self.scheduler.r.llen(self.scheduler.cfg['redis_prefix']+':ports:fake-laptop')
        self.assertTrue(ports_allocated >= 1)
        nb_ports_before = self.scheduler.r.llen(self.scheduler.cfg['redis_prefix']+':ports:fake-laptop')
        self.watcher.check_running_jobs()
        nb_ports_after = self.scheduler.r.llen(self.scheduler.cfg['redis_prefix']+':ports:fake-laptop')
        # Check port is released
        self.assertTrue(nb_ports_before + 1 == nb_ports_after)


    def test_task_array_create(self):
        task = copy.deepcopy(self.sample_task)
        task['requirements']['array']['values'] = '1:3:1'
        task_id = self.scheduler.add_task(task)
        self.assertTrue(task_id > 0)
        new_task = self.scheduler.db_jobs.find_one({'id': task_id})
        self.assertTrue(new_task is not None)
        self.assertTrue(new_task['status']['primary'] == 'pending')
        nb_tasks = self.scheduler.db_jobs.find().count()
        self.assertTrue(nb_tasks == 4)
        return (task_id, new_task['requirements']['array']['tasks'])

    def test_task_array_schedule(self):
        (task_id, subtasks) = self.test_task_array_create()
        pending_tasks = self.scheduler.db_jobs.find({'status.primary': 'pending'})
        task_list = []
        for p in pending_tasks:
            task_list.append(p)
        queued_tasks = self.scheduler.schedule_tasks(task_list)
        self.assertTrue(len(queued_tasks) == 4)
        return queued_tasks

    def test_run_task_array(self):
        queued_tasks = self.test_task_array_schedule()
        self.scheduler.run_tasks(queued_tasks)
        running_tasks = self.scheduler.db_jobs.find({'status.primary': 'running'})
        self.assertTrue(running_tasks.count() == 4)
        return running_tasks

    def test_watch_task_array_over(self):
        self.test_run_task_array()
        self.watcher.check_running_jobs()
        # May need a second pass, need to get all child tasks over first to get parent task over
        self.watcher.check_running_jobs()
        over_tasks = self.watcher.db_jobsover.find()
        #tasks = self.watcher.db_jobs.find()
        #for task in tasks:
        #    print(str(task))
        #print("###"+str(over_tasks.count()))
        self.assertTrue(over_tasks.count() == 4)

    def test_kill_task_running(self):
        running_tasks = self.test_run_task_array()
        task_to_kill = None
        subtasks_to_kill = []
        for running_task in running_tasks:
            if running_task['parent_task_id'] is None:
                task_to_kill = running_task
            else:
                subtasks_to_kill.append(running_task)
        self.watcher.r.rpush(self.watcher.cfg['redis_prefix']+':jobs:kill', dumps(task_to_kill))
        self.watcher.kill_tasks([task_to_kill])
        self.watcher.kill_tasks(subtasks_to_kill)
        self.watcher.kill_tasks([task_to_kill])
        running_tasks = self.scheduler.db_jobs.find({'status.primary': 'running'})
        self.assertTrue(running_tasks.count() == 0)
        over_tasks = self.scheduler.db_jobsover.find()
        self.assertTrue(over_tasks.count() == 4)

    def test_plugin_get_users(self):
        user_list = self.scheduler.executors[0].get_users(['osallou'])
        self.assertTrue(user_list.count()==1)


    def test_user_rate_limit(self):
        self.scheduler.cfg['rate_limit'] = 1
        task = copy.deepcopy(self.sample_task)
        task_id = self.scheduler.add_task(task)
        pending_tasks = self.scheduler.db_jobs.find({'status.primary': 'pending'})
        task_list = []
        for p in pending_tasks:
            task_list.append(p)
        queued_tasks = self.scheduler.schedule_tasks(task_list)
        task = copy.deepcopy(self.sample_task)
        task_id = self.scheduler.add_task(task)
        self.assertTrue(task_id is None)

    def test_global_rate_limit(self):
        self.scheduler.cfg['rate_limit_all'] = 1
        task = copy.deepcopy(self.sample_task)
        task_id = self.scheduler.add_task(task)
        pending_tasks = self.scheduler.db_jobs.find({'status.primary': 'pending'})
        task_list = []
        for p in pending_tasks:
            task_list.append(p)
        queued_tasks = self.scheduler.schedule_tasks(task_list)
        task = copy.deepcopy(self.sample_task)
        task_id = self.scheduler.add_task(task)
        self.assertTrue(task_id is None)

    def test_disk_quota(self):
        queued_tasks = self.test_schedule_task()
        self.scheduler.run_tasks(queued_tasks)
        running_tasks = self.scheduler.db_jobs.find({'status.primary': 'running'})
        self.assertTrue(running_tasks.count() == 1)
        self.watcher.check_running_jobs()
        self.scheduler.cfg['disk_default_quota'] = '10'
        queued_tasks = self.test_schedule_task()
        quota_job_id = queued_tasks[0]['id']
        self.scheduler.run_tasks(queued_tasks)
        over_quota_task = self.scheduler.db_jobsover.find_one({'id': quota_job_id})
        self.assertTrue(over_quota_task['status']['secondary'] == godutils.STATUS_SECONDARY_QUOTA_REACHED)
