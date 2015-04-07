from godocker.iSchedulerPlugin import ISchedulerPlugin

class FiFo(ISchedulerPlugin):
    def get_name(self):
        return "FiFo"

    def get_type(self):
        return "Scheduler"

    def schedule(self, tasks):
        '''
        Schedule list of tasks to be ran according to user list

        :return: list of sorted tasks
        '''
        return tasks
