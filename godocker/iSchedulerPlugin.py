from godocker.IGoDockerPlugin import IGoDockerPlugin

class ISchedulerPlugin(IGoDockerPlugin):


    def schedule(self, tasks, users):
        '''
        Schedule list of tasks to be ran according to user list

        :return: list of sorted tasks
        '''
        pass
