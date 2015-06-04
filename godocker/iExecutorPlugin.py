from godocker.IGoDockerPlugin import IGoDockerPlugin

class IExecutorPlugin(IGoDockerPlugin):
    '''
    Executor plugins interface
    '''

    def features(self):
        '''
        Get supported features

        :return: list of features within ['kill', 'pause','resources.port']
        '''
        return []

    def open(self, proc_type=None):
        '''
        Request start of executor if needed

        :param proc_type: type of process requesting open, 0 for scheduler, 1 for watcher
        :type proc_type:
        '''
        pass

    def close(self):
        '''
        Request end of executor if needed
        '''
        pass

    def suspend_task(self, task):
        '''
        Suspend/pause a task

        :param tasks: task to suspend
        :type tasks: Task
        :return: (Task, over) over is True if task could be suspended
        '''

        return (task, True)

    def resume_task(self, task):
        '''
        Resume/restart a task

        :param tasks: task to resumed
        :type tasks: Task
        :return: (Task, over) over is True if task could be resumed
        '''

        return (task, True)

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

    def run_all_tasks(self, tasks, callback=None):
        '''
        Execute all task list on executor system, all tasks must be executed together

        :param tasks: list of tasks to run
        :type tasks: list
        :param callback: callback function to update tasks status (running/rejected)
        :type callback: func(running list,rejected list)
        :return: tuple of submitted and rejected/errored tasks
        '''
        return (None,None)

    def kill_task(self, task):
        '''
        Kills a running task

        :param tasks: task to kill
        :type tasks: Task
        :return: (Task, over) over is True if task could be killed
        '''
        return (task, True)



    def watch_tasks(self, task):
        '''
        Get task status

        :param task: current task
        :type task: Task
        :param over: is task over
        :type over: bool
        '''
        return (task, True)

    def get_mapping_port(self, host, task):
        '''
        Get a port mapping for interactive tasks

        :param host: hostname of the container
        :type host: str
        :param task: task
        :type task: int
        :return: available port
        '''
        if not self.redis_handler.exists(self.cfg.redis_prefix+':ports:'+host):
            for i in range(self.cfg.port_range):
                self.redis_handler.rpush(self.cfg.redis_prefix+':ports:'+host, self.cfg.port_start + i)
        port = self.redis_handler.lpop(self.cfg.redis_prefix+':ports:'+host)
        self.logger.debug('Port:Give:'+task['container']['meta']['Node']['Name']+':'+str(port))
        if not 'ports' in task['container']:
            task['container']['ports'] = []
        task['container']['ports'].append(port)
        return int(port)
