from godocker.IGoDockerPlugin import IGoDockerPlugin


class IWatcherPlugin(IGoDockerPlugin):
    '''
    Watcher plugin reference. Watchers checks if task can continue to run
    '''

    def can_start(self, task):
        '''
        Checks if task can be scheduled for running now
        '''
        return True

    def started(self, task):
        '''
        Task  is started, this is an information event

        Task startup may be cancelled due to other watchers, quotas etc.... Resource reservation etc. should be effective only at this time.
        Resources will ke kept reserved until job termination or kill (*done* method)
        '''
        pass

    def can_run(self, task):
        '''
        Checks if task can continue to run. If task cannot run, this method must kill itself the task.

        Workflow:
          check if task is still running
          for each watcher, test watcher.can_run(task):
              if returns None
                  stop and remove from running tasks

        :param task: current task
        :type task: Task
        :return: Task or None if running checks should continue
        '''
        return task

    def done(self, task):
        '''
        Inform watcher of task termination

        :param task: current task
        :type task: Task
        '''
        return None
