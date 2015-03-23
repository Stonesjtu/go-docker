from godocker.iExecutorPlugin import IExecutorPlugin
import logging

class FakeExecutor(IExecutorPlugin):
    def get_name(self):
        return "fake"

    def get_type(self):
        return "Executor"

    def run_all_tasks(self, tasks, callback=None):
        '''
        Execute all task list on executor system, all tasks must be executed together

        :param tasks: list of tasks to run
        :type tasks: list
        :param callback: callback function to update tasks status (running/rejected)
        :type callback: func(running list,rejected list)
        :return: tuple of submitted and rejected/errored tasks
        '''
        return self.run_tasks(tasks, callback)

    def run_tasks(self, tasks, callback=None):
        '''
        Execute task list on executor system

        this fake executor will reject all tasks above 5 to simulate a "no more resources"

        :param tasks: list of tasks to run
        :type tasks: list
        :param callback: callback function to update tasks status (running/rejected)
        :type callback: func(running list,rejected list)
        :return: tuple of submitted and rejected/errored tasks
        '''
        running_tasks = []
        rejected_tasks = []
        i = 0
        for task in tasks:
            if task['parent_task_id']:
                # Virtual task for a task array, do not really execute
                running_tasks.append(task)
                self.logger.debug('Execute:Job:'+str(task['id'])+':Skip:Array')
                continue
            if i < 5:
                self.logger.debug("Run:Fake:task:run:"+str(task['id']))
                running_tasks.append(task)
                if task['command']['interactive']:
                    # port mapping
                    task['container']['meta'] = { 'Node': { 'Name': 'fake-laptop'} }
                    mapped_port = self.get_mapping_port('fake-laptop', task)
            else:
                self.logger.debug("Run:Fake:task:reject:"+str(task['id']))
                rejected_tasks.append(task)
            i += 1
        return (running_tasks, rejected_tasks)
