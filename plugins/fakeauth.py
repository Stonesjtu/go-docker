from godocker.iAuthPlugin import IAuthPlugin
import logging

import ldap

class FakeAuth(IAuthPlugin):
    def get_name(self):
        return "fake"

    def get_type(self):
        return "Auth"

    def bind_credentials(self, login, password):
        '''
        Check user credentials and return user info

        Returns a user dict:
                 {
                  'id' : userId,
                  'uidNumber': systemUserid,
                  'gidNumber': systemGroupid,
                  'email': userEmail,
                  'homeDirectory': userHomeDirectory
                  }
        '''
        if login != 'osallou':
            return None
        user = {
                 'id' : 'osallou',
                 'uidNumber': 1001,
                 'gidNumber': 1001,
                 'email': 'olivier.sallou@irisa.fr',
                 'homeDirectory': '/home/osallou'
               }
        return user



    def bind_api(self, apikey):
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
              'acl': 'rw'
            },
            { 'name': 'db',
              'acl': 'ro'
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
        volumes = []
        for req in requested_volumes:
            if req['name'] == 'home':
                req['path'] = user['homeDirectory']
                req['mount'] = '/home/'+user['id']
                volumes.append(req)
                continue
            if req['name'] == 'omaha':
                req['path'] = '/omaha-beach/'+user['id']
                req['mount'] = None
                volumes.append(req)
                continue
            if req['name'] == 'db':
                req['path'] = '/db'
                req['acl'] = 'ro'
                req['mount'] = None
                volumes.append(req)
                continue
        return volumes
