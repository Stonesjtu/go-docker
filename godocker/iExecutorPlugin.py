from godocker.IGoDockerPlugin import IGoDockerPlugin

class IExecutorPlugin(IGoDockerPlugin):

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
            for i in range(self.cfg.port_start):
                self.redis_handler.rpush(self.cfg.redis_prefix+':ports:'+host, self.cfg.port_start + i)
        port = self.redis_handler.lpop(self.cfg.redis_prefix+':ports:'+host)
        self.logger.debug('Port:Give:'+task['container']['meta']['Node']['Name']+':'+str(port))
        if not 'ports' in task['container']:
            task['container']['ports'] = []
        task['container']['ports'].append(port)
        return int(port)
