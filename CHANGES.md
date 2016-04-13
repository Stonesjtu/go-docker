1.0.3:
    GOD-22 Add Kubernetes executor (experimental)
    GOD-23 support scheduler failover
        high availability mode for schedulers (one active at a time)
        allow mesos reuse of frameworkID atfer a restart or by new leader
    GOD-21 get used/available resources from executor
    GOD-20 add Consul as StatusManager
    GOD-12 Add Python3 support
    GOD-18 Support multiple sotrage managers
    GOD-26 Add Alpine Linux support
    Add optional volumes_check config param to check if a volume exists before mounting it
    Add get_quota method in auth plugins so that user quota can be extracted from an external system, auth dependant.
    GOD-28 Add possiblity to open additional ports in container
    GOD-27 Add FTP server to upload user data (read only in container), directory available in container with $GODOCKER_DATA
1.0.2:
    minor error cases handling
    extract container id from TaskStatus in Mesos when available (mesos >= 0.23)
    add Temporary local volumes
        Use docker-plugin-zfs Docker volume plugin
        New configuration parameter: plugin_zfs
    add hostnames in etcd
    support optional guest users (not in system)*
    GOD-3 add node reservation support
    GOD-4 experimental resource management for GPUs
    GOD-10 allow interactive session in any image, godocker will try to install
         a ssh server if none is installed in the container.
    Fix #21 mesos start daemon failure
    GOD-14 change pairtree implementation for python 3 support
    switch ini config file to YAML format
    switch ldap library for python3 compat
1.0.1:
    encode script to UTF-8
    add Status plugins with etcd support: add new config parameter *status_policy*
    check volumes name to catch invalid volume injection
    add global try/catch to catch errors generating an exit
    fix authorization on volumes so that config cannot be overriden by standard user
    manage case where job was not running
    store job duration from god.info file info
    manage failure to kill, switch to UNKNOWN status
1.0.0: First release
