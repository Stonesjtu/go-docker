# Go-Docker

Cluster management tool with Docker

Manage user job (batch/interactive) submissions with Docker (like SUN Grid Engine, Torque, ... on nodes). User does not need to have Docker rights, everything will go through the application.
Linked to the system users (or ldap), user will have their home mounted automatically as well as other configured directories according to required priviledges in container.
They will be able to run jobs with their uid/gid or as root in the container.

The user specifies his job command line or script and its requirements (docker image, cpu, ram) via a CLI tool and go-d-web Web UI.

Go-Docker supports a plugin system to manage authentication, scheduling and execution of containers.

Go-Docker does not compete against Kuberbenets, Mesos frameworks etc... on the contrary.
Most of those tools manage efficiently the dispatch of containers, but they are
not "user aware". All users are equal and equal in time. They do not focus either usually on the need to connect (ssh) into a container for interactive tasks, they focus on executing a task based on what user asks. Go-Docker wants to act as a top layer above those tools and to benefit from those tools. The plugin mechanism provides a way to create an executor for Swarm (provided with the tool), but also Kubernetes etc...

They also usually focus on running "production" long running tasks (such as a webapp), or regular tasks (Chronos). GO-Docker focus on one computational task. If it fails, there is no automatic restart, user will decide after anaylisis to reschedule it if necessary.

1 task = 1 computation = 1 result

This application mainly targets systems where you know your users (not an open cloud platform) which have a home directory they usually access to via SSH/SCP/... , working dirs, ... With Go-Docker, they can ask to get their home directroy mounted in the container (read-only when root access is required for example, and rw for basic access), as well as other pre-defined directories to do... what they need to do. The Authentication plugin will define what users can mount or not.
With the plugin schedulers, it is possible to reorder the pending jobs before running them, based on previous user usage for example, or to reject a job because user reached some quota.

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

## LICENSE

See COPYRIGHT file. Go-Docker is developped at IRISA.

## Other components

* Web: web interface, https://bitbucket.org/osallou/go-docker-web (mandatory)
* CLI: command line client, https://bitbucket.org/osallou/go-docker-cli/
* Airflow module: submit Airflow workflow command to go-docker, https://bitbucket.org/osallou/go-docker-airflow/
* FireWorks module: submit FireWorks workflow commands to go-docker, https://bitbucket.org/osallou/go-docker-fireworks/
* Live: view job logs in real-time, https://bitbucket.org/osallou/go-docker-live/


## Dependencies

apt-get install python-dev libldap2-dev gcc libsasl2-dev (Debian/Ubuntu)

yum install python-devel libldap-devel gcc cyrus-sasl-devel (Fedora/CentOS)

pip install -r requirements.txt

## Databases

Application needs Mongodb and Redis. Setup Redis to save data on disk for
persistence.

For time based statistics, you can optionally install InfluxDB (if you do not
with to use it, let influxdb_host to empty in configuration file).
If InfluxDB is used, databases must be created first.
Graphics can be displayed with Grafana on series *god_task_usage*

InfluxDB can also be used with cAdvisor to archive usage statistics (see go-docker-web)

InfluxDB is optional but recommended. Grafana will help getting charts of usage recorded in InfluxDB.

## Directories

go-d-docker needs a shared directory between go-d-scheduler, go-d-watcher and
container nodes.

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

## Watcher

watcher checks job status and manage jobs kill/suspend/resume. There can be
multiple watchers running in parallel

## Configuration

Configuration is in file go-d.ini. One can define the scheduler and executor to use. It must be one of the classes defined in plugins. One can easily add new ones following godocker/iExecutorPlugin and iSchedulterPlugin interfaces

One can set environment variable GOD_CONFIG to specify go-d.ini location for go-d-scheduler and go-d-watcher.

Once application is configured, it is necessary, the first time, to initialize the database:

  python go-d-scheduler.py init

Logging is defined in log_config field. One can set logging for logstash, graylog, file etc...

### Fairshare

FairShare plugin adds additional, optional configuration to manage different weight to apply on paramerers:


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

    export GOD_PROCID = 1
    python go-d-scheduler start

    export GOD_PROCID = 2
    python go-d-watcher start


For debug, it is possible to run processes in foreground with run option, or only one time (no loop) with option once.

Log level can be modified with env variable GOD_LOGLEVEL (DEBUG, INFO, ERROR)


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
* iStatus register processes and get status of processes to an external system (etcd, ...), if none is set, no monitoring will be done

Base classes are documented here: http://go-docker.readthedocs.org/en/latest/

The Utils class can also be used with a few helpers.

Available plugins are:


* Scheduler:
    * fifo: First In First Out basic strategy
    * fairshare: Fair share user tasks repartition (prio, previous usage, ...)
* Executor:
    * swarm (Docker Swarm)
    * mesos (Apache Mesos, tested with mesos 0.22)
    * fake  (not be used, for test only, simulate a job execution)
* Auth:
    * goauth: ldap based authentications.
    * fake: fake authentication for tests
    * local: match db users (using *create_local_user.py*) with system users.
* Watcher:
    * maxlifespan: Checks max life duration of a job
* Status:
     etcd: register processes to etcd

### Swarm

To integrate with Swarm, swarm process needs to listen on a tcp socker (tcp://ip_address:2376 for example). Swarm is in charge of dispatching tasks to the Docker instances on slaves.

### Mesos

The Mesos plugin integrates go-docker in as a mesos framework (http://mesos.apache.org/). Framework is managed via the scheduler process.

It does not manage for the moment Mesos master failover nor reoffers (offer rejected)/slave failure. See bugs for remaining issues/missing feaures for Mesos.

Tasks are executed using Mesos executor with Docker. Port allocation (for interactive jobs) are managed via the port resources declared on slaves.

Slaves should be started with an attribute "hostname" matching the slave hostname or ip, for example:

    mesos-slave.sh --master=10.0.0.1:5050 --containerizers=docker,mesos --attributes='hostname:10.0.0.2'

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
For interactive sessions, the selected image MUST have the openssh server package installed.

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


## Temporary local storage

This feature needs the Docker volume plugin docker-plugin-zfs on each node (see Docker plugins).
User can specify a local Temporary storage size on tasks. System will create and mount a ZFS storage volume for the container and will be deleted at the end of the task. Volume has quota according to task requirements. This provides a local disk storage for intermediate computation requiring fast disk access.

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
