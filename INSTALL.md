# Basic installation

Here is basic install for a single node.

## Create python virtualenv

    $ virtualenv envgodocker
    $ . envgodocker/bin/activate

## Get code

    $git clone https://bitbucket.org/osallou/go-docker.git
    $git clone https://bitbucket.org/osallou/go-docker-web.git

## Dependencies

    $apt-get install python-dev libldap2-dev gcc libsasl2-dev
    $apt-get install openssl libpython-dev libffi-dev libssl-dev

(see README.md for CentOS)


## Docker / Swarm

Install Docker Swarm/Docker to listen on tcp port 2375


## Databases


Install mongodb and redis

or use available containers with the following (update swam_ip and port according to your swam install)

    mkdir /opt/god-docker-mongo
    docker -H swarm_ip:2375  run -p 27017:27017 --name god-mongo -v /opt/god-docker-mongo:/data/db -d mongo
    docker -H swarm_ip:2375  run -p 6379:6379 --name god-redis -d redis



# GoDocker scheduler and watcher

## Setup

    $cd go-docker
    $python setup.py develop
    $cp go-d.ini.sample go-d.ini

## Config

Edit go-d.ini and update following fields

    plugins_dir: 'path_to_install/go-docker/plugins'
    shared_dir: 'path_to_install/go-docker/godshared'
    ...
    volumes:
        - name: 'home'
          acl: 'rw'

    mongo_url: 'mongodb://localhost:27017/'
    redis_host: 'localhost'

    executor: 'swarm'

To use local system users, let's select the *local* auth plugin.

    auth_policy: 'local'

Update ip and port to match Docker or Swarm ip and port

    docker_url: 'tcp://127.0.0.1:2375'

Let's skip prometheus monitoring for the moment

    prometheus_key: null

To allow any image, not only those defined in config:

    allow_user_images: True


If you want process supervision, select the consul status plugin, else leave it commented.
To run the consul container:

    docker run -p 8400:8400 -p 8500:8500 -p 8600:53/udp -d progrium/consul -server -bootstrap


In go-d.ini

    status_policy: 'consul'

## Initialization

Let's init the system

    $python go-d-scheduler.py init


As we use local system users, we need to create the user in the database (not needed for LDAP) with an existing system user


    $ id osallou
    uid=1000(osallou) gid=1000(osallou) groups=1000(osallou)

    # user: osallou, password: test, home directory /home/osallou

    $python path_to_install/go-docker/seed/create_local_user.py -c path_to_install/go-docker/go-d.ini -l osallou -p test -h /home/osallou --uid 1000 --gid 1000


As we use swarm, let's comment mesos plugin (to avoid its dependencies installation)

    cd path_to_install/go-docker/plugins
    $mv mesos.yapsy-plugin mesos.yapsy-plugin.skip


## Start processes

    $python go-d-scheduler.py start
    $python go-d-watcher.py start

To allow job archiving:

    $python go-d-archive start


To automatically archive old jobs, add a cron task calling go-d-clean.py

Optionally, start the FTP server (for user upload of data)

    $python go-d-ftp.py

# Web interface

## Setup

    $cd ../go-docker-web
    $python setup.py develop

    $cp production.ini.example production.ini


## Config

Edit properties

    global_properties = path_to_install/go-docker/go-d.ini
    admin = osallou   ( the system user you use)

## Start web server

    $export PYRAMID_ENV=prod
    $gunicorn -D -p godweb.pid --log-config=production.ini --paste production.ini

Server will listen on port 6543 => http://localhost:6543/app/#/

You can login with the user you created (osallou/test in example).
After login, you can execute your first job


# First job

Try following script:

    echo HelloGODOCKER
    ls $GODOCKER_HOME

and select the *home* mount volume

## Logs

Logs files are located in go-docker and go-docker-web directories. Log level can be modified in go-d.ini and production.ini
