# Go-Docker

Cluster management tool with Docker

Manage user job (batch/interactive) submissions with Docker (like gridengine on
nodes). User does not need to have Docker rights, everything will go through the application.
Linked to the system users (or ldap), user will have their home mounted automatically as well as other configured directories according to required priviledges in container.
They will be to run jobs with their uid/gid or as root in the container.

User specify his job command line and requirements (docker image, cpu, ram).

## Scheduler

scheduler is in charge of scheduling pending jobs and running them on an
executor

There is only one scheduler running

## Watcher

watcher checks job status and manage jobs kill/suspend/resume. There can be
multiple watchers running in parallel

## Conf

Config is in go-d.ini. One can define the scheduler and executor to use. It must
be one of the classes defined in plugins. One can easily add new ones following
godocker/iExecutorPlugin and iSchedulterPlugin interfaces

One can set environment variable GOD_CONFIG to specify go-d.ini location for go-d-scheduler and go-d-watcher.

## Plugins

Tool support plugins for Authorization, Scheduling and Execution. A few ones are provided but it is easy to create new one, following existing ones using Yapsy.
To create a new plugin, create a xx.yapsy-plugin file and a xx.py file following Yapsy convention. In xx.py you should extend one of the available interfaces according to plugin goal (iExecutorPlugin.py, iAuthPlugin.py, iSchedulerPlugin.py).

* iScheduler plugins look at pending jobs and basically reorder them according to their scheduling strategy.
* iExecutor execute the job and checks its status
* iAuth is used for the web interface, to authenticate a user (ldap bind for example), get some user information (uidnumber, home directory...) and ACLs (which volumes can be mounted for this user request for example).

Available plugins are:


* Scheduler
 * fifo: First In First Out basic strategy
 * fairshare: not yet implemented
* Executor
  * swarm (Docker Swarm)
  * fake  (not be used, for test only, simulate a job execution)
* Auth
  * goauth: specific for our internal usage, but can be easily used as a template for ldap based authentications.

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
