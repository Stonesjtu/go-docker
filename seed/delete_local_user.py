import os
import json
import datetime
import time
import logging
import logging.config
import yaml
import argparse
import sys

from yapsy.PluginManager import PluginManager
from pymongo import MongoClient

from godocker.iAuthPlugin import IAuthPlugin


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('-c', '--config', dest="config", help="Configuration file")
    parser.add_argument('-l', '--login', dest="login", help="User identifier", required=True)

    args = parser.parse_args()

    config_file = 'go-d.ini'
    if args.config:
        config_file = args.config
    if not os.path.exists(config_file):
        logging.error("Configuration file not found")
        sys.exit(1)
    cfg= None
    with open(config_file, 'r') as ymlfile:
        cfg = yaml.load(ymlfile)

    if not cfg['plugins_dir'] or not os.path.exists(cfg['plugins_dir']):
        logging.error("Plugin directory not found")
        sys.exit(1)


    logger = logging.getLogger('root')
    if cfg['log_config'] is not None:
        for handler in list(cfg['log_config']['handlers'].keys()):
            cfg['log_config']['handlers'][handler] = dict(cfg['log_config']['handlers'][handler])
        logging.config.dictConfig(cfg['log_config'])
        logger = logging.getLogger('root')


    mongo = MongoClient(cfg['mongo_url'])
    db = mongo[cfg['mongo_db']]
    db_users = db.users

    # Build the manager
    simplePluginManager = PluginManager()
    # Tell it the default place(s) where to find plugins
    simplePluginManager.setPluginPlaces([cfg['plugins_dir']])
    simplePluginManager.setCategoriesFilter({
       "Auth": IAuthPlugin,
     })
    # Load all plugins
    simplePluginManager.collectPlugins()


    auth_policy = None
    if cfg['auth_policy'] != 'local':
        logging.error('Wrong auth policy, only local auth allows user creation')
        sys.exit(1)
    for pluginInfo in simplePluginManager.getPluginsOfCategory("Auth"):
        if pluginInfo.plugin_object.get_name() == cfg['auth_policy']:
             auth_policy = pluginInfo.plugin_object
             auth_policy.set_users_handler(db_users)
             auth_policy.set_config(cfg)
             auth_policy.set_logger(logger)
             print "Loading auth policy: "+auth_policy.get_name()


    user = auth_policy.delete_user(args.login)
    if user is not None:
        logging.info("User deleted: "+str(user))
    else:
        logging.error("Could not delete user")

if __name__ == '__main__':
    main()
