import time
import sys
import logging
import os
import datetime
from datetime import timedelta
import json

import redis
from pymongo import MongoClient
import yaml
from godocker.pairtreeStorage import PairtreeStorage
import godocker.utils as godutils

'''
Script to archive old jobs based on last run. Archive all jobs older than *clean_old* configuration parameter

Without parameters, archive old jobs. Else, with dditional parameters (job ids), only selected jobs will be archived.

'''

if __name__ == "__main__":
        config_file = 'go-d.ini'
        if 'GOD_CONFIG' in os.environ:
            config_file = os.environ['GOD_CONFIG']
        jobs_to_archive = []
        if len(sys.argv) >= 2:
            jobs_to_archive = sys.argv[1:]
            print "Request to archive job ids: " + str(jobs_to_archive)
        else:
            print "Archive old jobs"

        cfg = None
        with open(config_file, 'r') as ymlfile:
            cfg = yaml.load(ymlfile)
        mongo = MongoClient(cfg['mongo_url'])
        db = mongo[cfg['mongo_db']]
        db_jobsover = db.jobsover
        db_cleanup = db.cleanup
        db_users = db.users

        r = redis.StrictRedis(host=cfg['redis_host'], port=cfg['redis_port'], db=cfg['redis_db'], decode_responses=True)

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
            clean_old = cfg['clean_old']

        quota = True
        if 'disk_default_quota' not in cfg or cfg['disk_default_quota'] is None:
            quota = False


        if jobs_to_archive:
            for job_to_archive in jobs_to_archive:
                old_job = db_jobsover.find_one({'id': int(job_to_archive)})
                del old_job['_id']
                r.rpush(cfg['redis_prefix'] + ':jobs:archive', json.dumps(old_job))
        else:
            dt = datetime.datetime.now() - timedelta(days=clean_old)
            old_time = time.mktime(dt.timetuple())
            old_jobs = db_jobsover.find({'status.date_over': {'$lte': old_time, '$gte': last_run}})
            for job in old_jobs:
                del job['_id']
                r.rpush(cfg['redis_prefix'] + ':jobs:archive', json.dumps(job))

            # Update last_run
            db.cleanup.update({'id': 'pairtree'}, {'$set': {'last': new_run}})
