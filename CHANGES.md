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
