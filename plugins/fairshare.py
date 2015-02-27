from godocker.iSchedulerPlugin import ISchedulerPlugin

class FairShare(ISchedulerPlugin):
    def get_name(self):
        return "FairShareScheduler"

    def get_type(self):
        return "Scheduler"

    def schedule(self, tasks, users):
        '''
        Schedule list of tasks to be ran according to user list

        :return: list of sorted tasks
        '''
        #TODO
        return tasks
