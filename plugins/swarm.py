from godocker.iExecutorPlugin import IExecutorPlugin
import json
import datetime
import iso8601


class Swarm(IExecutorPlugin):
    def get_name(self):
        return "swarm"

    def get_type(self):
        return "Executor"

    def set_config(self, cfg):
        self.cfg = cfg

        from docker import Client

        self.docker_client = Client(base_url=self.cfg.docker_url)

    def run_tasks(self, tasks, callback=None, portmapping=None):
        '''
        Execute task list on executor system

        :param tasks: list of tasks to run
        :type tasks: list
        :param callback: callback function to update tasks status (running/rejected)
        :type callback: func(running list,rejected list)
        :param portmapping: function(hostname) to call to get a free port on host for port mapping
        :type portmapping: def
        :return: tuple of submitted and rejected/errored tasks
        '''
        running_tasks = []
        error_tasks = []
        for task in tasks:
            try:
                #job  = json.loads(task)
                job = task
                port_list = []
                if job['command']['interactive']:
                    port_list = [22]
                #self.logger.warn('Reservation: '+str(job['requirements']['cpu'])+','+str(job['requirements']['ram'])+'g')
                container = self.docker_client.create_container(name=job['meta']['name']+'_'+str(job['id'])
                                                                image=job['container']['image'],
                                                                command=job['command']['cmd'],
                                                                cpu_shares=job['requirements']['cpu'],
                                                                mem_limit=str(job['requirements']['ram'])+'g',
                                                                ports=port_list)

                job['container']['meta'] = self.docker_client.inspect_container(container.get('Id'))

                port_mapping = {}
                for port in port_list:
                    mapped_port = portmapping(job['container']['meta']['Node']['name'], job)
                    port_mapping[port] = mapped_port

                response = self.docker_client.start(container=container.get('Id'),
                                        network_mode='host',
                                        #publish_all_ports=True
                                        port_bindings=port_mapping
                                        )
                job['container']['id'] = container['Id']
                #job['container']['meta'] = self.docker_client.inspect_container(container.get('Id'))
                running_tasks.append(job)
                self.logger.debug('Execute:Job:'+str(job['id'])+':'+job['container']['id'])
            except Exception as e:
                self.logger.error(str(job['id'])+':'+str(e))
                error_tasks.append(task)
        return (running_tasks,error_tasks)

    def watch_tasks(self, task):
        '''
        Get task status

        :param task: current task
        :type task: Task
        :param over: is task over
        :type over: bool
        '''
        over = False

        #task['container']['stats'] = self.docker_client.stats(task['container']['id'])

        task['container']['meta'] = self.docker_client.inspect_container(task['container']['id'])
        finished_date =  task['container']['meta']['State']['FinishedAt']
        finished_date = iso8601.parse_date(finished_date)
        if finished_date.year > 1:
            over = True

        if over:
            self.logger.warn('Container:'+str(task['container']['id'])+':Over')
            self.docker_client.remove_container(task['container']['id'])
            over = True
        else:
            self.logger.debug('Container:'+task['container']['id']+':Running')
        return (task, over)
