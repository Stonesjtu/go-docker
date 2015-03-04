from yapsy.IPlugin import IPlugin

class IAuthPlugin(IPlugin):

    def get_name(self):
        pass

    def set_config(self, cfg):
        self.cfg = cfg


    def set_logger(self, logger):
        '''
        Set logger for logging
        '''
        self.logger = logger
