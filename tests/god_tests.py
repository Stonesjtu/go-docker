from nose.tools import *
from nose.plugins.attrib import attr

import json
import shutil
import os
import tempfile
import logging
import copy
import stat

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
        self.daemon = GoDScheduler(os.path.join(self.test_dir,'godsched.pid'))
        self.daemon.load_config(self.cfg)

    def tearDown(self):
        pass

    def test_sample(self):
        self.assertTrue(1==1)
