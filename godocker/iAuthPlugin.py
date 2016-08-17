from godocker.IGoDockerPlugin import IGoDockerPlugin


class IAuthPlugin(IGoDockerPlugin):
    '''
    ACL plugins interface
    '''

    def get_quotas(self, id, is_group=False, guest=None):
        '''
        Get quota related info for user id.

        :param id: user or group identifier
        :type id: str
        :param is_group: define if identifier is a group
        :type is_group: bool
        :param guest: user id is authenticated via social auth (google, ...)
        :type guest: str
        :return: dict
                    {
                        'prio': 50,
                        'quota_time': 0,
                        'quota_cpu': 0,
                        'quota_ram': 0
                    }

        Zero value means unlimited, 0 < prio < 100
        '''
        return {
            'prio': 50,
            'quota_time': 0,
            'quota_cpu': 0,
            'quota_ram': 0
        }

    def can_run(self, task):
        '''
        Check if task can run (according to user etc...). If return False, then task is rejected

        :param task: task to schedule
        :type task: Task
        :return: bool
        '''
        return True

    def bind_credentials(self, login, password):
        '''
        Check user credentials and return user info

        Returns a user dict:
                 {
                  'id' : userId,
                  'uidNumber': systemUserid,
                  'gidNumber': systemGroupid,
                  'sgids': list of secondary group ids,
                  'email': userEmail,
                  'homeDirectory': userHomeDirectory
                  }
        '''
        return None

    def get_user(self, login):
        '''
        Get user information

        Returns a user dict:
                 {
                  'id' : userId,
                  'uidNumber': systemUserid,
                  'gidNumber': systemGroupid,
                  'sgids': list of user secondary group ids,
                  'email': userEmail,
                  'homeDirectory': userHomeDirectory
                  }
        '''
        return None

    def bind_api(self, login, apikey):
        '''
        Check api key and return user info (same than bind_credentials)
        '''
        return None

    def get_volumes(self, user, requested_volumes, root_access=False):
        '''
        Returns a list of container volumes to mount, with acls, according to user requested volumes.
        Returned volumes should set real path to requested volumes, possibliy changed requested acl.

        :param user: User returned by bind_credentials or bind_api
        :type user: dict
        :param requested_volumes: list of volumes user expects to be mounted in container
        :type requested_volumes: list
        :param root_access: user request root access to the container
        :type root_access: bool
        :return: list of volumes to mount

        Volumes path are system specific and this method must be implemented according to each system.

        If 'mount' is None, then mount path is the same than original directory.

        requested_volumes looks like:

        volumes: [
            { 'name': 'home',
              'acl': 'rw'
            },
            { 'name': 'omaha',
              'acl': 'rw',
              'path': '/omaha/$USERID',
              'mount': '/omaha/$USERID'
            },
            { 'name': 'db',
              'acl': 'ro',
              'path': '/db'
            },
        ]

        Return volumes:

            volumes: [
                { 'name': 'home',
                  'acl': 'rw',
                  'path': '/home/mygroup/myuserid',
                  'mount': '/home/myuserid'
                },
                { 'name': 'omaha',
                  'acl': 'ro',
                  'path': '/mynfsshare/myuserid'
                  'mount': None
                },
                { 'name': 'db',
                  'acl': 'ro',
                  'path': '/db',
                  'mount': None
                },
            ]


        '''
        return []
