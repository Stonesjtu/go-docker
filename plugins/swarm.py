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

        self.docker_client = Client(base_url=self.cfg.docker_url, version=self.cfg.docker_api_version)

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
            container = None
            try:
                #job  = json.loads(task)
                job = task
                port_list = []
                if job['command']['interactive']:
                    port_list = [22]
                #self.logger.warn('Reservation: '+str(job['requirements']['cpu'])+','+str(job['requirements']['ram'])+'g')
                vol_list = []
                for v in job['container']['volumes']:
                    if v['mount'] is None:
                        v['mount'] = v['path']
                    vol_list.append(v['mount'])
                container = self.docker_client.create_container(image=job['container']['image'],
                                                                command=job['command']['script'],
                                                                cpu_shares=job['requirements']['cpu'],
                                                                mem_limit=str(job['requirements']['ram'])+'g',
                                                                ports=port_list,
                                                                volumes=vol_list)
                job['container']['meta'] = self.docker_client.inspect_container(container.get('Id'))
                port_mapping = {}
                for port in port_list:
                    mapped_port = self.get_mapping_port(job['container']['meta']['Node']['Name'], job)
                    port_mapping[port] = mapped_port
                vol_binds = {}
                for v in job['container']['volumes']:
                    if v['mount'] is None:
                        v['mount'] = v['path']
                    ro = True
                    if v['acl'] == 'rw':
                        ro = False
                    vol_binds[v['path']] = {
                        'bind': v['mount'],
                        'ro': ro
                    }
                response = self.docker_client.start(container=container.get('Id'),
                                        network_mode='bridge',
                                        #publish_all_ports=True
                                        port_bindings=port_mapping,
                                        binds=vol_binds
                                        )

                job['container']['id'] = container['Id']
                #job['container']['meta'] = self.docker_client.inspect_container(container.get('Id'))
                running_tasks.append(job)
                self.logger.debug('Execute:Job:'+str(job['id'])+':'+job['container']['id'])
            except Exception as e:
                self.logger.error('Execute:Job:'+str(job['id'])+':'+str(e))
                error_tasks.append(task)
                if container:
                    self.docker_client.remove_container(container.get('Id'))
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
        finished_date = None
        #task['container']['stats'] = self.docker_client.stats(task['container']['id'])
        try:
            task['container']['meta'] = self.docker_client.inspect_container(task['container']['id'])
            finished_date =  task['container']['meta']['State']['FinishedAt']
            finished_date = iso8601.parse_date(finished_date)
        except Exception:
            self.logger.debug("Could not get container, may be already killed: "+task['container']['id'])
            finished_date = datetime.datetime.now()

        if finished_date.year > 1:
            over = True

        if over:
            self.logger.warn('Container:'+str(task['container']['id'])+':Over')
            try:
                self.docker_client.remove_container(task['container']['id'])
            except Exception:
                self.logger.debug('Could not remove container '+task['container']['id'])
            over = True
        else:
            self.logger.debug('Container:'+task['container']['id']+':Running')
        return (task, over)


    def kill_task(self, task):
        '''
        Kills a running task

        :param tasks: task to kill
        :type tasks: Task
        :return: (Task, over) over is True if task could be killed
        '''
        over = True
        try:
            self.docker_client.kill(task['container']['id'])
        except Exception as e:
            self.logger.debug("Could not kill container: "+task['container']['id'])
        try:
            self.docker_client.remove_container(task['container']['id'])
        except Exception as e:
            self.logger.debug("Could not kill/remove container: "+task['container']['id'])
            if e.response.status_code == 404:
                self.logger.debug('container not found, already deleted?')
                over = True
            else:
                over = False
        return (task, over)
