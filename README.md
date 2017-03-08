# Go-Docker

Batch computing/cluster management tool with Docker.

Manage user job (batch/interactive) submissions with Docker (like SUN Grid Engine, Torque, ... on nodes). User does not need to have Docker rights, everything will go through the application. Jobs that cannot be scheduled are kept in queue until contraints/resources are available.
Linked to the system users (or ldap), user will have their home mounted automatically as well as other configured directories according to required priviledges in container.
They will be able to run jobs with their uid/gid or as root in the container.

The user specifies his job command line or script and its requirements (docker image, cpu, ram) via a CLI tool and go-d-web Web UI.

Go-Docker supports a plugin system to manage authentication, scheduling and execution of containers.

Go-Docker does not compete against Kuberbenets, Mesos frameworks etc... on the contrary.
Most of those tools manage efficiently the dispatch of containers, but they are
not "user aware". All users are equal and equal in time. They do not focus either usually on the need to connect (ssh) into a container for interactive tasks, they focus on executing a task based on what user asks. Go-Docker wants to act as a top layer above those tools and to benefit from those tools. The plugin mechanism provides a way to create an executor for Swarm (provided among others with the tool), but also Kubernetes etc...

They also usually focus on running "production" long running tasks (such as a webapp), or regular tasks (Chronos). GO-Docker focus on one computational task. If it fails, there is no automatic restart, user will decide after anaylisis to reschedule it if necessary.

1 task = 1 computation = 1 result

This application mainly targets systems where you know your users (not an open cloud platform) which have a home directory they usually access to via SSH/SCP/... , working dirs, ... With Go-Docker, they can ask to get their home directroy mounted in the container (read-only when root access is required for example, and rw for basic access), as well as other pre-defined directories to do... what they need to do. The Authentication plugin will define what users can mount or not.
With the plugin schedulers, it is possible to reorder the pending jobs before running them, based on previous user usage for example, or to reject a job because user reached some quota.

## Documentation

https://godocker.atlassian.net/wiki/display/GOD/GODOCKER

## Limitations

docker images used to submit jobs must have *bash* installed.
On Alpine linux, if *bash* is not installed, GoDocker will try to install it but it will delay command startup.

For interactive jobs, GoDocker expects openssh server to be installed. If not in image, it will automatically install it but this will delay session startup.

## Features

* job submission
* job watch (check if job is over)
* kill job
* suspend/resume job
* reschedule a job
* quotas: user or project (cpu, memory, disk)
* use a private registry
* rate limiting: limit number of pending tasks for a user or globally
* dependency between tasks
* process monitoring
* temporary local storage on nodes
* optional *guest* support, i.e. accepting users connecting with Google, GitHub, ... and not in system. Guest will map to a system user for execution.
* node reservation (mesos)
* experimental resource reservation (GPU, etc.)
* open some ports in container
* FTP server for user data upload (with quota)
* CNI Docker network plugins support

## LICENSE

See COPYRIGHT file. Go-Docker is developed at IRISA.

## Other components

* Web: web interface, https://bitbucket.org/osallou/go-docker-web (mandatory)
* CLI: command line client, https://bitbucket.org/osallou/go-docker-cli/
* Airflow module: submit Airflow workflow command to go-docker, https://bitbucket.org/osallou/go-docker-airflow/
* FireWorks module: submit FireWorks workflow commands to go-docker, https://bitbucket.org/osallou/go-docker-fireworks/
* Live: view job logs in real-time, https://bitbucket.org/osallou/go-docker-live/

## Python

go-docker and its components (go-docker-web, ...) are Python 2.7+ and Python 3 compatible.
However, Mesos does not provide yet Python 3 libraries.

If you do not plan to use mesos, you can simply delete plugins/mesos.* files.

## Dependencies

apt-get install python-dev libldap2-dev gcc libsasl2-dev openssl libpython-dev libffi-dev libssl-dev protobuf-compiler (Debian/Ubuntu)

yum install python-devel libldap-devel gcc cyrus-sasl-devel openssl python-devel libffi-devel openssl-devel protobuf-compiler (Fedora/CentOS)

