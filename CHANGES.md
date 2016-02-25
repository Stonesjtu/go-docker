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
