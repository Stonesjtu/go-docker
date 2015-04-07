from godocker.iSchedulerPlugin import ISchedulerPlugin

import datetime
import time

class FairShare(ISchedulerPlugin):
    '''
    Fair share policy scheduler
    '''

    waiting_time_weight = 0.1
    user_time_weight = 1
    user_cpu_weight = 0.2
    user_ram_weight = 0.2
    group_time_weight = 0.1
    group_cpu_weight = 0.01
    group_ram_weight = 0.01
    user_weight = 1
    group_weight = 1

    def load(self):

        self.max_waiting_time = 0
        self.min_waiting_time = 0

        self.max_user_time = 0
        self.max_user_cpu = 0
        self.max_user_ram = 0

        self.max_group_time = 0
        self.max_group_cpu = 0
        self.max_group_ram = 0

        self.min_user_time = 0
        self.min_user_cpu = 0
        self.min_user_ram = 0

        self.min_group_time = 0
        self.min_group_cpu = 0
        self.min_group_ram = 0

        self.users_usage = {}
        self.projects_usage = {}

        self.users_prio = {}
        self.projects_prio = {}

    def normalize(self, value, min, max):
        result = 0.5
        if max - min < 1:
            result = 0.5
        else:
            result = (value - min)/( max - min);
        return result;

    def get_ticket_share(self, user, group, task):
        '''
        user and group previous usage: (cpu, ram, duration, prio)
        '''
        dt = datetime.datetime.now()
        timestamp = time.mktime(dt.timetuple())
        task_waiting_time = self.normalize(timestamp - task['date'], self.min_waiting_time, self.max_waiting_time)
        (user_cpu, user_ram, user_time, user_prio) = user
        user_time = self.normalize(user_time, self.min_user_time, self.max_user_time)
        user_cpu = self.normalize(user_cpu, self.min_user_cpu, self.max_user_cpu)
        user_ram = self.normalize(user_ram, self.min_user_ram, self.max_user_ram)
        (group_cpu, group_ram, group_time, group_prio) = group
        group_time = self.normalize(group_time, self.min_group_time, self.max_group_time)
        group_cpu = self.normalize(group_cpu, self.min_group_cpu, self.max_group_cpu)
        group_ram = self.normalize(group_ram, self.min_group_ram, self.max_group_ram)
        ticket_share =  task_waiting_time*self.waiting_time_weight + \
                        user_time*self.user_time_weight + \
                        user_cpu*self.user_cpu_weight + \
                        user_ram*self.user_ram_weight + \
                        group_time*self.group_time_weight + \
                        group_cpu*self.group_cpu_weight + \
                        group_ram*self.group_ram_weight + \
                        (1-user_prio)*(1-self.user_weight) + \
                        (1-group_prio)*(1-self.group_weight)
        return ticket_share

    def get_name(self):
        return "FairShare"

    def get_type(self):
        return "Scheduler"

    def schedule(self, tasks):
        '''
        Schedule list of tasks to be ran according to user list

        :return: list of sorted tasks
        '''
        #TODO
        #(self.max_waiting_time, self.min_waiting_time) = self.get_bounds_waiting_time(tasks)

        self.max_waiting_time = 0
        self.min_waiting_time = -1
        dt = datetime.datetime.now()
        timestamp = time.mktime(dt.timetuple())

        self.load()

        for task in tasks:
            user_id = task['user']['id']
            project_id = task['user']['project']
            if user_id not in self.users_usage:
                user_usage = self.get_user_usage(user_id, 'user')
                self.users_usage[user_id] = user_usage
            if project_id not in self.projects_usage:
                self.projects_usage[project_id] = self.get_user_usage(project_id, 'group')

            if user_id not in self.users_prio:
                self.users_prio[user_id] = self.get_user_prio(user_id)
            if project_id not in self.projects_prio:
                self.projects_prio[project_id] = self.get_project_prio(project_id)
            delta = timestamp - task['date']
            if delta > self.max_waiting_time:
                self.max_waiting_time = delta
            if delta < self.min_waiting_time or self.min_waiting_time == -1:
                self.min_waiting_time = delta

        # Get user bounds
        usages = []
        for user_id in self.users_usage.keys():
            usages.append(self.users_usage[user_id])
        max_usages = self.get_bounds_usage(usages)
        self.max_user_time = max_usages['max_time']
        self.min_user_time = max_usages['min_time']
        self.max_user_cpu = max_usages['max_cpu']
        self.min_user_cpu = max_usages['min_cpu']
        self.max_user_ram = max_usages['max_ram']
        self.min_user_ram = max_usages['min_ram']

        # Get project bounds
        usages = []
        for project_id in self.projects_usage.keys():
            usages.append(self.projects_usage[project_id])
        max_usages = self.get_bounds_usage(usages)
        self.max_group_time = max_usages['max_time']
        self.min_group_time = max_usages['min_time']
        self.max_group_cpu = max_usages['max_cpu']
        self.min_group_cpu = max_usages['min_cpu']
        self.max_group_ram = max_usages['max_ram']
        self.min_group_ram = max_usages['min_ram']

        for task in tasks:
            user_id = task['user']['id']
            project_id = task['user']['project']
            user_prio = self.users_prio[user_id]
            project_prio = self.projects_prio[project_id]
            user_usage = (self.users_usage[user_id]['total_cpu'], self.users_usage[user_id]['total_ram'], self.users_usage[user_id]['total_time'], user_prio)
            project_usage = (self.projects_usage[project_id]['total_cpu'], self.projects_usage[project_id]['total_ram'], self.projects_usage[project_id]['total_time'], project_prio)
            task['requirements']['ticket_share'] = self.get_ticket_share(user_usage, project_usage, task)

        tasks.sort(key=lambda x: x['requirements']['ticket_share'], reverse=True)

        return tasks
