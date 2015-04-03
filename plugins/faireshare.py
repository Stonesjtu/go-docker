from godocker.iSchedulerPlugin import ISchedulerPlugin

import datetime
import time

class FaireShare(ISchedulerPlugin):
    '''
    Faire share policy scheduler
    '''

    waiting_time_weight = 0.1
    user_time_weight = 1
    user_cpu_weight = 0.2
    user_ram_weight = 0.2
    group_time_weight = 0.1
    group_cpu_weight = 0.01
    group_ram_weight = 0.01

    max_waiting_time = 0
    min_waiting_time = 0

    max_user_time = 0
    max_user_cpu = 0
    max_user_ram = 0
    max_group_time = 0
    max_group_cpu = 0
    max_group_ram = 0

    min_user_time = 0
    min_user_cpu = 0
    min_user_ram = 0
    min_group_time = 0
    min_group_cpu = 0
    min_group_ram = 0

    def normalize(self, value, min, max):
        result = 0.5
        if max - min < 1:
            result = 0.5
        else:
            result = (value - min)/( max - min);
        return result;

    def get_ticket_share(self, user, group, task):
        '''
        user and group previous usage: (cpu, ram, duration)
        '''
        dt = datetime.datetime.now()
        timestamp = time.mktime(dt.timetuple())
        task_waiting_time = self.normalize(timestamp - task['date'], min_waiting_time, max_waiting_time)
        (user_cpu, user_ram, user_time) = user
        user_time = self.normalize(user_time, min_user_time, max_user_time)
        user_cpu = self.normalize(user_cpu, min_user_cpu, max_user_cpu)
        user_ram = self.normalize(user_ram, min_user_ram, max_user_ram)
        (group_cpu, group_ram, group_time) = group
        group_time = self.normalize(group_time, min_group_time, max_group_time)
        group_cpu = self.normalize(group_cpu, min_group_cpu, max_group_cpu)
        group_ram = self.normalize(group_ram, min_group_ram, max_group_ram)
        ticket_share = task_waiting_time*waiting_time_weight + \
                        user_time*user_time_weight + \
                        user_cpu*user_cpu_weight + \
                        user_ram*user_ram_weight + \
                        group_time*group_time_weight + \
                        group_cpu*group_cpu_weight + \
                        group_ram*group_ram_weight
        return ticket_share

    def get_name(self):
        return "FaireShare"

    def get_type(self):
        return "Scheduler"

    def schedule(self, tasks, users):
        '''
        Schedule list of tasks to be ran according to user list

        :return: list of sorted tasks
        '''
        #TODO
        return tasks
