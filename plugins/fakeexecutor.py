from godocker.iExecutorPlugin import IExecutorPlugin
from godocker.utils import is_array_task


class FakeExecutor(IExecutorPlugin):

    fail_on = 5

    def get_name(self):
        return "fake"

    def get_type(self):
        return "Executor"

    def features(self):
        '''
        Get supported features

        :return: list of features within ['kill', 'pause']
        '''
        return ['kill', 'pause', 'interactive']

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
            if is_array_task(task):
                # Virtual task for a task array, do not really execute
                running_tasks.append(task)
                self.logger.debug('Execute:Job:' + str(task['id']) + ':Skip:Array')
                continue
            if i < self.fail_on:
                self.logger.debug("Run:Fake:task:run:" + str(task['id']))
                task['container']['meta'] = {'Node': {'Name': 'fake-laptop'}}
                if task['command']['interactive']:
                    # port mapping
                    mapped_port = self.get_mapping_port('fake-laptop', task)
                    self.logger.debug('Run:Fake:MappedPort:' + str(mapped_port))
                running_tasks.append(task)
            else:
                self.logger.debug("Run:Fake:task:reject:" + str(task['id']))
                rejected_tasks.append(task)
            i += 1
        return (running_tasks, rejected_tasks)


    def watch_tasks(self, task):
        '''
        Get task status

        Must update task with following params if task is over:
            task['container']['meta']['State']['ExitCode']
        In case of node failure:
            task['status']['failure'] = { 'reason': reason_of_failure,
                                           'nodes': [ node(s)_where_failure_occured]}


        :param task: current task
        :type task: Task
        :param over: is task over
        :type over: bool
        '''
        self.logger.debug('Mesos:Task:Check:Running:' + str(task['id']))
        if 'testerror' == task['meta']['name']:
            task['status']['failure'] = {'reason': 'fake error', 'nodes': ['testhost']}
        return (task, True)
