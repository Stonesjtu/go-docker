# Running Go-Docker in containers

## About

All components of GO-Docker can run as separate containers.

Example configuration files are available in https://bitbucket.org/osallou/go-docker/src under docker_files/prod directory.
They should be adapted to your local configuration.

In examples, fake authentication is used (any user with no password control). If
user does not exists on system, it will create a fake user in the container.
Fake *godocker* user is declared as administrator in the web interface.

If using swarm (as per example go-d.ini), you should have swarm running
somewhere reachable by the host running scheduler and watchers. Swarm can run
itself as a container. Example expects a god-swarm hostname (via --link
parameter), it can be set to a known ip address in:

    docker_url: 'tcp://god-swarm:2375'

For Mesos, latest mesos package is installed from repositories. Some issue may occur if using a different version, depending on API compatibilities. If this occurs, you must uninstall mesos package and install your mesos version package in the container (needed for the Python API).

## Requirements

Mongodb and Redis are required. Either install them on a server, or get them in containers:

    # Development purpose, for production you should set data persistency
    docker -H swarm_ip:2375  run --name god-mongo -d mongo
    docker -H swarm_ip:2375  run --name god-redis -d redis

## Running components


Run the web server, interface is reachable at http://host_ip_godweb:6543

*Warning*: data shared directory (here /opt/godshared) *must* match
on host AND container as final job will end in a host container needing the same volume directory.
*shared_dir* parameter in go-d.ini configuration file must be changed accordingly.

    docker -H swarm_ip:2375  run \
      --rm \
      --name god-web
      --link god-mongo:god-mongo  \
      --link god-redis:god-redis  \
      -v /opt/godshared:/opt/godshared \
      -v path_to/go-d.ini:/opt/go-docker/go-d.ini \
      -v path_to/production.ini:/opt/go-docker-web/production.ini \
      -p 6543:6543 \
      -e "PYRAMID_ENV=prod" \
      osallou/go-docker \
      gunicorn -c /opt/go-docker-web/gunicorn_conf.py -p godweb.pid --log-config=/opt/go-docker-web/production.ini --paste /opt/go-docker-web/production.ini


The first time only, initialize db etc...

    docker -H swarm_ip:2375 run \
    --link god-mongo:god-mongo \
    --link god-redis:god-redis \
    -v /opt/godshared:/opt/godshared \
    -v path_to/go-d.ini:/opt/go-docker/go-d.ini \
     --rm \
     osallou/go-docker \
     /usr/bin/python go-d-scheduler.py init


Run *one* scheduler

    docker -H swarm_ip:2375 run \
      --rm \
      --link god-mongo:god-mongo  \
      --link god-redis:god-redis  \
      --link god-web:god-web \
      -v /opt/godshared:/opt/godshared \
      -v path_to/go-d.ini:/opt/go-docker/go-d.ini \
      osallou/go-docker \
      /usr/bin/python go-d-scheduler.py run

Run *one or many* watchers (1 is enough test or medium size production)

    docker -H swarm_ip:2375  run \
      --rm \
      --link god-mongo:god-mongo  \
      --link god-redis:god-redis  \
      --link god-web:god-web \
      -v /opt/godshared:/opt/godshared \
      -v path_to/go-d.ini:/opt/go-docker/go-d.ini \
      osallou/go-docker \
      /usr/bin/python go-d-watcher.py run

## Customization

From GoDocker v1.2, it is possible to override some configuration with environment variables (see README.md for the list). Example:

    docker run --rm -e "GODOCKER_EXECUTOR=mesos" -e "GODOCKER_MESOS_MASTER=master_ip:5050" -e "GODOCKER_REDIS_HOST=test-redis" -e "GODOCKER_MONGO_URL=mongodb://test-mongo:27017" -w /opt/go-docker --link test-mongo:test-mongo --link test-redis:test-redis -v /opt/godshared:/opt/godshared --name godocker-scheduler test-godocker python go-d-scheduler.py run

In this example we override the default executor to use mesos instead of default swarm executor and we specify the master url. Redis and Mongo hosts are also specified in the command line.

To add a prefix to the web server:

Add  -e "GODOCKER_WEB_PREFIX=/testapp" to web container to add a prefix to web UI (http://xxx:6543/testapp/app).
Update scheduler/watcher containers command with -e "GODOCKER_PROMETHEUS_EXPORTER=godocker-web:6543/testapp" to match the declared prefix.
