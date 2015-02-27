from yapsy.IPlugin import IPlugin

class IExecutorPlugin(IPlugin):

    def get_name(self):
        pass

    def set_config(self, cfg):
        self.cfg = cfg

    def run_tasks(self, tasks):
        '''
        Execute task list on executor system

        :return: tuple of submitted and rejected/errored tasks
        '''
        return (None,None)

    def set_logger(self, logger):
        '''
        Set logger for logging
        '''
        self.logger = logger

    def list_running_tasks(self):
        '''
        Return a list of running tasks
        '''
        return []
