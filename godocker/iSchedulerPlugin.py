from godocker.IGoDockerPlugin import IGoDockerPlugin

import datetime
from datetime import date, timedelta
import time

class ISchedulerPlugin(IGoDockerPlugin):
    '''
    Scheduler plugins interface
    '''


    def get_user_prio(self, user_id):
        '''
        Get user priority (between 0 and 1)
        '''
        prio = self.redis_handler.get(self.cfg.redis_prefix+':user:'+user_id+':prio')
        if prio is None:
            user = self.users_handler.find_one({'id': user_id})
            if not user or 'prio' not in user['usage']:
                prio = 0.5
            else:
                prio = float(user['usage']['prio']/100)
                self.redis_handler.set(self.cfg.redis_prefix+':user:'+user_id+':prio',str(prio))
        return prio

    def get_project_prio(self, project_id):
        '''
        Get project priority (between 0 and 1)
        '''
        prio = self.redis_handler.get(self.cfg.redis_prefix+':project:'+project_id+':prio')
        if prio is None:
            project = self.projects_handler.find_one({'id': project_id})
            if not project or 'prio' not in project['usage']:
                prio = 0.5
            else:
                prio = float(project['usage']['prio']/100)
                self.redis_handler.set(self.cfg.redis_prefix+':project:'+project_id+':prio',str(prio))
        return prio

    def get_user_usage(self, identifier, key='user'):
        '''
        :param identifier: user/group identifier
        :type identifier: str
        :param key: user or group
        :type key: str
        :return: dict {
                total_time,
                total__cpu,
                total_ram,
                }
        '''

        dt = datetime.datetime.now()

        total_time = 0.0
        total_cpu = 0
        total_ram = 0

        for i in range(0, self.cfg.user_reset_usage_duration):
            previous = dt - timedelta(days=i)
            date_key = str(previous.year)+'_'+str(previous.month)+'_'+str(previous.day)
            if self.redis_handler.exists(self.cfg.redis_prefix+':'+key+':'+identifier+':cpu:'+date_key):
                cpu = self.redis_handler.get(self.cfg.redis_prefix+':'+key+':'+identifier+':cpu:'+date_key)
                ram = self.redis_handler.get(self.cfg.redis_prefix+':'+key+':'+identifier+':ram:'+date_key)
                duration = self.redis_handler.get(self.cfg.redis_prefix+':'+key+':'+identifier+':time:'+date_key)
                total_cpu += int(cpu)
                total_ram += int(ram)
                total_time += float(duration)
            else:
                break


        usage = {
                'total_time': total_time,
                'total_cpu': total_cpu,
                'total_ram': total_ram,
                }
        return usage

    def get_bounds_waiting_time(self, tasks):
        '''
        Gets min and max waiting time for tasks

        :param tasks: list of pending tasks
        :type tasks: list
        :return: list (max_time, min_time)
        '''
        max_time = 0
        min_time = -1
        dt = datetime.datetime.now()
        timestamp = time.mktime(dt.timetuple())

        for task in tasks:
            delta = timestamp - task['date']
            if delta > max_time:
                max_time = delta
            if delta < min_time or min_time == -1:
                min_time = delta
        return (max_time, min_time)

    def get_bounds_usage(self, usages):
        '''
        Gets min and max usage

        :param usages: input usages list of dict{ total_time, total__cpu, total_ram }
        :type usages: list
        :return: dict {
                        max_time, min_time,
                        max_cpu, min_cpu,
                        max_ram, min_ram
                    }
        '''
        max_time = 0.0
        min_time = -1
        max_cpu = 0
        min_cpu = -1
        max_ram = 0
        min_ram = -1
        for usage in usages:
            if usage['total_time'] > max_time:
                max_time = usage['total_time']
            if usage['total_time'] < min_time or min_time == -1:
                min_time = usage['total_time']
            if usage['total_cpu'] > max_cpu:
                max_cpu = usage['total_cpu']
            if usage['total_cpu'] < min_cpu or min_cpu == -1:
                min_cpu = usage['total_cpu']
            if usage['total_ram'] > max_ram:
                max_ram = usage['total_ram']
            if usage['total_ram'] < min_ram or min_ram == -1:
                min_ram = usage['total_ram']

        return {
                'max_time': max_time,
                'min_time': min_time,
                'max_cpu': max_cpu,
                'min_cpu': min_cpu,
                'max_ram': max_ram,
                'min_ram': min_ram
        }

    def schedule(self, tasks):
        '''
        Schedule list of tasks to be ran according to user list

        :return: list of sorted tasks
        '''
        pass
