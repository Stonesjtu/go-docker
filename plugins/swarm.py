from godocker.iExecutorPlugin import IExecutorPlugin


class Swarm(IExecutorPlugin):
    def get_name(self):
        return "swarm"

    def get_type(self):
        return "Executor"

    def run_tasks(self, tasks):
        '''
        Execute task list on executor system

        :return: rejected/errored tasks
        '''
        return []
