# Go-Docker

Cluster management tool with Docker

Manage user job (batch/interactive) submissions with Docker (like SUN Grid Engine, Torque, ... on
nodes). User does not need to have Docker rights, everything will go through the application.
Linked to the system users (or ldap), user will have their home mounted automatically as well as other configured directories according to required priviledges in container.
They will be able to run jobs with their uid/gid or as root in the container.

The user specifies his job command line or script and its requirements (docker image, cpu, ram) via a CLI tool and go-d-web Web UI.

Go-Docker supports a plugin system to manage authentication, scheduling and execution of containers.

Go-Docker does not compete against Kuberbenets, Mesos frameworks etc... on the contrary.
Most of those tools manage efficiently the dispatch of containers, but they are not "user aware". All users are equal and equal in time. They do not focus either usually on the need to log into a container for interactive tasks, they focus on executing a task based on what user asks. Go-Docker wants to act as a top layer above those tools and to benefit from those tools. The plugin mechanism provides a way to create an executor for Swarm (provided with the tool), but also Kubernetes etc...
theu also usually focus on running "production" long running tasks (such as a webapp), or regular tasks (Chronos). GO-Docker focus on one computational task. If it fails, there is no automatic restart, user will decide after anaylisis to reschedule it if necessary.

1 task = 1 computation = 1 result

This application mainly targets systems where you know your users (not an open cloud platform) which have a home directory they usually access to via SSH/SCP/... , working dirs, ... With Go-Docker, they can ask to get their home directroy mounted in the container (read-only when root access is required for example, and rw for basic access), as well as other pre-defined directories to do... what they need to do. The Authentication plugin will define what users can mount or not.
With the plugin schedulers, it is possible to reorder the pending jobs before running them, based on previous user usage for example, or to reject a job because user reached some quota.

## Features

* job submission
* job watch (check if job is over)
* kill job

### TODO

* API documentation
* suspend/resume jobs
* Reschedule a job

## LICENSE

See COPYRIGHT file. Go-Docker is developped at IRISA.

## Dependencies

apt-get install libldap2-dev gcc libsasl2-dev (Debian/Ubuntu)

yum install libldap-devel gcc cyrus-sasl-devel (Fedora/CentOS)

pip install -r requirements.txt

## Databases

Application needs Mongodb and Redis. Setup Redis to save data on disk for
persistence.

For time based statistics, you can optionally install InfluxDB (if you do not
with to use it, let influxdb_host to empty in configuration file).
If InfluxDB is used, databases must be created first.
Graphics can be displayed with Grafana on series *god_task_usage*

InfluxDB can also be used with cAdvisor to archive usage statistics (see go-docker-web)

InfluxDB is optional but recommended.

## Directories

go-d-docker needs a shared directory between go-d-scheduler, go-d-watcher and
container nodes.

## Status

In development

[![Build Status](https://drone.io/bitbucket.org/osallou/go-docker/status.png)](https://drone.io/bitbucket.org/osallou/go-docker/latest)

[![codecov.io](https://codecov.io/bitbucket/osallou/go-docker/coverage.svg?branch=master)](https://codecov.io/bitbucket/osallou/go-docker?branch=master)

[![Dependency Status](https://www.versioneye.com/user/projects/5501ce724a10640f8c000097/badge.svg?style=flat)](https://www.versioneye.com/user/projects/5501ce724a10640f8c000097)
## Scheduler

scheduler is in charge of scheduling pending jobs and running them on an
executor.

There is only one scheduler running

## Watcher

watcher checks job status and manage jobs kill/suspend/resume. There can be
multiple watchers running in parallel

## Conf

Config is in go-d.ini. One can define the scheduler and executor to use. It must
be one of the classes defined in plugins. One can easily add new ones following
godocker/iExecutorPlugin and iSchedulterPlugin interfaces

One can set environment variable GOD_CONFIG to specify go-d.ini location for go-d-scheduler and go-d-watcher.

Once application is configured, it is necessary, the first time, to initialize the database:

  python go-d-scheduler.py init

## Plugins

Tool support plugins for Authorization, Scheduling and Execution. A few ones are provided but it is easy to create new one, following existing ones using Yapsy.

To create a new plugin, create a xx.yapsy-plugin file and a xx.py file following Yapsy convention. In xx.py you should extend one of the available interfaces according to plugin goal (iExecutorPlugin.py, iAuthPlugin.py, iSchedulerPlugin.py).

* iScheduler plugins look at pending jobs and basically reorder them according to their scheduling strategy.
* iExecutor execute the job and checks its status
* iAuth is used by the web interface, to authenticate a user (ldap bind for example), get some user information (uidnumber, home directory...) and ACLs (which volumes can be mounted for this user request for example).

Available plugins are:


* Scheduler:
  * fifo: First In First Out basic strategy
  * fairshare: not yet implemented
* Executor:
  * swarm (Docker Swarm)
  * fake  (not be used, for test only, simulate a job execution)
* Auth:
  * goauth: specific for our internal usage, but can be easily used as a template for ldap based authentications.
  * fakeauth: fake authentication for tests


## User scripts

User submits a bash script that will be executed as root or user id (according to request) in the container.
Volumes will be mounted in container according to requested volumes and iAuth interface.

'home' is a reserved name for volumes, expecting to match user home directory (if mounted). An environment variable will point to the mounted directory.

Several environment variables are available in user script:

* GODOCKER_JID: Job identifier
* GODOCKER_PWD: Job directory, container will execute script in this directory
* GODOCKER_HOME: mount path for user home directory.

If root access is not required, script will be executed with user id/gid under the container user name *godocker*.
All files in GODOCKER_PWD will be chowned to the user id/gid.

If root access is required, user should take care not to write to other directories (if allowed) as files will have root ACLs.

Network access is required if sudo is not installed, go-docker will install it at container start.

## Interactive sessions

If user selects an interactive session, a port will be opened and the sshd process started in the container.
For interactive sessions, the selected image MUST have the openssh server package installed.

Mapped port will be available in task description.

## Tips

Remove old containers

docker  -H 127.0.0.1:2376  ps -a | awk 'NR > 1 {print $1}' | xargs docker  -H
127.0.0.1:2376 rm

swarm binpacking strategy:

bin/swarm manage --strategy binpacking -H 127.0.1:2376 nodes://127.0.0.1:2375

## CAdvisor

sudo docker run \
  --volume=/:/rootfs:ro \
  --volume=/var/run:/var/run:rw \
  --volume=/sys:/sys:ro \
  --volume=/var/lib/docker/:/var/lib/docker:ro \
  --publish=8080:8080 \
  --detach=true \
  --name=cadvisor \
  google/cadvisor:latest
