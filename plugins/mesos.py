from godocker.iExecutorPlugin import IExecutorPlugin
import json
import datetime
import time
import iso8601
import os
import sys
import threading
import redis
import urllib3

from bson.json_util import dumps

from godocker.utils import is_array_child_task, is_array_task

import mesos.interface
from mesos.interface import mesos_pb2
import mesos.native

class MesosThread(threading.Thread):

    def set_driver(self, driver):
        self.driver = driver

    def run(self):
        self.driver.run()

    def stop(self):
        self.driver.stop()

class MesosScheduler(mesos.interface.Scheduler):

    def __init__(self, implicitAcknowledgements, executor):
        self.implicitAcknowledgements = implicitAcknowledgements
        self.executor = executor
        self.Terminated = False
        self.jobs_handler = None

    def features(self):
        '''
        Get supported features

        :return: list of features within ['docker-plugin-zfs']
        '''
        return ['docker-plugin-zfs']

    def set_config(self, config):
        self.config = config
        self.redis_handler = redis.StrictRedis(host=self.config['redis_host'], port=self.config['redis_port'], db=self.config['redis_db'], decode_responses=True)

    def set_logger(self, logger):
        self.logger = logger

    def registered(self, driver, frameworkId, masterInfo):
        self.logger.info("Registered with framework ID %s" % frameworkId.value)
        master_address = None
        master_ip = None
        master_port = 5050
        try:
            master_address = masterInfo.address.hostname
            master_ip = masterInfo.address.ip
            master_port = masterInfo.address.port
        except Exception:
            self.logger.warn("Address not available from master")
        if master_address is None and master_ip is None:
            try:
                master_address = masterInfo.hostname
                master_port = masterInfo.port
            except Exception:
                self.logger.warn("Could not get master address info")

        if master_ip is not None and master_address is None:
            master_address  = master_ip

        if master_address is not None:
            self.logger.info("Master hostname: "+str(master_address))
            self.logger.info("Master port: "+str(master_port))
            self.redis_handler.set(self.config['redis_prefix']+':mesos:master',
                                   master_address+':'+str(master_port))

        self.frameworkId = frameworkId.value
        self.redis_handler.set(self.config['redis_prefix']+':mesos:frameworkId',
                               self.frameworkId)
        self.redis_handler.expire(self.config['redis_prefix']+':mesos:frameworkId',
                                       3600*24*7)

    def has_enough_resource(self, offer, requested_resource, quantity):
        '''
        Checks if a resource is available and has enough slots available in offer

        :param offer: Mesos offer
        :type offer: Mesos Offer
        :param requested_resource: requested resource name as defined in mesos-slave resource (resource==gpu)
        :type requested_resource: str
        :param quantity: number of slots requested_resource
        :type quantity: int
        :return: True if resource is available in offer, else False
        '''
        available_resources = 0
        for resource in offer.resources:
            if resource.name == requested_resource:
                for mesos_range in resource.ranges.range:
                    if mesos_range.begin <= mesos_range.end:
                        available_resources += 1 + mesos_range.end - mesos_range.begin
        if available_resources >= quantity:
            return True
        else:
            return False

    def get_mapping_port(self, offer, task):
        '''
        Get a port mapping for interactive tasks

        :param task: task
        :type task: int
        :return: available port
        '''
        #port_min = self.config['port_start']
        #port_max = self.config['port_start'] + self.config['port_range']

        #if not self.redis_handler.exists(self.config['redis_prefix']+':ports:'+host):
        #    for resource in offer.resources:
        #        if resource.name == "ports":
        #            for mesos_range in resource.ranges.range:
        #                for port in range(mesos_range.end - mesos_range.begin):
        #                    self.redis_handler.rpush(self.config['redis_prefix']+':ports:'+host, mesos_range.begin + port)
        #port = self.redis_handler.lpop(self.config['redis_prefix']+':ports:'+host)

        # Get first free port
        port = None
        for resource in offer.resources:
            if resource.name == "ports":
                for mesos_range in resource.ranges.range:
                    if mesos_range.begin <= mesos_range.end:
                        port = str(mesos_range.begin)
                        mesos_range.begin += 1
                        break
        if port is None:
            return None
        self.logger.debug('Port:Give:'+task['container']['meta']['Node']['Name']+':'+str(port))
        if not 'ports' in task['container']:
            task['container']['ports'] = []
        task['container']['ports'].append(port)
        return int(port)

    def plugin_zfs_unmount(self, hostname, task):
        '''
        Unmount and delete temporary storage
        '''
        if 'plugin_zfs' not in self.config or not self.config['plugin_zfs']:
            return

        if 'tmpstorage' not in task['requirements']:
            return

        if task['requirements']['tmpstorage'] is None or task['requirements']['tmpstorage']['size'] == '':
            return

        try:
            http = urllib3.PoolManager()
            r = http.urlopen('POST', 'http://'+ hostname + ':5000/VolumeDriver.Unmount', body=json.dumps({'Name': str(task['id'])}))
            res = json.loads(r.data)
            if res['Err'] is not None or res['Err'] != '':
                r = http.urlopen('POST', 'http://'+ hostname + ':5000/VolumeDriver.Remove', body=json.dumps({'Name': str(task['id'])}))
            else:
                self.logger.error('Failed to remove zfs volume: '+str(task['id']))
        except Exception as e:
            self.logger.error('Failed to remove zfs volume: '+str(task['id']))


    def plugin_zfs_mount(self, hostname, task):
        '''
        Create and mount temporary storage
        '''
        zfs_path = None

        if 'plugin_zfs' not in self.config or not self.config['plugin_zfs']:
            return (True, None)

        if 'tmpstorage' not in task['requirements']:
            return (True, None)

        if task['requirements']['tmpstorage'] is None or task['requirements']['tmpstorage']['size'] == '':
            return (True, None)

        try:
            http = urllib3.PoolManager()
            r = None
            activated = self.redis_handler.get(self.config['redis_prefix']+':plugins:zfs:'+hostname)
            if activated is None:
                http.urlopen('GET', 'http://' + hostname + ':5000/Plugin.Activate')
                self.redis_handler.set(self.config['redis_prefix']+':plugins:zfs:'+ hostname,"plugin-zfs")
            r = http.urlopen('POST', 'http://'+ hostname + ':5000/VolumeDriver.Create', body=json.dumps({'Name': str(task['id']), 'Opts': {'size': str(task['requirements']['tmpstorage']['size'])}}))
            if r.status == 200:
                r = http.urlopen('POST', 'http://'+ hostname + ':5000/VolumeDriver.Mount', body=json.dumps({'Name': str(task['id'])}))
                res = json.loads(r.data)
                if res['Err'] is not None:
                    return (False, None)
                r = http.urlopen('POST', 'http://'+ hostname + ':5000/VolumeDriver.Path', body=json.dumps({'Name': str(task['id'])}))
                res = json.loads(r.data)
                zfs_path = res['Name']
            else:
                self.logger.error("Failed to resource plugin-zfs")
                return (False, None)
        except Exception as e:
            self.logger.error("Failed to resource plugin-zfs:"+str(e))
            return (False, None)
        return (True, zfs_path)

    def resourceOffers(self, driver, offers):
        '''
        Basic placement strategy (loop over offers and try to push as possible)
        '''
        if self.Terminated:
            self.logger.info("Stop requested")
            driver.stop()
            return

        self.logger.debug('Mesos:Offers:Kill:Begin')
        redis_task_id = self.redis_handler.lpop(self.config['redis_prefix']+':mesos:kill')
        while redis_task_id is not None:
            is_over = self.redis_handler.get(self.config['redis_prefix']+':mesos:over:'+redis_task_id)
            if is_over is not None:
                task_id = mesos_pb2.TaskID()
                task_id.value = redis_task_id
                self.logger.debug('Mesos:Offers:Kill:Task:'+redis_task_id)
                driver.killTask(task_id)
            redis_task_id = self.redis_handler.lpop(self.config['redis_prefix']+':mesos:kill')
        self.logger.debug('Mesos:Offers:Kill:End')

        self.logger.debug('Mesos:Offers:Begin')
        # Get tasks
        tasks = []
        redis_task = self.redis_handler.lpop(self.config['redis_prefix']+':mesos:pending')
        while redis_task is not None:
            task = json.loads(redis_task)
            task['mesos_offer'] = False
            tasks.append(task)
            redis_task = self.redis_handler.lpop(self.config['redis_prefix']+':mesos:pending')

        for offer in offers:
            if not tasks:
                self.logger.debug('Mesos:Offer:NoTask')
                driver.declineOffer(offer.id)
                continue
            offer_tasks = []
            offerCpus = 0
            offerMem = 0
            labels = {}
            for resource in offer.resources:
                if resource.name == "cpus":
                    offerCpus += resource.scalar.value
                elif resource.name == "mem":
                    offerMem += resource.scalar.value

            for attr in offer.attributes:
                if attr.type == 3:
                    labels[attr.name] = attr.text.value
            self.logger.debug("Mesos:Labels:"+str(labels))
            if 'hostname' not in labels:
                self.logger.error('Mesos:Error:Configuration: missing label hostname')

            self.logger.debug("Mesos:Received offer %s with cpus: %s and mem: %s" \
                  % (offer.id.value, offerCpus, offerMem))
            for task in tasks:
                if not task['mesos_offer'] and task['requirements']['cpu'] <= offerCpus and task['requirements']['ram']*1000 <= offerMem:
                    # check for reservation constraints, if any
                    self.logger.debug("Try to place task "+str(task['id']))
                    if 'reservation' in labels:
                        self.logger.debug("Node has reservation")
                        reservations = labels['reservation'].split(',')
                        offer_hostname = "undefined"
                        if 'hostname' in labels:
                            offer_hostname = labels['hostname']
                        self.logger.debug("Check reservation for "+ offer_hostname)
                        if task['user']['id'] not in reservations and task['user']['project'] not in reservations:
                            self.logger.debug("User "+task['user']['id']+" not allowed to execute on "+ offer_hostname)
                            continue

                    # check for resources
                    if 'label' in task['requirements'] and task['requirements']['label']:
                        task['requirements']['resources'] = {}
                        for task_resource in task['requirements']['label']:
                            if not task_resource.startswith('resource=='):
                                continue
                            requested_resource = task_resource.split('==')
                            requested_resource = requested_resource[1]
                            if requested_resource not in task['requirements']['resources']:
                                task['requirements']['resources'][requested_resource] = 1
                            else:
                                task['requirements']['resources'][requested_resource] += 1
                        # check if enough resources
                        has_enough_resources = True
                        for requested_resource in task['requirements']['resources']:
                            quantity = task['requirements']['resources'][requested_resource]
                            if not self.has_enough_resource(offer, requested_resource, quantity):
                                self.logger.debug('Not enough '+requested_resource+' on this node')
                                has_enough_resources = False
                                break
                        if not has_enough_resources:
                            self.logger.debug("Not enough specific resources for task "+str(task['id']))
                            del task['requirements']['resources']
                            continue

                    # check for label constraints, if any
                    if 'label' in task['requirements'] and task['requirements']['label']:
                        is_ok = True
                        for req in task['requirements']['label']:
                            reqlabel = req.split('==')
                            if reqlabel[0] == 'resource':
                                continue

                            if reqlabel[0] not in labels or reqlabel[1] != labels[reqlabel[0]]:
                                is_ok = False
                                break
                        if not is_ok:
                            self.logger.debug("Label requirements do not match for task "+str(task['id']))
                            continue

                    (res, zfs_path) = self.plugin_zfs_mount(labels['hostname'], task)
                    if not res:
                        self.logger.debug("Zfs mount not possible for task "+str(task['id']))
                        continue
                    else:
                        if zfs_path is not None:
                            task['requirements']['tmpstorage']['path'] = zfs_path
                        else:
                            if task['requirements']['tmpstorage'] is not None:
                                task['requirements']['tmpstorage']['path'] = None
                            else:
                                task['requirements']['tmpstorage'] = { 'path': None, 'size': ''}

                    new_task = self.new_task(offer, task, labels)
                    if new_task is None:
                        self.logger.debug('Mesos:Task:Error:Failed to create new task '+str(task['id']))
                        continue
                    offer_tasks.append(new_task)
                    offerCpus -= task['requirements']['cpu']
                    offerMem -= task['requirements']['ram']*1000
                    task['mesos_offer'] = True
                    self.logger.debug('Mesos:Task:Running:'+str(task['id']))
                    self.redis_handler.rpush(self.config['redis_prefix']+':mesos:running', dumps(task))
                    self.redis_handler.set(self.config['redis_prefix']+':mesos:over:'+str(task['id']),0)
            driver.launchTasks(offer.id, offer_tasks)
            #tasks = [self.new_task(offer)]
        for task in tasks:
            if not task['mesos_offer']:
                self.logger.debug('Mesos:Task:Rejected:'+str(task['id']))
                self.redis_handler.rpush(self.config['redis_prefix']+':mesos:rejected', dumps(task))
            #driver.launchTasks(offer.id, tasks)
            #driver.declineOffer(offer.id)
        if tasks:
            self.redis_handler.set(self.config['redis_prefix']+':mesos:offer', 1)
        self.logger.debug('Mesos:Offers:End')

    def new_task(self, offer, job, labels=None):
        '''
        Creates a task for mesos
        '''
        task = mesos_pb2.TaskInfo()
        container = mesos_pb2.ContainerInfo()
        container.type = 1 # mesos_pb2.ContainerInfo.Type.DOCKER

        # Reserve requested resource and mount related volumes
        if 'resources' in job['requirements'] and job['requirements']['resources']:
            for requested_resource in job['requirements']['resources']:
                quantity = job['requirements']['resources'][requested_resource]
                mesos_resources = task.resources.add()
                mesos_resources.name = requested_resource
                mesos_resources.type = mesos_pb2.Value.RANGES
                for resource in offer.resources:
                    if resource.name == requested_resource and quantity > 0:
                        for mesos_range in resource.ranges.range:
                            if mesos_range.begin <= mesos_range.end:
                                if (1 + mesos_range.end - mesos_range.begin >= quantity):
                                    # take what is necessary
                                    mesos_resource = mesos_resources.ranges.range.add()
                                    mesos_resource.begin = mesos_range.begin
                                    mesos_resource.end = mesos_range.begin + quantity - 1
                                    mesos_range.begin  = quantity
                                    quantity = 0
                                else:
                                    # take what is available
                                    mesos_resource = mesos_resources.ranges.range.add()
                                    mesos_resource.begin = mesos_range.begin
                                    mesos_resource.end = mesos_range.begin + (mesos_range.end - mesos_range.begin)
                                    mesos_range.begin += 1 + mesos_range.end - mesos_range.begin
                                    quantity -= 1 + mesos_range.end - mesos_range.begin
                                self.logger.debug("Take resources: "+str(mesos_resource.begin)+"-"+str(mesos_resource.end))
            for mesos_range in mesos_resources.ranges.range:
                for res_range in range(mesos_range.begin,mesos_range.end + 1):
                    resource_volume_id = mesos_resources.name+"_"+str(res_range)
                    self.logger.debug("Add volumes for resource "+resource_volume_id)
                    if resource_volume_id in labels:
                        resource_volumes = labels[resource_volume_id].split(',')
                        for resource_volume in resource_volumes:
                            volume = container.volumes.add()
                            self.logger.debug("Add volume for resource: " + resource_volume)
                            volume.container_path = resource_volume
                            volume.host_path = resource_volume
                            volume.mode = 1
            del job['requirements']['resources']

        dockercfg = None

        for v in job['container']['volumes']:
            if v['mount'] is None:
                v['mount'] = v['path']
            volume = container.volumes.add()
            volume.container_path = v['mount']
            volume.host_path = v['path']
            if v['acl'] == 'rw':
                volume.mode = 1 # mesos_pb2.Volume.Mode.RW
            else:
                volume.mode = 2 # mesos_pb2.Volume.Mode.RO
            if v['name'] == 'home':
                if os.path.exists(os.path.join(v['path'],'docker.tar.gz')):
                    self.logger.debug('Add .dockercfg ' + os.path.join(v['path'],'docker.tar.gz'))
                    dockercfg = os.path.join(v['path'],'docker.tar.gz')

        if job['requirements']['tmpstorage']['path'] is not None:
            volume = container.volumes.add()
            volume.container_path = '/tmp-data'
            volume.host_path = job['requirements']['tmpstorage']['path']
            volume.mode = 1

        tid = str(job['id'])

        command = mesos_pb2.CommandInfo()
        command.value = job['command']['script']
        if dockercfg:
            dockerconfig = command.uris.add()
            dockerconfig.value = dockercfg
            #dockerconfig.output_file = ".dockercfg"

        task.command.MergeFrom(command)
        task.task_id.value = tid
        task.slave_id.value = offer.slave_id.value
        task.name = job['meta']['name']

        cpus = task.resources.add()
        cpus.name = "cpus"
        cpus.type = mesos_pb2.Value.SCALAR
        cpus.scalar.value = job['requirements']['cpu']

        mem = task.resources.add()
        mem.name = "mem"
        mem.type = mesos_pb2.Value.SCALAR
        mem.scalar.value = job['requirements']['ram']*1000

        if 'meta' not in job['container'] or job['container']['meta'] is None:
            job['container']['meta'] = {}
        if 'Node' not in job['container']['meta'] or job['container']['meta']['Node'] is None:
            job['container']['meta']['Node'] = {}
        job['container']['meta']['Node']['slave'] = offer.slave_id.value
        if labels is not None and 'hostname' in labels:
            job['container']['meta']['Node']['Name'] = labels['hostname']
        else:
            job['container']['meta']['Node']['Name'] = offer.slave_id.value
        self.logger.debug("Task placed on host "+str(job['container']['meta']['Node']['Name']))

        docker = mesos_pb2.ContainerInfo.DockerInfo()
        docker.image = job['container']['image']
        docker.network = 2 # mesos_pb2.ContainerInfo.DockerInfo.Network.BRIDGE
        docker.force_pull_image = True

        port_list = []
        job['container']['port_mapping'] = []
        if 'ports' in job['requirements']:
            port_list = job['requirements']['ports']
        if job['command']['interactive']:
            port_list.append(22)
        if port_list:
            mesos_ports = task.resources.add()
            mesos_ports.name = "ports"
            mesos_ports.type = mesos_pb2.Value.RANGES
            for port in port_list:
                if self.config['port_allocate']:
                    mapped_port = self.get_mapping_port(offer, job)
                    if mapped_port is None:
                        return None
                else:
                    mapped_port = port
                job['container']['port_mapping'].append({'host': mapped_port, 'container': port})
                docker_port = docker.port_mappings.add()
                docker_port.host_port = mapped_port
                docker_port.container_port = port
                port_range = mesos_ports.ranges.range.add()
                port_range.begin = mapped_port
                port_range.end = mapped_port
        container.docker.MergeFrom(docker)
        task.container.MergeFrom(container)
        return task


    def statusUpdate(self, driver, update):
        self.logger.debug("Task %s is in state %s" % \
            (update.task_id.value, mesos_pb2.TaskState.Name(update.state)))

        if update.state == 1:
            #Switched to RUNNING, get container id
            job = self.jobs_handler.find_one({'id': int(update.task_id.value)})

            #Switched to RUNNING, get container id
            containerId = None
            try:
                if str(update.data) != "":
                    containers = json.loads(update.data)
                    containerId = str(containers[0]["Name"]).split(".")
                    containerId = "mesos-"+containerId[1]
                    self.jobs_handler.update({'id': int(update.task_id.value)},{'$set': {'container.id': container}})

            except Exception as e:
                self.logger.debug("Could not extract container id from TaskStatus")
                containerId = None

            # Mesos <= 0.22, container id is not in TaskStatus, let's query mesos
            if containerId is None:
                http = urllib3.PoolManager()
                r = None
                try:
                    r = http.urlopen('GET', 'http://'+job['container']['meta']['Node']['Name']+':5051/slave(1)/state.json')

                    if r.status == 200:
                        slave = json.loads(r.data)
                        for f in slave['frameworks']:
                            if f['name'] == "Go-Docker Mesos":
                                for executor in f['executors']:
                                    if str(executor['id']) == str(update.task_id.value):
                                        container = 'mesos-'+executor['container']
                                        self.jobs_handler.update({'id': int(update.task_id.value)},{'$set': {'container.id': container}})
                                        break
                                break
                except Exception as e:
                    self.logger.error('Failed to contact mesos slave: '+str(e))

        self.logger.debug('Mesos:Task:Over:'+str(update.task_id.value))
        if int(update.state) in [2,3,4,5,7]:
            job = self.jobs_handler.find_one({'id': int(update.task_id.value)})
            if job is not None and 'meta' in job['container'] and job['container']['meta'] is not None and 'Node' in job['container']['meta']:
                self.plugin_zfs_unmount(job['container']['meta']['Node']['Name'], job)


        if update.reason:
            self.redis_handler.set(self.config['redis_prefix']+':mesos:over:'+str(update.task_id.value)+':reason',update.reason)
        self.redis_handler.set(self.config['redis_prefix']+':mesos:over:'+str(update.task_id.value),update.state)

    def frameworkMessage(self, driver, executorId, slaveId, message):
        self.logger.debug("Received framework message")

