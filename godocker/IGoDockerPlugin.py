from yapsy.IPlugin import IPlugin
from bson.json_util import dumps
import json

class IGoDockerPlugin(IPlugin):

    def set_redis_handler(self, redis_handler):
        self.redis_handler = redis_handler

    def set_jobs_handler(self, jobs_handler):
        self.jobs_handler = jobs_handler

    def set_users_handler(self, users_handler):
        self.users_handler = users_handler

    def get_name(self):
        '''
        Get name of plugin
        '''
        pass

    def set_config(self, cfg):
        '''
        Set configuration
        '''
        self.cfg = cfg

    def set_logger(self, logger):
        '''
        Set logger for logging
        '''
        self.logger = logger


    def get_users(self, user_id_list):
        '''
        Get users matching ids in user_id_list

        :param user_id_list: list containing the id of users
        :type user_id_list: list
        :return: list of users
        '''
        return self.users_handler.find({'id': {'$in' : user_id_list}})


    def kill_tasks(self, task_list):
        '''
        Set input tasks in kill queue

        :param task_list: list of tasks
        :type task_list: list
        '''
        for task in task_list:
            self.users_handler.update({'id': task['id']},
                {'$set': {
                        'status.secondary': 'kill requested'
                        }
            })
            self.redis_handler.rpush(self.cfg.redis_prefix+':jobs:kill',dumps(task))
