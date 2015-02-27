from godocker.iExecutorPlugin import IExecutorPlugin


class Swarm(IExecutorPlugin):
    def get_name(self):
        return "swarm"

    def get_type(self):
        return "Executor"

    def set_config(self, cfg):
        self.cfg = cfg

        from docker import Client

        self.docker_client = Client(base_url=self.cfg.docker_url)

    def run_tasks(self, tasks):
        '''
        Execute task list on executor system

        :return: tuple of submitted and rejected/errored tasks
        '''
        running_tasks = []
        for task in tasks:
            job  = json.loads(task)
            container = self.docker_client.create_container(image=job['container']['image'],
                                                            command=job['command']['cmd'],
                                                            cpu_shares=job['requirements']['cpu'],
                                                            mem_limit=str(job['requirements']['ram'])+'g',
                                                            ports=[22])
            response = cli.start(container=container.get('Id'),
                                    network_mode='host',
                                    port_bindings={22: None})
            job['container']['id'] = container['Id']
            running_tasks.append(json.dumps(job))
        return (running_tasks,[])


    def list_running_tasks(self):
        '''
        Return a list of running tasks
        '''
        #TODO
        containers = self.docker_client.containers()
        self.logger.debug(str(containers))
        return []
