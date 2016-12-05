import re
import os
import socket
import hashlib
import jwt

STATUS_CREATED = 'created'
STATUS_PENDING = 'pending'
STATUS_RUNNING = 'running'
STATUS_RESCHEDULE = 'reschedule'
STATUS_OVER = 'over'
STATUS_ARCHIVED = 'archived'

STATUS_SECONDARY_SUSPENDED = 'suspended'
STATUS_SECONDARY_SUSPEND_REJECTED = 'suspend rejected'
STATUS_SECONDARY_SUSPEND_REQUESTED = 'suspend requested'
STATUS_SECONDARY_RESUMED = 'resumed'
STATUS_SECONDARY_RESUME_REJECTED = 'resume rejected'
STATUS_SECONDARY_RESUME_REQUESTED = 'suspend requested'
STATUS_SECONDARY_KILLED = 'killed'
STATUS_SECONDARY_KILL_REQUESTED = 'kill requested'
STATUS_SECONDARY_RESCHEDULED = 'rescheduled'
STATUS_SECONDARY_RESCHEDULE_REQUESTED = 'reschedule requested'
STATUS_SECONDARY_SCHEDULER_REJECTED = 'rejected by scheduler'
STATUS_SECONDARY_QUOTA_REACHED = 'quota reached'
STATUS_SECONDARY_UNKNOWN = 'unknown'

QUEUE_QUEUED = 'queued'
QUEUE_RUNNING = 'running'
QUEUE_KILL = 'kill'
QUEUE_SUSPEND = 'suspend'
QUEUE_RESUME = 'resume'


def md5sum(fname):
    hash_md5 = hashlib.md5()
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def check_jwt_docker_token(docker_data, secret_passphrase):
    '''
    Check a JWT token against Docker provided auth data

    docker_data is the decoded data from plugin RequestBody (which is base64 encoded)
    '''
    god_auth_token = None
    for docker_env in docker_data['Env']:
        if docker_env.startswith('GOD_AUTH_TOKEN='):
            god_auth_token = docker_env.replace('GOD_AUTH_TOKEN=', '')
            break
    if not god_auth_token:
        return (False, 'No GOD_AUTH_TOKEN in env vars')
    decoded_msg = jwt.decode(god_auth_token, secret_passphrase, audience='urn:godocker/auth-api')
    decoded_msg = decoded_msg['docker']
    if decoded_msg['image'] != docker_data['Image']:
        return (False, 'Using different image')
    if 'network' in decoded_msg and decoded_msg['network'] and decoded_msg['network'] != docker_data['HostConfig']['NetworkMode']:
        return (False, 'Using a different network mode')
    if docker_data['HostConfig']['CapAdd']:
        return (False, 'Not allowed to extend capabilities')
    if docker_data['Entrypoint'][0] != decoded_msg['EntryPoint']:
        return (False, 'Not allowed to override Entrypoint')
    if docker_data['HostConfig']['Privileged']:
        return (False, 'Not allowed to execute in privileged mode')
    if docker_data['HostConfig']['Binds']:
        for bind in docker_data['HostConfig']['Binds']:
            if bind not in decoded_msg['volumes']:
                return (False, 'Volume not allowed: ' + str(bind))
    if 'files' in decoded_msg:
        for md5_file in decoded_msg['files']:
            file_to_check = md5_file['file']
            file_to_check_md5 = md5sum(file_to_check)
            if file_to_check_md5 != md5_file['md5']:
                return (False, 'Different files used')
    return (True, 'ok')


def get_jwt_docker_token(image, task_directory, secret_passphrase, entrypoint='/mnt/go-docker/wrapper.sh', volumes=[], network='default'):
    '''
    Get a JWT token that will be used for Docker authorization plugin using env variable GOD_AUTH_TOKEN

    :return: JWT encoded token
    '''
    dockerinfo = {
        'image': image,
        'EntryPoint': entrypoint,
        'volumes': volumes,
        'network': network,
        'files': []
    }
    wrapper_file = os.path.join(task_directory, 'wrapper.sh')
    wrapper_file_md5 = md5sum(wrapper_file)
    dockerinfo['files'].append({
        'file': wrapper_file, 'md5': wrapper_file_md5
    })
    godocker_file = os.path.join(task_directory, 'godocker.sh')
    godocker_file_md5 = md5sum(godocker_file)
    dockerinfo['files'].append({
        'file': godocker_file, 'md5': godocker_file_md5
    })

    token = jwt.encode({'docker': dockerinfo,
#                        'exp': datetime.datetime.utcnow() + datetime.timedelta(seconds=3600),
                        'aud': 'urn:godocker/auth-api'}, secret_passphrase)
    return token


