from godocker.iExecutorPlugin import IExecutorPlugin
import json


class Swarm(IExecutorPlugin):
    def get_name(self):
        return "swarm"

    def get_type(self):
        return "Executor"

    def set_config(self, cfg):
        self.cfg = cfg

        from docker import Client

        self.docker_client = Client(base_url=self.cfg.docker_url)

    def run_tasks(self, tasks, callback=None):
        '''
        Execute task list on executor system

        :param tasks: list of tasks to run
        :type tasks: list
        :param callback: callback function to update tasks status (running/rejected)
        :type callback: func(running list,rejected list)

        :return: tuple of submitted and rejected/errored tasks
        '''
        running_tasks = []
        error_tasks = []
        for task in tasks:
            try:
                #job  = json.loads(task)
                job = task
                #self.logger.warn('Reservation: '+str(job['requirements']['cpu'])+','+str(job['requirements']['ram'])+'g')
                container = self.docker_client.create_container(image=job['container']['image'],
                                                                command=job['command']['cmd'],
                                                                cpu_shares=job['requirements']['cpu'],
                                                                mem_limit=str(job['requirements']['ram'])+'g',
                                                                ports=[22])
                response = self.docker_client.start(container=container.get('Id'),
                                        network_mode='host',
                                        publish_all_ports=True
                                        #port_bindings={22: None}
                                        )
                job['container']['id'] = container['Id']
                job['container']['meta'] = self.docker_client.inspect_container(container.get('Id'))
                running_tasks.append(job)
                self.logger.debug('Execute:Job:'+str(job['id'])+':'+job['container']['id'])
            except Exception as e:
                self.logger.error(str(job['id'])+':'+str(e))
                error_tasks.append(task)
        return (running_tasks,error_tasks)

    def get_finished_tasks(self, running_tasks):
        '''
        Return a list of tasks over
        '''
        tasks_finished = []
        containers = self.docker_client.containers()
        containers_running = []
        for c in containers:
            containers_running.append(c['Id'])
        for r in running_tasks:
            #job  = json.loads(r)
            job = r
            if job['container']['id'] not in containers_running:
                self.logger.debug('Container:'+str(job['container']['id'])+':Over')
                r['container']['meta'] = self.docker_client.inspect_container(container.get('Id'))
                r['container']['stats'] = self.docker_client.stats(job['container']['id'])
                tasks_finished.append(r)
                self.docker_client.remove_container(job['container']['id'])
            else:
                self.logger.debug('Container:'+job['container']['id']+':Running')
        return tasks_finished


    def list_running_tasks(self):
        '''
        Return a list of running tasks
        '''
        #TODO, if over, remove container
        containers = self.docker_client.containers()
        self.logger.debug(str(containers))
        return containers
