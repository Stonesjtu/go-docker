import os
import json
import datetime
import time
import logging
from config import Config
import argparse
import sys

from yapsy.PluginManager import PluginManager
from pymongo import MongoClient

from godocker.iAuthPlugin import IAuthPlugin


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('-c', '--config', dest="config", help="Configuration file")
    parser.add_argument('-l', '--login', dest="login", help="User identifier", required=True)
    parser.add_argument('-p', '--password', dest="password", help="User password", required=True)
    parser.add_argument('-e', '--email', dest="email", help="User email")
    parser.add_argument('-h', '--home', dest="homeDirectory", help="User home directory")

    args = parser.parse_args()

    config_file = 'go-d.ini'
    if args.config:
        config_file = args.config
    if not os.path.exists(config_file):
        logging.error("Configuration file not found")
        sys.exit(1)
    cfg = Config(config_file)

    if not cfg.plugins_dir or not os.path.exists(cfg.plugins_dir):
        logging.error("Plugin directory not found")
        sys.exit(1)

    mongo = MongoClient(cfg.mongo_url)
    db = mongo[cfg.mongo_db]
    db_users = db.users

    # Build the manager
    simplePluginManager = PluginManager()
    # Tell it the default place(s) where to find plugins
    simplePluginManager.setPluginPlaces([cfg.plugins_dir])
    simplePluginManager.setCategoriesFilter({
       "Auth": IAuthPlugin,
     })
    # Load all plugins
    simplePluginManager.collectPlugins()

    auth_policy = None
    if cfg.auth_policy != 'local':
        logging.error('Wrong auth policy, only local auth allows user creation')
        sys.exit(1)
    for pluginInfo in simplePluginManager.getPluginsOfCategory("Auth"):
        if pluginInfo.plugin_object.get_name() == cfg.auth_policy:
             auth_policy = pluginInfo.plugin_object
             auth_policy.set_users_handler(db_users)
             auth_policy.set_config(cfg)
             print "Loading auth policy: "+auth_policy.get_name()

    user = auth_policy.create_user(args.login, args.password, args.email, args.homeDirectory)
    logging.info("User created: "+str(user))

if __name__ == '__main__':
    main()
