import sys
import logging
import logging.config
import os
import yaml
import socket

import redis
from pymongo import MongoClient


from yapsy.PluginManager import PluginManager
from godocker.storageManager import StorageManager
from godocker.iAuthPlugin import IAuthPlugin
from godocker.iStatusPlugin import IStatusPlugin
import godocker.utils as godutils


from pyftpdlib.authorizers import DummyAuthorizer, AuthenticationFailed
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer


class GodFtpHandler(FTPHandler, object):

    god_cfg = None
    god_mongo = None
    logger = None

    '''
    Questions: file overwrite, how to? keep list of files and calculate total?
    async transfer need to use on_file_received
    risk on delete
    '''

    def quota(self, path, add=True):
        '''
        Check and update quota.

        :param path: file path
        :type path: str
        :param add: add or remove file
        :type add: bool
        :return: True if quota ok, else return False
        '''
        self.logger.debug('FTP:Quota: ' + str(path))
        file_size = os.stat(path).st_size
        filename = path.replace('/', '_').replace('.', '_')
        if self.god_cfg['ftp']['quota'] and add:
            # current_quota = self.god_mongo.users.find_one({'id': self.username})
            self.god_mongo.users.update({'id': self.username},
                                {'$set': {'ftp.quota.' + filename: file_size}})
        if self.god_cfg['ftp']['quota'] and not add:
            self.god_mongo.users.update({'id': self.username},
                                {'$unset': {'ftp.quota.' + filename: ''}})
        return True

    def check_quota(self):
        self.logger.debug('FTP:Quota:Check')
        if self.god_cfg['ftp']['quota']:
            max_size = godutils.convert_size_to_int(self.god_cfg['ftp']['quota'])
            current_quota = self.god_mongo.users.find_one({'id': self.username})
            if 'ftp' not in current_quota:
                current_quota['ftp'] = {'quota': {}}
            user_quota = 0
            for filename in list(current_quota['ftp']['quota'].keys()):
                user_quota += current_quota['ftp']['quota'][filename]
            self.logger.debug('FTP:User:' + self.username + ':Quota:' + str(current_quota['ftp']['quota']))
            if user_quota > max_size:
                self.logger.debug('FTP:User:' + self.username + ':Quota:Reached')
                return False
        return True

    def on_file_received(self, path):
        """Called every time a file has been succesfully received.
        "file" is the absolute name of the file just being received.
        """
        self.quota(path)

    def ftp_STOR(self, path, mode='w'):
        """Store a file (transfer from the client to the server).
        On success return the file path, else None.
        """
        self.logger.debug('FTP:ftp_STOR: ' + str(path))
        quota = self.check_quota()
        if not quota:
            self.respond('550 %s.' % 'max quota reached')
            return
        operation = super(GodFtpHandler, self).ftp_STOR(path, mode)
        return operation

    def ftp_APPE(self, path):
        """Append data to an existing file on the server.
        On success return the file path, else None.
        """
        self.logger.debug('FTP:ftp_APPE: ' + str(path))
        quota = self.check_quota()
        if not quota:
            self.respond('550 %s.' % 'max quota reached')
            return
        operation = super(GodFtpHandler, self).ftp_APPE(path)
        return operation

    def ftp_DELE(self, path):
        self.logger.debug('FTP:DELETE: ' + str(path))
        # quota = self.quota(path, add=False)
        operation = super(GodFtpHandler, self).ftp_DELE(path)
        return operation


class GodAuthorizer(DummyAuthorizer):

    def set_policy(self, policy):
        self.policy = policy

    def set_config(self, cfg):
        self.cfg = cfg

    def set_store(self, store):
        self.store = store

    def validate_authentication(self, username, apikey, handler):
        """Raises AuthenticationFailed if supplied username and
        password don't match the stored credentials, else return
        None.
        """
        msg = "Authentication failed."
        if not self.has_user(username):
            if username == 'anonymous':
                msg = "Anonymous access not allowed."
            raise AuthenticationFailed(msg)
        if username != 'anonymous':
            user = self.policy.bind_api(username, apikey)
            if user is None:
                raise AuthenticationFailed(msg)

    def get_home_dir(self, username):
        """Return the user's home directory.
        Since this is called during authentication (PASS),
        AuthenticationFailed can be freely raised by subclasses in case
        the provided username no longer exists.
        """
        user_info = {
            'id': 'user_' + username
            }
        home_dir = self.store.get_task_dir(user_info)
        if not os.path.exists(home_dir):
            self.store.add_file(user_info, 'README.txt', 'This is your personal storage for GoDocker, you have a quota of ' + self.cfg['ftp']['quota'])
        if sys.version_info.major == 2:
            home_dir = home_dir.encode('utf-8')
        return home_dir

    def has_user(self, username):
            """Whether the username exists in the virtual users table."""
            user = self.policy.get_user(username)
            if user is None:
                return False
            else:
                return True

    def get_msg_login(self, username):
        """Return the user's login message."""
        return 'Welcome to your GoDocker personal storage, this storage is in read-only mode in your container and available at $GODOCKER_DATA'

    def get_msg_quit(self, username):
        """Return the user's quitting message."""
        return 'Bye'

    def has_perm(self, username, perm, path=None):
        """Whether the user has permission over path (an absolute
        pathname of a file or a directory).
        Expected perm argument is one of the following letters:
        "elradfmwM".
        """
        user_perms = 'elradfmwM'
        '''

        if path is None:
            return perm in user_perms

        path = os.path.normcase(path)
        for dir in self.user_table[username]['operms'].keys():
            operm, recursive = self.user_table[username]['operms'][dir]
            if self._issubpath(path, dir):
                if recursive:
                    return perm in operm
                if (path == dir or os.path.dirname(path) == dir and not
                        os.path.isdir(path)):
                    return perm in operm

        return perm in self.user_table[username]['perm']
        '''
        return user_perms

    def get_perms(self, username):
        """Return current user permissions."""
        return 'elradfmwM'

    def override_perm(self, username, directory, perm, recursive=False):
        """Override permissions for a given directory."""
        '''
        self._check_permissions(username, perm)
        if not os.path.isdir(directory):
            raise ValueError('no such directory: %r' % directory)
        directory = os.path.normcase(os.path.realpath(directory))
        user_info = {
                'id': 'user_'+username
                }
        home_dir = self.store.get_task_dir(user_info)
        home = os.path.normcase(home_dir)
        if directory == home:
            raise ValueError("can't override home directory permissions")
        if not self._issubpath(directory, home):
            raise ValueError("path escapes user home directory")
        self.user_table[username]['operms'][directory] = perm, recursive
        '''
        return


