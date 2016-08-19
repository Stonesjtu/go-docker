from godocker.iExecutorPlugin import IExecutorPlugin
import datetime
import iso8601
from godocker.utils import is_array_task


class Swarm(IExecutorPlugin):

    def get_name(self):
        return "swarm"

    def get_type(self):
        return "Executor"

    def features(self):
        '''
        Get supported features

        :return: list of features within ['kill', 'pause', 'cni']
        '''
        return ['kill', 'pause', 'cni']

    def release_port(self, task):
        '''
        Release a port mapping
        '''
        for port in task['container']['ports']:
            host = 'godocker-swarm'
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
        host = 'godocker-swarm'
        if not self.redis_handler.exists(self.cfg['redis_prefix'] + ':ports:' + host):
            for i in range(self.cfg['port_range']):
                self.redis_handler.rpush(self.cfg['redis_prefix'] + ':ports:' + host, self.cfg['port_start'] + i)
        port = self.redis_handler.lpop(self.cfg['redis_prefix'] + ':ports:' + host)
        if port is None:
            return None
        self.logger.debug('Port:Give:' + host + ':' + str(port))
        if 'ports' not in task['container']:
            task['container']['ports'] = []
        task['container']['ports'].append(port)
        return int(port)

    def set_config(self, cfg):
        self.cfg = cfg

        from docker import Client, tls

        # base_url = None
        if 'docker' in self.cfg:
            tls_config = False
            if self.cfg['docker']['tls']:
                # https://docker-py.readthedocs.io/en/stable/tls/
                # Authenticate server based on public/default CA pool
                if not self.cfg['docker']['ca_cert'] and not self.cfg['docker']['client_cert']:
                    tls_config = tls.TLSConfig(verify=False)
                # Authenticate server based on given CA
                if self.cfg['docker']['ca_cert'] and not self.cfg['docker']['client_cert']:
                    tls_config = tls.TLSConfig(
                        ca_cert=self.cfg['docker']['ca_cert']
                        )
                # Authenticate with client certificate, do not authenticate server based on given CA
                if not self.cfg['docker']['ca_cert'] and self.cfg['docker']['client_cert']:
                    tls_config = tls.TLSConfig(
                        client_cert=(self.cfg['docker']['client_cert'], self.cfg['docker']['client_key']),
                        verify=False
                        )
                # Authenticate with client certificate, authenticate server based on given CA
                if self.cfg['docker']['ca_cert'] and self.cfg['docker']['client_cert']:
                    tls_config = tls.TLSConfig(
                        client_cert=(self.cfg['docker']['client_cert'], self.cfg['docker']['client_key']),
                        verify=self.cfg['docker']['ca_cert']
                        )
            self.docker_client = Client(base_url=self.cfg['docker']['url'], version=self.cfg['docker']['api_version'], tls=tls_config)

        else:
            self.docker_client = Client(base_url=self.cfg['docker_url'], version=self.cfg['docker_api_version'])

    def run_all_tasks(self, tasks, callback=None):
        '''
        Execute all task list on executor system, all tasks must be executed together

        NOT IMPLEMENTED, will reject all tasks

        :param tasks: list of tasks to run
        :type tasks: list
        :param callback: callback function to update tasks status (running/rejected)
        :type callback: func(running list,rejected list)
        :return: tuple of submitted and rejected/errored tasks
        '''
        self.logger.error('run_all_tasks not implemented')
        return ([], tasks)

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
            if is_array_task(task):
                # Virtual task for a task array, do not really execute
                running_tasks.append(task)
                self.logger.debug('Execute:Job:' + str(task['id']) + ':Skip:Array')
                continue
            container = None
            try:
                job = task
                port_list = []
                if 'ports' in job['requirements']:
                    port_list = job['requirements']['ports']
                if job['command']['interactive']:
                    port_list.append(22)

                # self.logger.warn('Reservation: '+str(job['requirements']['cpu'])+','+str(job['requirements']['ram'])+'g')
                vol_list = []
                for v in job['container']['volumes']:
                    if v['mount'] is None:
                        v['mount'] = v['path']
                    vol_list.append(v['mount'])

                constraints = []
                if 'label' in job['requirements'] and job['requirements']['label']:
                    for label in job['requirements']['label']:
                        constraints.append('constraint:' + label)

                vol_binds = {}
                for v in job['container']['volumes']:
                    if v['mount'] is None:
                        v['mount'] = v['path']
                    mode = 'ro'
                    if 'acl' in v and v['acl'] == 'rw':
                        mode = 'rw'
                    vol_binds[v['path']] = {
                        'bind': v['mount'],
                        'mode': mode
                    }

                job['container']['port_mapping'] = []

                networking_config = None
                container_network_name = None

                if self.network is None:
                    port_mapping = {}
                    for port in port_list:
                        if self.cfg['port_allocate']:
                            mapped_port = self.get_mapping_port('godocker-swarm', job)
                            if mapped_port is None:
                                raise Exception('no port available')
                        else:
                            mapped_port = port
                        job['container']['port_mapping'].append({'host': mapped_port, 'container': port})
                        port_mapping[port] = mapped_port
                else:
                    # Create network if necessary and set config
                    endpoint_config = self.docker_client.create_endpoint_config()
                    container_network = {}
                    container_network_name = self.network.network(job['requirements']['network'], job['user'])
                    network_status = self.network.create_network(container_network_name)
                    if not network_status:
                        raise Exception('Failed to create network %s for %s' % (job['requirements']['network'], container_network_name))
                    container_network[container_network_name] = endpoint_config
                    networking_config = self.docker_client.create_networking_config(container_network)

                if networking_config:
                    host_config = self.docker_client.create_host_config(
                                        mem_limit=str(job['requirements']['ram']) + 'g',
                                        network_mode=container_network_name,
                                        binds=vol_binds
                                        )
                    container = self.docker_client.create_container(image=job['container']['image'],
                                                                entrypoint=[job['command']['script']],
                                                                cpu_shares=job['requirements']['cpu'],
                                                                ports=port_list,
                                                                network_disabled=self.cfg['network']['disabled'],
                                                                environment=constraints,
                                                                host_config=host_config,
                                                                volumes=vol_list,
                                                                networking_config=networking_config
                                                                )
                else:
                    host_config = self.docker_client.create_host_config(
                                        mem_limit=str(job['requirements']['ram']) + 'g',
                                        network_mode='bridge',
                                        binds=vol_binds,
                                        port_bindings=port_mapping
                                        )
                    container = self.docker_client.create_container(image=job['container']['image'],
                                                                entrypoint=[job['command']['script']],
                                                                cpu_shares=job['requirements']['cpu'],
                                                                ports=port_list,
                                                                network_disabled=self.cfg['network']['disabled'],
                                                                environment=constraints,
                                                                host_config=host_config,
                                                                volumes=vol_list
                                                                )

                self.docker_client.start(container=container.get('Id'))
                job['container']['id'] = container['Id']
                job['status']['reason'] = None

                job['container']['meta'] = self.docker_client.inspect_container(container.get('Id'))
                if 'Node' not in job['container']['meta']:
                    # If using 1 Docker instance, for tests, intead of swarm,
                    # some fields are not present, or not at the same place
                    # Use required fields and place them like in swarm
                    job['container']['meta']['Node'] = {'Name': 'localhost'}

                if networking_config:
                    job['container']['ip_address'] = job['container']['meta']['NetworkSettings']['Networks'][container_network_name]['IPAddress']
                else:
                    job['container']['ip_address'] = job['container']['meta']['Node']['Name']

                if 'Config' in job['container']['meta'] and 'Labels' in job['container']['meta']['Config']:
                    # We don't need labels and some labels with dots create
                    # issue to store the information in db
                    del job['container']['meta']['Config']['Labels']

                # job['container']['meta'] = self.docker_client.inspect_container(container.get('Id'))
                running_tasks.append(job)
                self.logger.debug('Execute:Job:' + str(job['id']) + ':' + job['container']['id'])
            except Exception as e:
                self.logger.error('Execute:Job:' + str(job['id']) + ':' + str(e))
                job['status']['reason'] = str(e)
                if job['container']['meta'] is None:
                    job['container']['meta'] = {}
                if 'Node' not in job['container']['meta']:
                    job['container']['meta']['Node'] = {'Name': 'localhost'}
                error_tasks.append(job)
                if container:
                    self.docker_client.remove_container(container.get('Id'))
        return (running_tasks, error_tasks)

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
        # task['container']['stats'] = self.docker_client.stats(task['container']['id'])
        try:
            task['container']['meta'] = self.docker_client.inspect_container(task['container']['id'])
            if 'Config' in task['container']['meta'] and 'Labels' in task['container']['meta']['Config']:
                # We don't need labels and some labels with dots create
                # issue to store the information in db
                del task['container']['meta']['Config']['Labels']

            finished_date = task['container']['meta']['State']['FinishedAt']
            finished_date = iso8601.parse_date(finished_date)
        except Exception:
            self.logger.debug("Could not get container, may be already killed: " + str(task['container']['id']))
            finished_date = datetime.datetime.now()

        if finished_date.year > 1:
            over = True

        if over:
            self.logger.warn('Container:' + str(task['container']['id']) + ':Over')
            try:
                self.docker_client.remove_container(task['container']['id'])
            except Exception:
                self.logger.debug('Could not remove container ' + str(task['container']['id']))
            over = True
        else:
            self.logger.debug('Container:' + task['container']['id'] + ':Running')
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
            self.logger.debug("Could not kill container: " + str(task['container']['id']))
        try:
            self.docker_client.remove_container(task['container']['id'])
        except Exception as e:
            self.logger.debug("Could not kill/remove container: " + str(task['container']['id']))
            if e.response.status_code == 404:
                self.logger.debug('container not found, already deleted?')
                over = True
            else:
                over = False
        return (task, over)

    def suspend_task(self, task):
        '''
        Suspend/pause a task

        :param tasks: task to suspend
        :type tasks: Task
        :return: (Task, over) over is True if task could be suspended
        '''
        over = True
        try:
            self.docker_client.pause(task['container']['id'])
        except Exception as e:
            self.logger.debug(str(e))
            self.logger.debug("Could not pause container: " + task['container']['id'])
            if e.response.status_code == 404:
                over = True
            else:
                over = False

        return (task, over)

    def resume_task(self, task):
        '''
        Resume/restart a task

        :param tasks: task to resumed
        :type tasks: Task
        :return: (Task, over) over is True if task could be resumed
        '''
        over = True
        try:
            self.logger.debug("Unpause:" + str(task['id']))
            self.docker_client.unpause(task['container']['id'])
        except Exception as e:
            self.logger.debug(str(e))
            self.logger.debug("Could not pause container: " + task['container']['id'])
            if e.response.status_code == 404:
                over = True
            else:
                over = False

        return (task, over)
