import time, sys
import redis
import json
import logging
import signal
import os
import datetime
import time
import random
import string
import shutil
from copy import deepcopy
from datetime import date, timedelta

from pymongo import MongoClient
from pymongo import DESCENDING as pyDESCENDING
from bson.json_util import dumps
from config import Config

from godocker.pairtreeStorage import PairtreeStorage

if __name__ == "__main__":
        config_file = 'go-d.ini'
        if 'GOD_CONFIG' in os.environ:
            config_file = os.environ['GOD_CONFIG']
        if len(sys.argv) == 2:
                config_file == sys.argv[1]

        cfg_file = file(config_file)
        cfg = Config(cfg_file)
        mongo = MongoClient(cfg.mongo_url)
        db = mongo[cfg.mongo_db]
        db_jobsover = db.jobsover
        db_cleanup = db.cleanup

        dt = datetime.datetime.now()
        new_run = time.mktime(dt.timetuple())
        cleanup = db.cleanup.find_one({'id': 'pairtree'})
        if cleanup is None:
            last_run = 0
            db.cleanup.insert({'id': 'pairtree', 'last': 0})
        else:
            last_run = cleanup['last']

        store = PairtreeStorage(cfg)
        # Should get last run timestamp

        if 'clean_old' not in cfg:
            clean_old = 30
        else:
            clean_old = cfg.clean_old

        dt = datetime.datetime.now() - timedelta(days=clean_old)
        old_time = time.mktime(dt.timetuple())
        old_jobs = db_jobsover.find({'status.date_over': {'$lte': old_time, '$gte': last_run}})
        for job in old_jobs:
            job_dir = store.get_task_dir(job)
            if os.path.exists(job_dir):
                logging.debug('Delete '+job_dir)
                shutil.rmtree(job_dir)
            else:
                logging.debug('Dir not present: '+job_dir)

        # Update last_run
        db.cleanup.update({'id': 'pairtree'},{'$set': {'last': new_run}})
