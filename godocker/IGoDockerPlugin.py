from yapsy.IPlugin import IPlugin
from bson.json_util import dumps
import json

class IGoDockerPlugin(IPlugin):
    '''
    Base plugin reference
    '''

    def set_redis_handler(self, redis_handler):
        self.redis_handler = redis_handler

    def set_jobs_handler(self, jobs_handler):
        self.jobs_handler = jobs_handler

    def set_users_handler(self, users_handler):
        self.users_handler = users_handler

    def set_projects_handler(self, projects_handler):
        self.projects_handler = projects_handler

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

    def get_group_usage(self, group_id):
        '''
        Get cpu/ram/time usage for last period for a group

        :param group_id: group identifier
        :type group_id: int
        :return: list (cpu,ram,duration)
        '''
        cpu = self.redis_handler.get(self.cfg.redis_prefix+':group:'+str(group_id)+':cpu')
        ram = self.redis_handler.get(self.cfg.redis_prefix+':group:'+str(group_id)+':ram')
        duration = self.redis_handler.get(self.cfg.redis_prefix+':group:'+str(group_id)+':time')
        return (cpu, ram, duration)

    def get_running_tasks(self, start=0, stop=-1):
        '''
        Get all tasks running

        :param start: first task index
        :type start: int
        :param stop: last task index (-1 = all)
        :type stop: int
        '''
        running_tasks = []
        tasks = self.redis_handler.lrange(self.cfg.redis_prefix+':jobs:running', start, stop)
        for task in tasks:
            running_tasks.append(json.loads(task))
        return running_tasks

    def is_task_running(self, task_id):
        '''
        Checks if task is running

        :param task_id: task identifier
        :type task_id: int
        :return: bool
        '''
        task = self.r.get(self.cfg.redis_prefix+':job:'+str(task['id'])+':task')
        if task is not None:
            return True
        return False

    def is_task_over(self, task_id):
        '''
        Checks if task is over

        :param task_id: task identifier
        :type task_id: int
        :return: bool
        '''
        task = self.db_jobsover.find_one({'id': task_id})
        if task is not None:
            return True
        return False

    def is_task_running_or_over(self, task_id):
        '''
        Checks if task is running or over

        :param task_id: task identifier
        :type task_id: int
        :return: bool
        '''
        if self.is_task_running(task_id):
            return True
        if self.is_task_over(task_id):
            return True
        return False



    def kill_tasks(self, task_list):
        '''
        Set input tasks in kill queue

        :param task_list: list of tasks
        :type task_list: list
        '''
        for task in task_list:
            self.jobs_handler.update({'id': task['id']},
                {'$set': {
                        'status.secondary': 'kill requested'
                        }
            })
            self.redis_handler.rpush(self.cfg.redis_prefix+':jobs:kill',dumps(task))