pip install -r requirements.txt

## Databases

Application needs Mongodb and Redis. Setup Redis to save data on disk for
persistence.

For time based statistics, you can optionally install InfluxDB (if you do not
with to use it, let influxdb_host to empty in configuration file).
If InfluxDB is used, databases must be created first.
Graphics can be displayed with Grafana on series *god_task_usage*

InfluxDB can also be used with cAdvisor to archive usage statistics (see go-docker-web)

InfluxDB is optional. Grafana will help getting charts of usage recorded in InfluxDB.

## Directories

go-d-docker needs a shared directory between go-d-scheduler, go-d-watcher and
container nodes.

## Install

See INSTALL.md

## Status

Documentation: http://go-docker.readthedocs.org/en/latest/index.html

[![Build Status](https://drone.io/bitbucket.org/osallou/go-docker/status.png)](https://drone.io/bitbucket.org/osallou/go-docker/latest)

[![codecov.io](https://codecov.io/bitbucket/osallou/go-docker/coverage.svg?branch=master)](https://codecov.io/bitbucket/osallou/go-docker?branch=master)

[![Dependency Status](https://www.versioneye.com/user/projects/5501ce724a10640f8c000097/badge.svg?style=flat)](https://www.versioneye.com/user/projects/5501ce724a10640f8c000097)

## Scheduler

The scheduler is in charge of scheduling pending jobs and running them on an
executor.

There is only one scheduler running. At startup, scheduler will check if Redis
database is populated, if not, it will sync it with mongo database. This
automatic check prevents Redis flushes or loss of data.

While only one scheduler is active, it is possible to execute multiple instances for high-availability.
If one instance is stopped, an other will take leadership and be the new scheduler master.
In case of failure, one need to wait for the previous keep-alive timeout for the new scheduler to be the new master (config parameter master_timeout, default to 600s).
Timeout must be higher than the maximum time needed for a scheduling run.

## Watcher

watcher checks job status and manage jobs kill/suspend/resume. There can be
multiple watchers running in parallel

## Archiver

The archiver is in charge of the cleanup of old jobs.
go-d-clean.py can be put as a cron task to delete old jobs based on configuration. Job identifiers can also be given as parameter to the script to force the archive of those jobs, even if expiration date is not reached.
*go-d-clean.py* sends archive requests to the go-d-archive daemon.

Archiver service is required to let user archive jobs themselves.


## Configuration

Configuration is in file go-d.ini. One can define the scheduler and executor to use. It must be one of the classes defined in plugins. One can easily add new ones following godocker/iExecutorPlugin and iSchedulerPlugin interfaces

File is in YAML format.

One can set environment variable GOD_CONFIG to specify go-d.ini location for go-d-scheduler and go-d-watcher.

Once application is configured, it is necessary, the first time, to initialize the database:

  python go-d-scheduler.py init

Logging is defined in log_config field. One can set logging for logstash, graylog, file etc...

Some configuration parameters can be overriden with environment variables:

* GODOCKER_PLUGINS_DIR
* GODOCKER_SHARED_DIR
* GODOCKER_MONGO_URL
* GODOCKER_MONGO_DB
* GODOCKER_REDIS_HOST
* GODOCKER_REDIS_PORT
* GODOCKER_INFLUXDB_HOST
* GODOCKER_INFLUXDB_PORT
* GODOCKER_INFLUXDB_USER
* GODOCKER_INFLUXDB_PASSWORD
* GODOCKER_INFLUXDB_DB
* GODOCKER_EXECUTOR
* GODOCKER_SCHEDULER_POLICY
* GODOCKER_AUTH_POLICY
* GODOCKER_STATUS_POLICY
* GODOCKER_PROMETHEUS_EXPORTER
* GODOCKER_WEB_ENDPOINT
* GODOCKER_MESOS_MASTER
* GODOCKER_KUBE_SERVER
* GODOCKER_KUBE_TOKEN
* GODOCKER_DOCKER_URL
* GODOCKER_DOCKER_TLS: set to 1 to activate
* GODOCKER_DOCKER_CA_CERT
* GODOCKER_DOCKER_CLIENT_CERT
* GODOCKER_DOCKER_CLIENT_KEY
* GODOCKER_LDAP_HOST
* GODOCKER_LDAP_PORT
* GODOCKER_LDAP_DN
* GODOCKER_LDAP_BASE_DN_FILTER
* GODOCKER_WATCHERS: comma separated list of watcher names
* GODOCKER_CADVISOR_PORT
* GODOCKER_EMAIL_FROM
* GODOCKER_EMAIL_SMTP_TLS: set to 1 to activate
* GODOCKER_EMAIL_SMTP_USER
* GODOCKER_EMAIL_SMTP_PASSWORD
* GODOCKER_EMAIL_SMTP_HOST
* GODOCKER_EMAIL_SMTP_PORT
* GODOCKER_ETCD_PREFIX
* GODOCKER_ETCD_HOST
* GODOCKER_EMAIL_SMTP_PORT
* GODOCKER_FTP_LISTEN
* GODOCKER_FTP_PUBLIC_ENDPOINT
* GODOCKER_FTP_PORT


### Fairshare

FairShare plugin adds additional, optional configuration to manage different weight to apply on parameters:


    fairshare_waiting_time_weight = 0.1  # weight apply to waiting time of tasks
    fairshare_user_time_weight = 1       # weight to cpu time spent in previous tasks for defined duration user_reset_usage_duration
    fairshare_user_cpu_weight = 0.2      # weight to number of cpu used in previous tasks for defined duration user_reset_usage_duration
    fairshare_user_ram_weight = 0.2      # weight to quantity of ram used in previous tasks for defined duration user_reset_usage_duration
    fairshare_group_time_weight = 0.1    # same as user but for user group
    fairshare_group_cpu_weight = 0.01    # same as user but for user group
    fairshare_group_ram_weight = 0.01    # same as user but for user group
    fairshare_user_weight = 1            # weight to apply on user priority
    fairshare_group_weight = 1           # weight to apply on group priority



## Running

To identify processes, each process must have a unique id. It is possible to set this id with the environment variable GOD_PROCID.
This variable is needed when multiple processes are executed on the same server and to set a process id (one watcher for example) identical after each restart.

Environment variable **GOD_CONFIG** can specify go-d.ini location.

    export GOD_PROCID = 1
    python go-d-scheduler start

    export GOD_PROCID = 2
    python go-d-watcher start

    python go-d-archive start

Executables have *start* and *stop* commands to manage their execution (ran in background)

For debug, it is possible to run processes in foreground with *run* option, or only one time (no loop) with option *once*.

Log level can be modified with env variable GOD_LOGLEVEL (DEBUG, INFO, ERROR)

Executables

## Running in containers

See docker-files/prod/README.md

## Running on Amazon EC2

Look at https://bitbucket.org/osallou/go-docker-ec2/overview for
contextualization scripts to deploy an EC2 GO-Docker cluster.

## Chef install

You can install GoDocker master and slaves using Chef cookbooks, see https://bitbucket.org/osallou/go-docker-chef.
Cookbooks can be used on EC2 or bare metal.

## Plugins

Tool support plugins for Authorization, Scheduling and Execution. A few ones are provided but it is easy to create new one, following existing ones using Yapsy.

To create a new plugin, create a xx.yapsy-plugin file and a xx.py file following Yapsy convention. In xx.py you should extend one of the available interfaces according to plugin goal (iExecutorPlugin.py, iAuthPlugin.py, iSchedulerPlugin.py).

* iScheduler plugins look at pending jobs and basically reorder them according to their scheduling strategy.
* iExecutor execute the job and checks its status
* iAuth is used by the web interface, to authenticate a user (ldap bind for example), get some user information (uidnumber, home directory...) and ACLs (which volumes can be mounted for this user request for example).
* iWatcher checks, once a job is running if it should continue or be killed, ...
* iStatus register processes and get status of processes to an external system (etcd, consul, ...), if none is set, no monitoring will be done
* iNetwork plugins are used by executors to use Docker CNI plugins to assign an IP to containers avoiding port mapping

Base classes are documented here: http://go-docker.readthedocs.org/en/latest/

The Utils class can also be used with a few helpers.

Available plugins are:


* Scheduler:
    * fifo: First In First Out basic strategy
    * fairshare: Fair share user tasks repartition (prio, previous usage, ...)
* Executor:
    * swarm (Docker Swarm)
    * mesos (Apache Mesos, tested with mesos 0.28)
    * Kubernetes (tested with 1.2.0, using API v1)
    * SGE (tested with SGE 8.1.9)
    * fake  (not be used, for test only, simulate a job execution)
* Auth:
    * goauth: ldap based authentications.
    * fake: fake authentication for tests
    * local: match db users (using *create_local_user.py*) with system users.
* Watcher:
    * maxlifespan: Checks max life duration of a job
* Status:
    * etcd: register processes to etcd
    * consul: register processes to Consul
* Network:
    * weave: Weave network Mesos/Docker plugin support, only 1 public network is supported for the moment.
    * calico: Calico network Mesos/Docker plugin

### Swarm

To integrate with Swarm, swarm process needs to listen on a tcp socket (tcp://ip_address:2376 for example). Swarm is in charge of dispatching tasks to the Docker instances on slaves.

### Mesos

The Mesos plugin integrates go-docker in as a mesos framework (http://mesos.apache.org/). Framework is managed via the scheduler process.

It does not manage for the moment Mesos master failover nor reoffers (offer rejected)/slave failure. See bugs for remaining issues/missing feaures for Mesos.

Tasks are executed using Mesos executor with Docker. Port allocation (for interactive jobs) are managed via the port resources declared on slaves.

Slaves should be started with an attribute "hostname" matching the slave hostname or ip, for example:

    mesos-slave.sh --master=10.0.0.1:5050 --containerizers=docker,mesos --attributes='hostname:10.0.0.2'

GoDocker supports both Docker and Mesos Unified containerizers, choice is made in config file in mesos section.

### Kubernetes

GoDocker has experimental support with Kubernetes (see Kubernetes section in configuration).
Tasks that cannot be planned doe to overcapacity are deleted from Kubernetes but remain in pending state in GoDocker.
It does not support GPU reservation has Kubernetes does not support yet arbitrary resource counters (though in roadmap).
Regarding temporary storage, software makes use of *emptyDir* volume capability of Kubernetes. A local directory is created on node, but no capacity is guaranteed (per user or global). Other kinds of persistent volumes are not supported here.

## User scripts

User submits a bash script that will be executed as root or user id (according to request) in the container.
Volumes will be mounted in container according to requested volumes and iAuth interface.

'home' is a reserved name for volumes, expecting to match user home directory (if mounted). An environment variable will point to the mounted directory.

Several environment variables are available in user script:

* GODOCKER_JID: Job identifier
* GODOCKER_PWD: Job directory, container will execute script in this directory
* GODOCKER_HOME: mount path for user home directory.

For job arrays the following variables are also available:

* GOGOCKER_TASK_ID: Job array task identifier
* GOGOCKER_TASK_FIRST: First job array task identifier
* GOGOCKER_TASK_LAST: Last job array task identifier
* GOGOCKER_TASK_STEP: steps in job array identifiers

If root access is not required, script will be executed with user id/gid under the container user name *godocker*.
All files in GODOCKER_PWD will be chowned to the user id/gid.

If root access is required, user should take care not to write to other directories (if allowed) as files will have root ACLs.

Network access is required if sudo is not installed, go-docker will install it at container start.

## Interactive sessions

If user selects an interactive session, a port will be opened and the sshd process started in the container.
For interactive sessions, the selected image SHOULD have the openssh server package installed. If not installed GoDocker will try to install openssh-server package via apt- or yum.

Mapped port will be available in task description.

The user public key will be copied in the container for access. If not set, user can cannot using his user id and his API Key as password.

It is possible to get SSH connection to the container via a Web SSH proxy such as GateOne (https://registry.hub.docker.com/u/liftoff/gateone/), running on a public IP (https).
Nodes name should be known in the network (dns) to access them through the proxy.


## Job arrays

Job arrays allows to execute multiple jobs with same parameters. A
start:end:step definition generate X jobs in separate job directories with
additional environment variables (GOGOCKER_TASK_ID, ...).

Main task has an id and refers the X sub tasks. Main task does not execute any
command and ends when all sub tasks are over. Killing a main tasks also kills
all the sub tasks.


## Projects

User can submit a task on a project. If not specified *default* is used.
*default* project has no quota, and all users can submit to the project. In this
case, only user quotas will apply.

Only administrators can create projects and assign users to projects. Other
projects can get a global quota applying to all members (cumulative usage of
members).

## Priority

User and projects can have a priority between 0 and 100. This value *may* be used by schedulers to order the pending tasks. *default* project has a priority of 50.

## DRMAA support

A drmaa library is available at https://bitbucket.org/osallou/go-docker-drmaa.
It is a C implementation of DRMAA v1. Not all methods are implemented but basic
use to submit/check jobs are present.

Python DRMAA modules can work with this library.

## Process monitoring

Process monitoring is optional, if you do not wish to use etcd default plugin, simple set status_policy to None or empty string.

### Etcd

Etcd must be running on a server. One can use Docker to do so:

    docker run -p 4001:4001 --name etcd --rm  quay.io/coreos/etcd \
        -listen-client-urls http://0.0.0.0:2379,http://0.0.0.0:4001 \
        -advertise-client-urls http://${HostIP}:2379,http://${HostIP}:4001


Configuration:

    status_policy: 'etcd'
    etcd_prefix: '/godocker'
    etcd_host: 'a.b.c.d' # Ip address where is running etcd
    etcd_port: 4001

### Consul

Installation/setup of Consul is out of the scope here.

Setting up Consul as status manager will register web/scheduler/watchers to Consul with ttl or http checks.
In addition, web services will be registered in Consul DNS with their ip and port for DNS queries.
Consul DNS can be used for load balancing to web servers using for example HAProxy.

## Temporary local storage

This feature needs the Docker volume plugin docker-plugin-zfs on each node (see Docker plugins).
User can specify a local Temporary storage size on tasks. System will create and mount a ZFS storage volume for the container and will be deleted at the end of the task. Volume has quota according to task requirements. This provides a local disk storage for intermediate computation requiring fast disk access.

At this moment, this works only with mesos plugin, not swarm due to swarm management/scheduling with Volume plugins.

## Guest support

The guest feature is optional and supported by the guest_XXX parameters in go-d.ini file. Guest users connect with Google, GitHub, ... and are not in system (ldap, ...). All guests are mapped/binded to a system user for execution. They do not have direct access to their *home directory*, which will be created as a subdirectory of a specified, existing, directory.

Administrator, via the web interface, must activate the users after their first login. Guest can be disabled afterward.

Care should be taken regarding disk space used in the guest home directory. Usage is visible in administrator panel of the web interface.

## Node reservation

With mesos, a node can be reserved for a set of users or projects.

Simply add to mesos-slave the attribute:

    reservation:users_or_project_names_comma_separated

    example:

    reservation:user1,project2

## Resource reservation

With mesos, one can ask for specific resources (GPU, etc.) according to resources available set in mesos-slave.

Resources are defined in go-docker as constraints, in constraint named *resource*:

    constraints: [
        { name: 'storage', value: 'ssd,disk' },
        { name: 'resource', value: 'gpu_10.5' }
    ]

One can define multiple resource with a comma (gpu_10.5,my_specific_resource).

On mesos-slave, resources should be added as following fro a GPU use case.

    admin:/etc/mesos-slave$ cat attributes
    hostname:10.72.136.115
    gpu_10.5_0:/dev/nvidia0,/dev/nvidiactl,/dev/nvidia-uvm
    gpu_10.5_1:/dev/nvidia1,/dev/nvidiactl,/dev/nvidia-uvm
    admin@ip-10-72-136-115:/etc/mesos-slave$ cat resources
    gpu_10.5:[0-1]

In resources files, we define the resource name and the available quantity for this resources. In above example, we have 2 GPUs (a range with left and right bounds included).
For each resource, it is possible to define volumes to mount in container. To do so, we add to the attributes file one attribute per resource with the name scheme: nameOfResource_resourceSlot. Volumes must be comma separated if multiple ones are needed.

Still in previous example, if system selects in available resources the slot 0 of resource *gpu_10.5*, then volumes defined in *gpu_10.5_0* will be mounted in container.

It is possible to specify in task multiple resource requirements.

## Private registry/images

### Mesos

To access a Docker registry/image with authentication, user needs to:

* Create an archive in his home directory named docker.tar.gz containing the .docker directory (.docker/, /.docker/config.json ) after a successful login
* Add *home* volume in his task (to access docker.tar.gz archive)

## CNI integration

Network plugins allows to assign a job to a network (public/user/project) and assign an IP per container, avoiding port mapping.
The choice of networks supported depends on the plugin. The provided network plugins only support the public network at this time.

In public network, all containers are in the same sub network and can dialog with each other.
In user or project network, containers are placed in a network where only containers from the same user or project can talk to each other.

CNI is activated in the network section of the configuration file. If not activated, basic Docker bridge and port mapping is used.

## SGE integration

If docker for SGE is not enabled, native SGE jobs will be executed (no containers). GoDocker will simply add mem and cpu requirements for the job and execute the job under user id (no root access possible, no mounts as job is directly executed on the node).
If docker is set, GoDocker will submit job in SGE and execute a Docker container. To prevent users from using direclty Docker, the web interface will act as an authorization plugin for docker. To do so, docker must be configured to:

* listen on a tcp port (docker/url parameter of config)
* define an authorization plugin

    # cat /etc/docker/plugins/godocker-auth.spec
    http://ip_of_godocker_web:6543

* Add authorization plugin to docker daemon

    # cat /etc/systemd/system/docker.service.d/docker.conf
    [Service]
    ExecStart=
    ExecStart=/usr/bin/docker daemon --host=fd:// --host=tcp://127.0.0.1:2375 --authorization-plugin=godocker-auth

* Reload config and restart docker (godocker web must already be running)

    #systemctl daemon-reload
    #service docker restart


When a docker command is executed, docker will trigger godocker web to ask for authorization. A specific token is created at job creation only and only docker commands using this token are accepted. GoDocker will check that volumes, scripts etc. are the same than those requested at job creation time to prevent reusing a token for a different job.
Without this token, users won't be able to use Docker directly on your cluster.

To allow job kill operation, SGE must be configured to either send a SIGTERM on qdel instead of SIGKILL or support the -notify option, else container will continue to run and won't be deleted on job completion.

SGE docker jobs cannot be monitored (cAdvisor/prometheus) at this time.

## Tips

Remove old containers

docker  -H 127.0.0.1:2376  ps -a | awk 'NR > 1 {print $1}' | xargs docker  -H
127.0.0.1:2376 rm

swarm binpacking strategy:

bin/swarm manage --strategy binpacking -H 127.0.1:2376 nodes://127.0.0.1:2375

Cleanup of counters in case of incoherency (due to some framework
restarts/errors....)

    redis-cli
    127.0.0.1:6379> get god:jobs:queued
    "-2"
    127.0.0.1:6379> set god:jobs:queued 0
    OK
    127.0.0.1:6379> llen god:jobs:running
    (integer) 2
    127.0.0.1:6379> lpop god:jobs:running
    "501"
    127.0.0.1:6379> lpop god:jobs:running
    "502"
    127.0.0.1:6379> lpop god:jobs:running
    nil


## CAdvisor

Running cAdvisor on nodes gives live monitoring of the container (ram/cpu/network) in the web interface.

sudo docker run --volume=/:/rootfs:ro  --volume=/var/run:/var/run:rw  --volume=/sys:/sys:ro --volume=/var/lib/docker/:/var/lib/docker:ro --publish=8080:8080 --detach=true --name=cadvisor google/cadvisor:latest

# End user tutorials

## CLI

https://www.youtube.com/watch?v=3fu2aLocTbI

## Web interface

https://www.youtube.com/watch?v=juw_foi-Q0c