class Mesos(IExecutorPlugin):
    def get_name(self):
        return "mesos"

    def get_type(self):
        return "Executor"

    def features(self):
        '''
        Get supported features

        :return: list of features within ['kill', 'pause','resources.port']
        '''
        return ['kill', 'resources.port']

    def set_config(self, cfg):
        self.cfg = cfg
        self.Terminated = False
        self.driver = None
        self.redis_handler = redis.StrictRedis(host=self.cfg['redis_host'], port=self.cfg['redis_port'], db=self.cfg['redis_db'], decode_responses=True)


    def open(self, proc_type):
        '''
        Request start of executor if needed
        '''
        #self.mesosthread = MesosThread()
        #self.mesosthread.set_driver(self.driver)
        #self.mesosthread.start()
        if proc_type is not None and proc_type ==1:
            # do not start framework on watchers
            return

        executor = mesos_pb2.ExecutorInfo()
        executor.executor_id.value = "go-docker"
        #executor.command.value = "/bin/echo hello # $MESOS_SANDBOX #"
        executor.name = "Go-Docker executor"

        framework = mesos_pb2.FrameworkInfo()
        framework.user = "" # Have Mesos fill in the current user.
        framework.name = "Go-Docker Mesos"
        framework.failover_timeout = 3600 * 24*7 # 1 week
        frameworkId = self.redis_handler.get(self.cfg['redis_prefix']+':mesos:frameworkId')
        if frameworkId:
            # Reuse previous framework identifier
            mesos_framework_id = mesos_pb2.FrameworkID()
            mesos_framework_id.value = frameworkId
            framework.id.MergeFrom(mesos_framework_id)

        if os.getenv("MESOS_CHECKPOINT"):
            self.logger.info("Enabling checkpoint for the framework")
            framework.checkpoint = True

        implicitAcknowledgements = 1
        if os.getenv("MESOS_EXPLICIT_ACKNOWLEDGEMENTS"):
            self.logger.info("Enabling explicit status update acknowledgements")
            implicitAcknowledgements = 0

        driver = None
        if os.getenv("MESOS_AUTHENTICATE"):
            self.logger.info("Enabling authentication for the framework")
            if not os.getenv("DEFAULT_PRINCIPAL"):
                self.logger.error("Expecting authentication principal in the environment")
                sys.exit(1);

            if not os.getenv("DEFAULT_SECRET"):
                self.logger.error("Expecting authentication secret in the environment")
                sys.exit(1);

            credential = mesos_pb2.Credential()
            credential.principal = os.getenv("DEFAULT_PRINCIPAL")
            credential.secret = os.getenv("DEFAULT_SECRET")

            framework.principal = os.getenv("DEFAULT_PRINCIPAL")

            mesosScheduler = MesosScheduler(implicitAcknowledgements, executor)
            mesosScheduler.set_logger(self.logger)
            mesosScheduler.set_config(self.cfg)
            mesosScheduler.jobs_handler = self.jobs_handler

            driver = mesos.native.MesosSchedulerDriver(
                mesosScheduler,
                framework,
                self.cfg['mesos_master'],
                credential)
        else:
            framework.principal = "godocker-mesos-framework"
            mesosScheduler = MesosScheduler(implicitAcknowledgements, executor)
            mesosScheduler.set_logger(self.logger)
            mesosScheduler.set_config(self.cfg)
            mesosScheduler.jobs_handler = self.jobs_handler
            driver = mesos.native.MesosSchedulerDriver(
                mesosScheduler,
                framework,
                self.cfg['mesos_master'])

        self.driver = driver
        self.driver.start()

    def close(self):
        '''
        Request end of executor if needed
        '''
        #if self.mesosthread.isAlive():
        #    self.mesosthread.stop()
        if self.driver is not None:
            self.driver.stop(True)
        self.Terminated = True

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
        return ([],tasks)

    def run_tasks(self, tasks, callback=None):
        '''
        Execute task list on executor system

        :param tasks: list of tasks to run
        :type tasks: list
        :param callback: callback function to update tasks status (running/rejected)
        :type callback: func(running list,rejected list)
        :return: tuple of submitted and rejected/errored tasks
        '''
        # Add tasks in redis to be managed by mesos
        self.redis_handler.set(self.cfg['redis_prefix']+':mesos:offer', 0)
        for task in tasks:
            self.redis_handler.rpush(self.cfg['redis_prefix']+':mesos:pending', dumps(task))
        # Wait for offer receival and treatment
        self.logger.debug('Mesos:WaitForOffer:Begin')
        mesos_offer = int(self.redis_handler.get(self.cfg['redis_prefix']+':mesos:offer'))
        while mesos_offer != 1 and not self.Terminated:
            self.logger.debug('Mesos:WaitForOffer:Wait')
            time.sleep(1)
            mesos_offer = int(self.redis_handler.get(self.cfg['redis_prefix']+':mesos:offer'))
        self.logger.debug('Mesos:WaitForOffer:End')
        # Get result
        rejected_tasks = []
        running_tasks = []
        redis_task = self.redis_handler.lpop(self.cfg['redis_prefix']+':mesos:running')
        while redis_task is not None:
            task = json.loads(redis_task)
            running_tasks.append(task)
            redis_task = self.redis_handler.lpop(self.cfg['redis_prefix']+':mesos:running')
        redis_task = self.redis_handler.lpop(self.cfg['redis_prefix']+':mesos:rejected')
        while redis_task is not None:
            task = json.loads(redis_task)
            rejected_tasks.append(task)
            redis_task = self.redis_handler.lpop(self.cfg['redis_prefix']+':mesos:rejected')

        return (running_tasks,rejected_tasks)

    def watch_tasks(self, task):
        '''
        Get task status

        :param task: current task
        :type task: Task
        :param over: is task over
        :type over: bool
        '''
        self.logger.debug('Mesos:Task:Check:Running:'+str(task['id']))
        mesos_task = self.redis_handler.get(self.cfg['redis_prefix']+':mesos:over:'+str(task['id']))
        if mesos_task is not None and int(mesos_task) in [2,3,4,5,7]:
            self.logger.debug('Mesos:Task:Check:IsOver:'+str(task['id']))
            exit_code = int(mesos_task)
            if 'State' not in task['container']['meta']:
                task['container']['meta']['State'] = {}
            if exit_code == 2:
                task['container']['meta']['State']['ExitCode'] = 0
            elif exit_code == 4:
                task['container']['meta']['State']['ExitCode'] = 137
            else:
                task['container']['meta']['State']['ExitCode'] = 1
            if int(mesos_task) in [3,5,7]:
                reason = self.redis_handler.get(self.cfg['redis_prefix']+':mesos:over:'+str(task['id'])+':reason')
                if not reason:
                    reason = 'Unknown'
                task['status']['reason'] = 'System crashed or failed to start the task: ' + str(reason)
            self.redis_handler.delete(self.cfg['redis_prefix']+':mesos:over:'+str(task['id']))
            self.redis_handler.delete(self.cfg['redis_prefix']+':mesos:over:'+str(task['id'])+':reason')
            return (task, True)
        else:
            self.logger.debug('Mesos:Task:Check:IsRunning:'+str(task['id']))
            return (task,False)


    def kill_task(self, task):
        '''
        Kills a running task

        :param tasks: task to kill
        :type tasks: Task
        :return: (Task, over) over is True if task could be killed
        '''
        self.logger.debug('Mesos:Task:Kill:Check:'+str(task['id']))
        mesos_task = self.redis_handler.get(self.cfg['redis_prefix']+':mesos:over:'+str(task['id']))
        if mesos_task is not None and int(mesos_task) in [2,3,4,5,7]:
            self.logger.debug('Mesos:Task:Kill:IsOver:'+str(task['id']))
            exit_code = int(mesos_task)
            if 'State' not in task['container']['meta']:
                task['container']['meta']['State'] = {}
            if exit_code == 2:
                task['container']['meta']['State']['ExitCode'] = 0
            elif exit_code == 4:
                task['container']['meta']['State']['ExitCode'] = 137
            else:
                task['container']['meta']['State']['ExitCode'] = 1
            self.redis_handler.delete(self.cfg['redis_prefix']+':mesos:over:'+str(task['id']))
            self.redis_handler.set(self.cfg['redis_prefix']+':mesos:kill_pending:'+str(task['id']), 1)
            return (task, True)
        else:
            self.logger.debug('Mesos:Task:Kill:IsRunning:'+str(task['id']))
            if self.redis_handler.get(self.cfg['redis_prefix']+':mesos:kill_pending:'+str(task['id'])) is None:
                self.redis_handler.rpush(self.cfg['redis_prefix']+':mesos:kill', str(task['id']))
                self.redis_handler.set(self.cfg['redis_prefix']+':mesos:kill_pending:'+str(task['id']), 1)
            return (task, None)


        return (task, True)


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
        mesos_master = self.redis_handler.get(self.cfg['redis_prefix']+':mesos:master')
        if not mesos_master:
            return []

        http = urllib3.PoolManager()
        r = http.urlopen('GET', 'http://' + mesos_master + '/master/state.json')
        master = json.loads(r.data)

        slaves = []
        for slave in master['slaves']:
            if slave['active']:
                r = http.urlopen('GET', 'http://'+slave['hostname']+':5051/metrics/snapshot')
                state = json.loads(r.data)
                slaves.append({
                    'name': slave['hostname'],
                    'cpu': (int(state['slave/cpus_used']), int(state['slave/cpus_total'])),
                    'mem': (int(state['slave/mem_used']), int(state['slave/mem_total'])),
                    'disk': (int(state['slave/disk_used']), int(state['slave/disk_total']))
                })
        return slaves
