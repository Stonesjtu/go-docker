from godocker.iAuthPlugin import IAuthPlugin
import logging
import pwd
import grp
import bcrypt
import datetime
import random
import string

class LocalAuth(IAuthPlugin):
    '''
    Binds users against local user database. Users must be manually registered
    in database with the script seed/create_local_user.py (see -h for help).
    Local users *must* bind system users with their uid/gid/home directory, but
    password verification is done against database created password, not system
    password.
    '''

    def get_name(self):
        return "local"

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
        user_in_db = self.users_handler.find_one({'id': login})
        if user_in_db is None:
            return None

        if bcrypt.hashpw(password.encode('utf-8'), user_in_db['password'].encode('utf-8')) != user_in_db['password']:
            return None
        try:
            user = {
                 'id' :login,
                 'uidNumber': user_in_db['uid'],
                 'gidNumber': user_in_db['gid'],
                 'sgids': user_in_db['sgids'],
                 'email': user_in_db['email'],
                 'homeDirectory': user_in_db['homeDirectory']
               }
        except Exception:
            return None

        return user

    def create_user(self, login, password, email=None, homeDirectory=None, uid=None, gid=None, sgids=None):
        password_encrypt = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        try:
            if uid is None:
                uid = pwd.getpwnam( login ).pw_uid
            if gid is None:
                gid = pwd.getpwnam( login ).pw_gid
            if sgids is None:
                sgids = self.get_groups(login)
        except Exception as e:
            self.logger.error("User creation error: "+str(e))
            return None

        user = {
                'id': login,
                'password': password_encrypt,
                'type': 'local',
                'last': datetime.datetime.now(),
                'uid': uid,
                'gid': gid,
                'sgids': sgids,
                'homeDirectory': homeDirectory,
                'email': email,
                'credentials': {
                    'apikey': ''.join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(10)),
                    'private': '',
                    'public': ''
                },
                'usage':
                    {
                        'prio': 50,
                        'quota_time': 0,
                        'quota_cpu': 0,
                        'quota_ram': 0
                    }
                }

        self.users_handler.insert(user)

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
        user_in_db = self.users_handler.find_one({'id': login})
        if user_in_db is None:
            return None

        user = None
        try:
            user = {
                     'id' :login,
                     'uidNumber': user_in_db['uid'],
                     'gidNumber': user_in_db['gid'],
                     'sgids': user_in_db['sgids'],
                     'email': user_in_db['email'],
                     'homeDirectory': user_in_db['homeDirectory']
                   }
        except Exception:
            return None

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
            if req['name'] == 'home':
                if user['homeDirectory'] is None:
                    continue
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

            volumes.append(req)

        return volumes