def get_executor(task, executors):
    '''
    Get executor for task from field requirements/executor.
    Field can be in the form executorname:somedata:otherdata
    '''
    if 'executor' not in task['requirements'] or not task['requirements']['executor']:
        task['requirements']['executor'] = executors[0].get_name()
    for executor in executors:
        executor_requirements = task['requirements']['executor'].split(':')
        if executor.get_name() == executor_requirements[0]:
            return executor
    return None


def get_hostname():
    if 'HOSTNAME' in os.environ and os.environ['HOSTNAME']:
        return os.environ['HOSTNAME']
    return socket.gethostbyaddr(socket.gethostname())[0]


def config_backward_compatibility(config):
    '''
    Manage config backward compatibility

    :param config: configuration object
    :type config: dict
    :return: list of warnings
    '''
    warnings = []
    if 'placement' not in config:
        config['placement'] = {}

    if 'mesos' not in config:
        config['mesos'] = {}

    if 'unified' not in config['mesos']:
        config['mesos']['unified'] = False

    if config['mesos']['unified']:
        config['cadvisor_url_part'] = '/containers/mesos'
    else:
        config['cadvisor_url_part'] = '/docker'

    if 'executor' in config:
        warnings.append('executor is deprecated in favor of executors array list')
        config['executors'] = [config['executor']]

    if 'cadvisor_url_part_override' in config and config['cadvisor_url_part_override']:
        config['cadvisor_url_part'] = config['cadvisor_url_part_override']

    if 'reconcile' not in config['mesos']:
        config['mesos']['reconcile'] = True

    if 'mesos_master' in config:
        if 'master' not in config['mesos']:
            config['mesos']['master'] = config['mesos_master']
            warnings.append('mesos_master is deprecated, master should be defined in mesos section')

    if 'network_disabled' in config:
        if 'network' not in config:
            config['network'] = {
                                'use_cni': False,
                                'cni_plugin': None
                                }
        if 'disabled' not in config['network']:
            config['network']['disabled'] = config['network_disabled']
            warnings.append('network_disabled is deprecated, disabled should be defined in network section')

    # Manage environment variables
    if 'GODOCKER_PLUGINS_DIR' in os.environ:
        config['plugins_dir'] = os.environ['GODOCKER_PLUGINS_DIR']
    if 'GODOCKER_SHARED_DIR' in os.environ:
        config['shared_dir'] = os.environ['GODOCKER_SHARED_DIR']
    if 'GODOCKER_MONGO_URL' in os.environ:
        config['mongo_url'] = os.environ['GODOCKER_MONGO_URL']
    if 'GODOCKER_MONGO_DB' in os.environ:
        config['mongo_db'] = os.environ['GODOCKER_MONGO_DB']
    if 'GODOCKER_REDIS_HOST' in os.environ:
        config['redis_host'] = os.environ['GODOCKER_REDIS_HOST']
    if 'GODOCKER_REDIS_PORT' in os.environ:
        config['redis_port'] = int(os.environ['GODOCKER_REDIS_PORT'])
    if 'GODOCKER_INFLUXDB_HOST' in os.environ:
        config['influxdb_host'] = os.environ['GODOCKER_INFLUXDB_HOST']
    if 'GODOCKER_INFLUXDB_PORT' in os.environ:
        config['influxdb_port'] = int(os.environ['GODOCKER_INFLUXDB_PORT'])
    if 'GODOCKER_INFLUXDB_USER' in os.environ:
        config['influxdb_user'] = os.environ['GODOCKER_INFLUXDB_USER']
    if 'GODOCKER_INFLUXDB_PASSWORD' in os.environ:
        config['influxdb_password'] = os.environ['GODOCKER_INFLUXDB_PASSWORD']
    if 'GODOCKER_INFLUXDB_DB' in os.environ:
        config['influxdb_db'] = os.environ['GODOCKER_INFLUXDB_DB']

    if 'GODOCKER_EXECUTOR' in os.environ:
        config['executor'] = os.environ['GODOCKER_EXECUTOR']

    if 'GODOCKER_SCHEDULER_POLICY' in os.environ:
        config['scheduler_policy'] = os.environ['GODOCKER_SCHEDULER_POLICY']
    if 'GODOCKER_AUTH_POLICY' in os.environ:
        config['auth_policy'] = os.environ['GODOCKER_AUTH_POLICY']
    if 'GODOCKER_STATUS_POLICY' in os.environ:
        config['status_policy'] = os.environ['GODOCKER_STATUS_POLICY']

    if 'GODOCKER_PROMETHEUS_EXPORTER' in os.environ:
        config['prometheus_exporter'] = os.environ['GODOCKER_PROMETHEUS_EXPORTER']

    if 'GODOCKER_WEB_ENDPOINT' in os.environ:
        config['web_endpoint'] = os.environ['GODOCKER_WEB_ENDPOINT']

    if 'GODOCKER_MESOS_MASTER' in os.environ:
        config['mesos']['master'] = os.environ['GODOCKER_MESOS_MASTER']

    if 'GODOCKER_KUBE_SERVER' in os.environ:
        config['kube_server'] = os.environ['GODOCKER_KUBE_SERVER']
    if 'GODOCKER_KUBE_TOKEN' in os.environ:
        config['kube_token'] = os.environ['GODOCKER_KUBE_TOKEN']

    if 'GODOCKER_DOCKER_URL' in os.environ:
        config['docker']['url'] = os.environ['GODOCKER_DOCKER_URL']
    if 'GODOCKER_DOCKER_TLS' in os.environ:
        # Set to 1 to activate
        do_tls = os.environ['GODOCKER_DOCKER_TLS']
        if do_tls == '1':
            config['docker']['tls'] = True
        else:
            config['docker']['tls'] = False
    if 'GODOCKER_DOCKER_CA_CERT' in os.environ:
        config['docker']['ca_cert'] = os.environ['GODOCKER_DOCKER_CA_CERT']
    if 'GODOCKER_DOCKER_CLIENT_CERT' in os.environ:
        config['docker']['client_cert'] = os.environ['GODOCKER_DOCKER_CLIENT_CERT']
    if 'GODOCKER_DOCKER_CLIENT_KEY' in os.environ:
        config['docker']['client_key'] = os.environ['GODOCKER_DOCKER_CLIENT_KEY']

    if 'GODOCKER_LDAP_HOST' in os.environ:
        config['ldap_host'] = os.environ['GODOCKER_LDAP_HOST']
    if 'GODOCKER_LDAP_PORT' in os.environ:
        config['ldap_port'] = int(os.environ['GODOCKER_LDAP_PORT'])
    if 'GODOCKER_LDAP_DN' in os.environ:
        config['ldap_dn'] = os.environ['GODOCKER_LDAP_DN']
    if 'GODOCKER_LDAP_BASE_DN_FILTER' in os.environ:
        config['ldap_base_dn_filter'] = os.environ['GODOCKER_LDAP_BASE_DN_FILTER']

    if 'GODOCKER_WATCHERS' in os.environ:
        # Comma separated list of watcher names
        config['watchers'] = os.environ['GODOCKER_WATCHERS'].split(',')

    if 'GODOCKER_CADVISOR_PORT' in os.environ:
        config['cadvisor_port'] = int(os.environ['GODOCKER_CADVISOR_PORT'])

    if 'GODOCKER_EMAIL_FROM' in os.environ:
        config['email_from'] = os.environ['GODOCKER_EMAIL_FROM']
    if 'GODOCKER_EMAIL_SMTP_TLS' in os.environ:
        # Set to 1 to activate
        do_tls = os.environ['GODOCKER_EMAIL_SMTP_TLS']
        if do_tls == '1':
            config['email_smtp_tls'] = True
        else:
            config['email_smtp_tls'] = False
    if 'GODOCKER_EMAIL_SMTP_USER' in os.environ:
        config['email_smtp_user'] = os.environ['GODOCKER_EMAIL_SMTP_USER']
    if 'GODOCKER_EMAIL_SMTP_PASSWORD' in os.environ:
        config['email_smtp_password'] = os.environ['GODOCKER_EMAIL_SMTP_PASSWORD']
    if 'GODOCKER_EMAIL_SMTP_HOST' in os.environ:
        config['email_smtp_host'] = os.environ['GODOCKER_EMAIL_SMTP_HOST']
    if 'GODOCKER_EMAIL_SMTP_PORT' in os.environ:
        config['email_smtp_port'] = int(os.environ['GODOCKER_EMAIL_SMTP_PORT'])

    if 'GODOCKER_ETCD_PREFIX' in os.environ:
        config['etcd_prefix'] = os.environ['GODOCKER_ETCD_PREFIX']
    if 'GODOCKER_ETCD_HOST' in os.environ:
        config['etcd_host'] = os.environ['GODOCKER_ETCD_HOST']
    if 'GODOCKER_EMAIL_SMTP_PORT' in os.environ:
        config['etcd_port'] = int(os.environ['GODOCKER_ETCD_PORT'])

    if 'GODOCKER_FTP_LISTEN' in os.environ:
        config['ftp']['listen'] = os.environ['GODOCKER_FTP_LISTEN']
    if 'GODOCKER_FTP_PUBLIC_ENDPOINT' in os.environ:
        config['ftp']['public_endpoint'] = os.environ['GODOCKER_FTP_PUBLIC_ENDPOINT']
    if 'GODOCKER_FTP_PORT' in os.environ:
        config['ftp']['port'] = int(os.environ['GODOCKER_FTP_PORT'])

    if config['plugins_dir'] and not os.path.exists(config['plugins_dir']):
        raise Exception('plugins_dir does not exists')
    if not os.path.exists(config['shared_dir']):
        raise Exception('shared_dir does not exists')

    return warnings


