from godocker.iAuthPlugin import IAuthPlugin
import logging
import pwd
import grp
import os

class FakeAuth(IAuthPlugin):
    def get_name(self):
        return "fake"

    def get_type(self):
        return "Auth"

    def get_groups(self, user_id):
        gids = [g.gr_gid for g in grp.getgrall() if user_id in g.gr_mem]
        return [grp.getgrgid(gid).gr_gid for gid in gids]


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
        if login == 'fake':
            return None
        try:
            user = {
                 'id' :login,
                 'uidNumber': pwd.getpwnam( login ).pw_uid,
                 'gidNumber': pwd.getpwnam( login ).pw_gid,
                 'sgids': self.get_groups(login),
                 'email': login+'@fake.org',
                 'homeDirectory': '/home/'+login
               }
        except Exception:
            user = {
                     'id' :login,
                     'uidNumber': 1001,
                     'gidNumber': 1001,
                     'sgids': [],
                     'email': login+'@fake.org',
                     'homeDirectory': '/home/'+login
                   }
        return user

    def get_user(self, login):
        '''
        Get user information

        Returns a user dict:
                 {
                  'id' : userId,
                  'uidNumber': systemUserid,
                  'gidNumber': systemGroupid,
                  'sgids': user secondary group ids,
                  'email': userEmail,
                  'homeDirectory': userHomeDirectory
                  }
        '''
        if login == 'fake':
            return None
        user = {
                 'id' :login,
                 'uidNumber': pwd.getpwnam( login ).pw_uid,
                 'gidNumber': pwd.getpwnam( login ).pw_gid,
                 'sgids': self.get_groups(login),
                 'email': login+'@fake.org',
                 'homeDirectory': '/home/'+login
               }
        return user

    def bind_api(self, login, apikey):
        '''
        Check api key and return user info (same than bind_credentials)
        '''
        return self.bind_credentials(login, apikey)

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
        volumes = []
        config_volumes = {}
        if len(requested_volumes) > 0:
            for vol in self.cfg['volumes']:
                config_volumes[vol['name']] = vol

        for req in requested_volumes:
            if req['name'] == 'go-docker':
                continue
            if req['name'] == 'god-ftp':
                continue
            if req['name'] == 'home':
                req['path'] = user['homeDirectory']
                req['mount'] = '/mnt/home'
            else:
                if req['name'] not in config_volumes:
                    continue
                req['path'] = config_volumes[req['name']]['path'].replace('$USERID', user['id'])
                if 'mount' not in config_volumes[req['name']] or config_volumes[req['name']]['mount'] is None or config_volumes[req['name']]['mount'] == '':
                    req['mount'] = req['path']
                else:
                    req['mount'] = config_volumes[req['name']]['mount'].replace('$USERID', user['id'])
            if config_volumes[req['name']]['acl'] == 'ro':
                req['acl'] = 'ro'

            if root_access:
                req['acl'] = 'ro'
            self.logger.debug("####"+str(self.cfg['volumes_check']))
            if 'volumes_check' in self.cfg and self.cfg['volumes_check'] and not os.path.exists(req['path']):
                self.logger.error('Volume path '+str(req['path'])+' does not exists')
                continue

            volumes.append(req)
        return volumes
