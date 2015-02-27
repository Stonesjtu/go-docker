from yapsy.IPlugin import IPlugin

class IExecutorPlugin(IPlugin):

    def get_name(self):
        pass

    def set_config(self, cfg):
        self.cfg = cfg

    def run_tasks(self, tasks):
        '''
        Execute task list on executor system

        :return: rejected/errored tasks
        '''
        pass

    def set_logger(self, logger):
        '''
        Set logger for logging
        '''
        self.logger = logger
