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

        this fake executor will reject all tasks above 5 to simulate a "no more resources"

        :param tasks: list of tasks to run
        :type tasks: list
        :param callback: callback function to update tasks status (running/rejected)
        :type callback: func(running list,rejected list)
        :param portmapping: function(hostname) to call to get a free port on host for port mapping
        :type portmapping: def
        :return: tuple of submitted and rejected/errored tasks
        '''
        running_tasks = []
        rejected_tasks = []
        i = 0
        for task in tasks:
            if i < 5:
                self.logger.debug("Run:Fake:task:run:"+str(task['id']))
                running_tasks.append(task)
            else:
                self.logger.debug("Run:Fake:task:reject:"+str(task['id']))
                rejected_tasks.append(task)
            i += 1
        return (running_tasks, rejected_tasks)
