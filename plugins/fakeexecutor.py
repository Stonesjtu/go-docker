from godocker.iExecutorPlugin import IExecutorPlugin
import logging

class FakeExecutor(IExecutorPlugin):
    def get_name(self):
        return "fake"

    def get_type(self):
        return "Executor"

    def run_tasks(self, tasks, callback=None, portmapping=None):
        '''
        Execute task list on executor system

        :param tasks: list of tasks to run
        :type tasks: list
        :param callback: callback function to update tasks status (running/rejected)
        :type callback: func(running list,rejected list)
        :param portmapping: function(hostname) to call to get a free port on host for port mapping
        :type portmapping: def
        :return: tuple of submitted and rejected/errored tasks
        '''
        for task in tasks:
            self.logger.info("Run:Fake:task: "+str(task))
        return (tasks, [])
