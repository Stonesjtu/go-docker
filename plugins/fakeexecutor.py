from godocker.iExecutorPlugin import IExecutorPlugin
import logging

class FakeExecutor(IExecutorPlugin):
    def get_name(self):
        return "fake"

    def get_type(self):
        return "Executor"

    def run_tasks(self, tasks, callback=None):
        '''
        Execute task list on executor system

        :param tasks: list of tasks to run
        :type tasks: list
        :param callback: callback function to update tasks status (running/rejected)
        :type callback: func(running list,rejected list)

        :return: tuple of submitted and rejected/errored tasks
        '''
        for task in tasks:
            self.logger.info("Run:Fake:task: "+str(task))
        return (tasks, [])

    def get_finished_tasks(self, running_tasks):
        '''
        Return a list of tasks over
        '''
        return running_tasks
