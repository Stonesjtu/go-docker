# Running Go-Docker in containers

## About

All components of GO-Docker can run as separate containers.

Example configuration files are available in this directory. They should be adapted to your local configuration.

In examples, fake authentication is used (any user with no password control). If
user does not exists on system, it will create a fake user in the container.
Fake *godocker* user is declared as administrator in the web interface.

If using swarm (as per example go-d.ini), you should have swarm running
somewhere reachable by the host running scheduler and watchers. Swarm can run
itself as a container. Example expects a god-swarm hostname (via --link
parameter), it can be set to a known ip address in:

    docker_url: 'tcp://god-swarm:2375'

Dockerfile is this directory is to build upon develop branch (with tag *dev*). Dockerfile in root
directory is based on master branch for stable release.


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
      gunicorn -p godweb.pid --log-config=/opt/go-docker-web/production.ini --paste /opt/go-docker-web/production.ini


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
