from yapsy.IPlugin import IPlugin

class IExecutorPlugin(IPlugin):

    def get_name(self):
        pass

    def set_config(self, cfg):
        self.cfg = cfg

    def run_tasks(self, tasks, callback=None):
        '''
        Execute task list on executor system

        :param tasks: list of tasks to run
        :type tasks: list
        :param callback: callback function to update tasks status (running/rejected)
        :type callback: func(running list,rejected list)

        :return: tuple of submitted and rejected/errored tasks
        '''
        return (None,None)

    def set_logger(self, logger):
        '''
        Set logger for logging
        '''
        self.logger = logger


    def watch_tasks(self, task, over):
        '''
        Get task status

        :param task: current task
        :type task: Task
        :param over: is task over
        :type over: bool
        '''
        return (task, True)
