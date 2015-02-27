from godocker.iExecutorPlugin import IExecutorPlugin
import logging

class FakeExecutor(IExecutorPlugin):
    def get_name(self):
        return "fake"

    def get_type(self):
        return "Executor"

    def run_tasks(self, tasks):
        '''
        Execute task list on executor system

        :return: rejected/errored tasks
        '''
        for task in tasks:
            self.logger.info("Run:Fake:task: "+str(task))
        return []