def get_folder_size(folder):
    '''
    Get directory path full size in bytes

    :param folder: directory path
    :type folder: str
    :return: size of files in folder
    '''
    if not os.path.exists(folder):
        return -1
    folder_size = 0
    for (path, dirs, files) in os.walk(folder):
        for fileInDir in files:
            filename = os.path.join(path, fileInDir)
            folder_size += os.path.getsize(filename)
    return folder_size


def convert_size_to_int(string_size):
    '''
    Convert a size with unit in long

    :param string_size: size defined with value and unit such as 5k 12M ...
    :type string_size: str
    :return: size value in bytes (0 if None)
    '''
    if string_size is None:
        return 0
    string_value = 0
    unit_multiplier = 1
    match = re.search("(\d+)([a-zA-Z])", string_size)
    if not match:
        match = re.search("(\d+)", string_size)
        if not match:
            raise ValueError('size pattern not correct: ' + str(string_size))
        string_value = int(match.group(1))
    else:
        string_value = int(match.group(1))
        unit = match.group(2).lower()
        if unit == 'k':
            unit_multiplier = 1000
        elif unit == 'm':
            unit_multiplier = 1000 * 1000
        elif unit == 'g':
            unit_multiplier = 1000 * 1000 * 1000
        elif unit == 't':
            unit_multiplier = 1000 * 1000 * 1000 * 1000
        else:
            raise ValueError('wrong unit: ' + str(unit))
    return string_value * unit_multiplier


def is_array_task(task):
    '''
    Checks if input task is an array task eg a parent task

    :return: bool
    '''
    if 'array' in task['requirements']:
        if 'values' in task['requirements']['array'] and task['requirements']['array']['values']:
            return True
        else:
            return False

    else:
        return False


def is_array_child_task(task):
    '''
    Checks if input task is an array child task

    :return: bool
    '''
    if 'parent_task_id' in task and task['parent_task_id']:
        return True
    return False
