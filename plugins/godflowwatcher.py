from godocker.iWatcherPlugin import IWatcherPlugin
import logging
from godocker.utils import is_array_child_task, is_array_task
import datetime
import time
import jwt
import requests

class GodFlowWatcher(IWatcherPlugin):
    def get_name(self):
        return "godflow"

    def get_type(self):
        return "Watcher"


    def done(self, task):
        if 'godflow' not in task['requirements'] or not task['requirements']['godflow']:
            return None
        web_endpoint = self.cfg['flow']['frontend']
        token = jwt.encode({'event': task['id'],
                                'exp': datetime.datetime.utcnow() + datetime.timedelta(seconds=3600),
                                'aud': 'urn:godocker/api'}, self.cfg['shared_secret_passphrase'])
        headers = {'Authorization': 'Bearer '+token}
        self.logger.debug("GodFlow:over: "+str(task['id']))
        # Submit task to godocker
        try:
            r = requests.get(web_endpoint + '/godflow/api/1.0/event/' + str(task['id']) + '/status/over', headers=headers)
        except Exception as e:
            self.logger.error("Failed to contact godflow "+web_endpoint+": "+str(e))
        return None