class GodFTP(object):

    def __init__(self):
        config_file = 'go-d.ini'
        if 'GOD_CONFIG' in os.environ:
            config_file = os.environ['GOD_CONFIG']
        self.cfg = None
        with open(config_file, 'r') as ymlfile:
            self.cfg = yaml.load(ymlfile)

        godutils.config_backward_compatibility(self.cfg)

        if self.cfg['log_config'] is not None:
            for handler in list(self.cfg['log_config']['handlers'].keys()):
                self.cfg['log_config']['handlers'][handler] = dict(self.cfg['log_config']['handlers'][handler])
            logging.config.dictConfig(self.cfg['log_config'])
        self.logger = logging.getLogger('godocker-ftp')

        if not self.cfg['plugins_dir']:
            dirname, filename = os.path.split(os.path.abspath(__file__))
            self.cfg['plugins_dir'] = os.path.join(dirname, '..', 'plugins')

        self.store = StorageManager.get_storage(self.cfg)

        self.r = redis.StrictRedis(host=self.cfg['redis_host'], port=self.cfg['redis_port'], db=self.cfg['redis_db'], decode_responses=True)
        self.mongo = MongoClient(self.cfg['mongo_url'])
        self.db = self.mongo[self.cfg['mongo_db']]

        # Build the manager
        simplePluginManager = PluginManager()
        # Tell it the default place(s) where to find plugins
        simplePluginManager.setPluginPlaces([self.cfg['plugins_dir']])
        simplePluginManager.setCategoriesFilter({
                                                "Auth": IAuthPlugin,
                                                "Status": IStatusPlugin
         })
        # Load all plugins
        simplePluginManager.collectPlugins()

        # Activate plugins
        self.status_manager = None
        for pluginInfo in simplePluginManager.getPluginsOfCategory("Status"):
            if 'status_policy' not in self.cfg or not self.cfg['status_policy']:
                print("No status manager in configuration")
                break
            if pluginInfo.plugin_object.get_name() == self.cfg['status_policy']:
                self.status_manager = pluginInfo.plugin_object
                self.status_manager.set_logger(self.logger)
                self.status_manager.set_redis_handler(self.r)
                self.status_manager.set_config(self.cfg)
                print("Loading status manager: " + self.status_manager.get_name())

        self.auth_policy = None
        for pluginInfo in simplePluginManager.getPluginsOfCategory("Auth"):
            if pluginInfo.plugin_object.get_name() == self.cfg['auth_policy']:
                self.auth_policy = pluginInfo.plugin_object
                self.auth_policy.set_logger(self.logger)
                self.auth_policy.set_config(self.cfg)
                print("Loading auth policy: " + self.auth_policy.get_name())

        authorizer = GodAuthorizer()
        authorizer.set_policy(self.auth_policy)
        authorizer.set_store(self.store)
        authorizer.set_config(self.cfg)
        # authorizer.add_user("user", "12345", "/tmp/osallou", perm="elradfmw")
        # authorizer.add_anonymous("/tmp/nobody")

        self.handler = GodFtpHandler
        self.handler.authorizer = authorizer
        self.handler.god_mongo = self.db
        self.handler.god_cfg = self.cfg
        self.handler.logger = self.logger

    def start(self):
        self.hostname = godutils.get_hostname()
        self.proc_name = 'scheduler-' + self.hostname
        if self.status_manager is not None:
            self.status_manager.keep_alive(self.proc_name, 'ftp')
        server = FTPServer((self.cfg['ftp']['listen'], self.cfg['ftp']['port']), self.handler)
        server.serve_forever()


ftp_handler = GodFTP()
ftp_handler.start()
