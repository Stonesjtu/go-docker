from godocker.pairtreeStorage import PairtreeStorage
import logging


class StorageManager(object):

    implementations = {
        'pairtree': PairtreeStorage
    }

    @staticmethod
    def get_storage(cfg):
        '''
        Return a storage handler implementing iStorage interface
        Default = pairtreeStorage
        '''
        kind = 'pairtree'  # default
        if 'storage' in cfg:
            kind = cfg['storage']
        if kind not in StorageManager.implementations:
            logging.error('Storage manager ' + str(kind) + 'does not exists')
            return None
        handler = StorageManager.implementations[kind](cfg)
        return handler
