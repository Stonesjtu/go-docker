from godocker.IGoDockerPlugin import IGoDockerPlugin


class IExecutorPlugin(IGoDockerPlugin):
    '''
    Executor plugins interface
    '''

    def features(self):
        '''
        Get supported features

        :return: list of features within ['kill', 'pause','resources.port',' cni', 'interactive']
        '''
        return []

    def usage(self):
        '''
        Get resource usage

        :return: array of nodes with used/total resources with
            {
                'name': slave_hostname,
                'cpu': (cpus_used, cpu_total),
                'mem': (mem_used, mem_total),
                'disk': (disk_used, disk_total),
            }

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

        Method must update:
            - task['container']['port_mapping'] to append port mappings is some ports are opened with format {'host': mapped_port, 'container': port}
            - task['container']['ports'] array must also contain the list of host ports. Those are sets automatically if using get_mapping_port method.

        Executor can optionally set task['container']['status'] to give additional information to the user, and update it during the life cycle of the task.

            initializing: container is in startup step but not yet started (pulling image etc...)
            ready: container is started

        :param tasks: list of tasks to run
        :type tasks: list
        :param callback: callback function to update tasks status (running/rejected)
        :type callback: func(running list,rejected list)
        :return: tuple of submitted and rejected/errored tasks
        '''
        return (None, None)

    def run_all_tasks(self, tasks, callback=None):
        '''
        Execute all task list on executor system, all tasks must be executed together

        :param tasks: list of tasks to run
        :type tasks: list
        :param callback: callback function to update tasks status (running/rejected)
        :type callback: func(running list,rejected list)
        :return: tuple of submitted and rejected/errored tasks
        '''
        return (None, None)

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
        return (task, True)

    def release_port(self, task):
        '''
        Release a port mapping
        '''
        for port in task['container']['ports']:
            host = task['container']['meta']['Node']['Name']
            self.logger.debug('Port:Back:' + host + ':' + str(port))
            self.redis_handler.rpush(self.cfg['redis_prefix'] + ':ports:' + host, port)

    def get_mapping_port(self, host, task):
        '''
        Get a port mapping for interactive tasks

        If None is returned, task should rejected.

        :param host: hostname of the container
        :type host: str
        :param task: task
        :type task: int
        :return: available port, None if no port is available
        '''
        if not self.redis_handler.exists(self.cfg['redis_prefix'] + ':ports:' + host):
            for i in range(self.cfg['port_range']):
                self.redis_handler.rpush(self.cfg['redis_prefix'] + ':ports:' + host, self.cfg['port_start'] + i)
        port = self.redis_handler.lpop(self.cfg['redis_prefix'] + ':ports:' + host)
        if port is None:
            return None
        self.logger.debug('Port:Give:' + task['container']['meta']['Node']['Name'] + ':' + str(port))
        if 'ports' not in task['container']:
            task['container']['ports'] = []
        task['container']['ports'].append(port)
        return int(port)

    def set_network_plugin(self, plugin):
        '''
        Sets the network plugin to use

        :param plugin: plugin instance
        :type plugin: iNetworkPlugin instance
        '''
        self.network = plugin
