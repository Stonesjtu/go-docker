from yapsy.IPlugin import IPlugin

class ISchedulerPlugin(IPlugin):

    def get_name(self):
        pass

    def set_config(self, cfg):
        self.cfg = cfg

    def schedule(self, tasks, users):
        '''
        Schedule list of tasks to be ran according to user list

        :return: list of sorted tasks
        '''
        pass

    def set_logger(self, logger):
        '''
        Set logger for logging
        '''
        self.logger = logger
