# Go-Docker

Cluster management tool with Docker

Manage user job (batch/interactive) submissions with Docker (like gridengine on
nodes). User does not need to have Docker rights, everything will go through the application.
Linked to the system users (or ldap), user will have their home mounted automatically as well as other configured directories according to required priviledges in container.
They will be to run jobs with their uid/gid or as root in the container.

User specify his job command line and requirements (docker image, cpu, ram).

## Tips

Remove old containers

docker  -H 127.0.0.1:2376  ps -a | awk 'NR > 1 {print $1}' | xargs docker  -H
127.0.0.1:2376 rm

swarm binpacking strategy:

bin/swarm manage --strategy binpacking -H 127.0.1:2376 nodes://127.0.0.1:2375
