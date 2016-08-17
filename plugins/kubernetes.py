from godocker.iExecutorPlugin import IExecutorPlugin
import json
import strict_rfc3339
import humanfriendly
import requests
from godocker.utils import is_array_task, STATUS_PENDING, STATUS_SECONDARY_SCHEDULER_REJECTED


class Kubernetes(IExecutorPlugin):
    def get_name(self):
        return "kubernetes"

    def get_type(self):
        return "Executor"

    def features(self):
        '''
        Get supported features

        :return: list of features within ['kill', 'pause']
        '''
        return ['kill', 'resources.port']

    def set_config(self, cfg):
        self.cfg = cfg

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
        headers = self._headers()

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
                job['container']['port_mapping'] = []
                if 'ports' in job['requirements']:
                    port_list = job['requirements']['ports']
                if job['command']['interactive']:
                    port_list.append(22)
                for port in port_list:
                    job['container']['port_mapping'].append({'host': port, 'container': port})

                vol_list = []
                for v in job['container']['volumes']:
                    if v['mount'] is None:
                        v['mount'] = v['path']
                    vol_list.append(v['mount'])
                constraints = []
                if 'label' in job['requirements'] and job['requirements']['label']:
                    for label in job['requirements']['label']:
                        constraints.append('constraint:' + label)

                if not job['container']['meta']:
                    job['container']['meta'] = {}
                if 'Node' not in job['container']['meta']:
                    # If using 1 Docker instance, for tests, intead of swarm,
                    # some fields are not present, or not at the same place
                    # Use required fields and place them like in swarm
                    job['container']['meta']['Node'] = {'Name': 'localhost'}

                if 'Config' in job['container']['meta'] and 'Labels' in job['container']['meta']['Config']:
                    # We don't need labels and some labels with dots create
                    # issue to store the information in db
                    del job['container']['meta']['Config']['Labels']

                vol_binds = {}
                for v in job['container']['volumes']:
                    if v['mount'] is None:
                        v['mount'] = v['path']
                    ro = True
                    if 'acl' in v and v['acl'] == 'rw':
                        ro = False
                    vol_binds[v['path']] = {
                        'bind': v['mount'],
                        'ro': ro,
                        'name': v['name']
                    }

                container_id = self._get_pod_id(job['id'])
                pod = {
                  "apiVersion": "v1",
                  "kind": "Pod",
                  "metadata": {
                    "name": str(container_id),
                    "labels": {}
                  },
                  "spec": {
                    "restartPolicy": "Never",
                    "containers": [
                      {
                        "name": container_id,
                        "image": job['container']['image'],
                        "imagePullPolicy": 'Always',
                        "env": [],
                        "command": [job['command']['script']],
                        "ports": [],
                        "volumeMounts": [],
                        "resources": {
                          "limits": {
                              "memory": str(job['requirements']['ram']) + 'Gi',
                              "cpu": str(job['requirements']['cpu'] * 1000) + "m"
                          }
                        }
                      }
                    ],
                    "volumes": []
                  }
                }
                for port in port_list:
                    pod['spec']['containers'][0]['ports'].append(
                                              {
                                                "containerPort": port
                                              }
                    )
                    job['container']['ports'].append(port)

                for vol_path in vol_binds:
                    vol = vol_binds[vol_path]
                    pod['spec']['containers'][0]['volumeMounts'].append({
                        "name": vol['name'],
                        "mountPath": vol['bind'],
                        "readOnly": vol['ro']
                    })
                    pod['spec']['volumes'].append({
                        "name": vol['name'],
                        "hostPath": {
                            "path": vol_path
                        }
                    })
                # Tmp dir, size is not controlled
                if job['requirements']['tmpstorage'] and job['requirements']['tmpstorage']['path'] is not None:
                    pod['spec']['containers'][0]['volumeMounts'].append({
                                            "name": 'tmp-data',
                                            "mountPath": '/tmp-data',
                                            "readOnly": False
                    })
                    pod['spec']['volumes'].append({
                        "name": 'tmp-data',
                        "emptyDir": {}
                    })

                # Node selection based on constraints
                if 'label' in job['requirements'] and job['requirements']['label']:
                    pod['spec']['nodeSelector'] = {}
                    for label in job['requirements']['label']:
                        constraint = label.split('==')
                        pod['spec']['nodeSelector'][constraint[0]] = constraint[1]

                self.logger.debug('Kube pod: ' + str(pod))
                r = requests.post('http://localhost:8080/api/v1/namespaces/default/pods', data=json.dumps(pod))
                kube_request = r.json()
                kube_ok = True
                if r.status_code != requests.codes.ok and r.status_code != 201:
                    kube_ok = False
                status = kube_request['status']['phase']
                job['status']['override'] = True
                job['status']['secondary'] = status
                job['status']['reason'] = None
                if status == 'Failed' or status == 'Unknown':
                    kube_ok = False
                    if 'message' in kube_request['status']:
                        job['status']['reason'] = kube_request['status']['message']
                        self.logger.error('Execute:Job:' + str(job['id']) + ':' + str(kube_request['status']['message']))
                    else:
                        self.logger.error('Execute:Job:' + str(job['id']) + ':' + str(status))
                if kube_ok:
                    job['container']['id'] = container_id
                    running_tasks.append(job)
                    self.logger.debug('Execute:Job:' + str(job['id']) + ':' + job['container']['id'])
            except Exception as e:
                self.logger.error('Execute:Job:' + str(job['id']) + ':' + str(e))
                if job['container']['meta'] is None:
                    job['container']['meta'] = {}
                if 'Node' not in job['container']['meta']:
                    job['container']['meta']['Node'] = {'Name': 'localhost'}
                error_tasks.append(job)
                if container:
                    headers = self._headers()
                    pod_id = self._get_pod_id(task['id'])
                    namespace = self._get_namespace()
                    r = requests.delete(self.cfg['kube_server'] + '/api/v1/namespaces/' + namespace + '/pods/' + pod_id, headers=headers)
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
        # finished_date = None
        headers = self._headers()
        pod_id = self._get_pod_id(task['id'])
        namespace = self._get_namespace()

        try:
            r = requests.get(self.cfg['kube_server'] + '/api/v1/namespaces/' + namespace + '/pods/' + pod_id, headers=headers)

            if r.status_code != requests.codes.ok:
                self.logger.debug("Could not get container, may be already killed: " + str(task['container']['id']))
                return (task, over)

            kube_status = r.json()

            if kube_status['status']['phase'] == 'Pending':
                # ? still pending ? check if scheduling issue
                container_id = self._get_pod_id(task['id'])
                data = {'fieldSelector': 'involvedObject.name=' + container_id}
                r = requests.get(self.cfg['kube_server'] + '/api/v1/namespaces/default/events', params=data, headers=headers)
                if r.status_code != requests.codes.ok:
                    self.logger.debug('Failed to get events for ' + container_id + ', scheduler may not have yet processed task')
                events = r.json()
                for event in events['items']:
                    if event['reason'] == 'FailedScheduling':
                        # Not enough resources, set as rescheduled
                        requests.delete(self.cfg['kube_server'] + '/api/v1/namespaces/' + namespace + '/pods/' + pod_id, headers=headers)
                        self.jobs_handler.update({
                                                'id': task['id']
                                                }, {
                                                '$set': {
                                                    'requirements.ticket_share': task['requirements']['ticket_share'],
                                                    'status.primary': STATUS_PENDING,
                                                    'status.secondary': STATUS_SECONDARY_SCHEDULER_REJECTED,
                                                    'status.reason': event['message'],
                                                    'container.ports': []
                                                    }
                                                })
                        # Drop from running, set back to pending
                        return (None, False)

            task['status']['date_running'] = strict_rfc3339.rfc3339_to_timestamp(kube_status['status']['startTime'])
            if kube_status['status']['phase'] in ['Succeeded', 'Failed', 'Unknown']:
                over = True
                reason = kube_status['status']['containerStatuses'][0]['state']['terminated']['reason']

                if kube_status['status']['phase'] in ['Failed', 'Unknown']:
                    node_name = None
                    if 'Node' in task['container']['meta'] and 'Name' in task['container']['meta']['Node']:
                        node_name = task['container']['meta']['Node']['Name']
                    if 'failure' not in task['status']:
                        task['status']['failure'] = {'reason': reason, 'nodes': []}
                    if node_name:
                        task['status']['failure']['nodes'].append(node_name)

                if 'State' not in task['container']['meta']:
                    task['container']['meta']['State'] = {}
                task['container']['meta']['State']['ExitCode'] = kube_status['status']['containerStatuses'][0]['state']['terminated']['exitCode']
                task['status']['reason'] = reason

                task['status']['date_running'] = strict_rfc3339.rfc3339_to_timestamp(kube_status['status']['containerStatuses'][0]['state']['terminated']['startedAt'])
                task['status']['date_over'] = strict_rfc3339.rfc3339_to_timestamp(kube_status['status']['containerStatuses'][0]['state']['terminated']['finishedAt'])

            update = None
            new_status = False
            if task['status']['secondary'] != kube_status['status']['phase']:
                update = {'status.secondary': kube_status['status']['phase']}
                new_status = True
            task['status']['secondary'] = kube_status['status']['phase']

            container_id = None
            if kube_status['status']['phase'] == 'Running' and new_status:
                if 'containerId' in kube_status['status']['containerStatuses'][0]:
                    container_id = kube_status['status']['containerStatuses'][0]['containerID']
                if container_id:
                    task['container']['id'] = container_id.replace('docker://', '')
                if not update:
                    update = {}
                update['container.id'] = task['container']['id']
                if kube_status['status']['hostIP']:
                    task['container']['meta']['Node'] = {'Name': kube_status['status']['podIP']}
                    update['container.meta.Node'] = task['container']['meta']['Node']

            if update is not None:
                self.jobs_handler.update({'id': task['id']}, {'$set': update})

        except Exception as e:
            self.logger.debug("Could not get container, may be already killed: " + str(task['container']['id']) + ", " + str(e))

        if over:
            self.logger.warn('Container:' + str(task['container']['id']) + ':Over')
            try:
                r = requests.delete(self.cfg['kube_server'] + '/api/v1/namespaces/' + namespace + '/pods/' + pod_id, headers=headers)
            except Exception:
                self.logger.debug('Could not remove container ' + str(task['container']['id']))
            over = True
        else:
            self.logger.debug('Container:' + task['container']['id'] + ':Running')
        return (task, over)

    def _get_pod_id(self, id):
        return 'god-' + str(id)

    def _get_namespace(self):
        namespace = 'default'
        if 'kube_namespace' in self.cfg and self.cfg['kube_namespace']:
            namespace = self.cfg['kube_namespace']
        return namespace

    def _headers(self):
        headers = {}
        if self.cfg['kube_token']:
            headers['Authorization'] = 'Bearer ' + str(self.cfg['kube_token'])
        return headers

    def kill_task(self, task):
        '''
        Kills a running task

        :param tasks: task to kill
        :type tasks: Task
        :return: (Task, over) over is True if task could be killed
        '''
        over = True
        if not self.cfg['kube_server']:
            self.logger.error('Kubernetes not configured')
            return (task, False)
        try:
            headers = self._headers()
            pod_id = self._get_pod_id(task['id'])
            namespace = self._get_namespace()
            r = requests.delete(self.cfg['kube_server'] + '/api/v1/namespaces/' + namespace + '/pods/' + pod_id, headers=headers)
            if r.status_code == 404:
                over = True
            elif r.status_code != requests.codes.ok:
                self.logger.debug('Error from Kubernetes, return code: ' + r.status_code)
                over = False
        except Exception as e:
            self.logger.debug("Could not kill container: " + str(task['container']['id']) + " - " + str(e))
            over = False
        return (task, over)

    def suspend_task(self, task):
        '''
        Suspend/pause a task

        :param tasks: task to suspend
        :type tasks: Task
        :return: (Task, over) over is True if task could be suspended
        '''
        self.logger.error('Not supported')
        return (task, False)

    def resume_task(self, task):
        '''
        Resume/restart a task

        :param tasks: task to resumed
        :type tasks: Task
        :return: (Task, over) over is True if task could be resumed
        '''
        self.logger.error('Not supported')
        return (task, False)

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
        headers = self._headers()
        r = requests.get(self.cfg['kube_server'] + '/api/v1/nodes', headers=headers)
        if r.status_code != requests.codes.ok:
            self.logger.error('Failed to get status from Kubernetes')
            return []
        slaves = []
        kub_nodes = r.json()
        for slave in kub_nodes['items']:
            available_memory = humanfriendly.parse_size(slave['status']['allocatable']['memory'])
            total_memory = humanfriendly.parse_size(slave['status']['capacity']['memory'])
            slaves.append({
                    'name': slave['status']['nodeInfo']['machineID'],
                    'cpu': (int(slave['status']['capacity']['cpu']) - int(slave['status']['allocatable']['cpu']), int(slave['status']['capacity']['cpu'])),
                    'mem': (total_memory - available_memory, total_memory),
                    'disk': (0, 0)
            })

        return slaves
