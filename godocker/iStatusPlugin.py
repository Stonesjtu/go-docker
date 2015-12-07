from godocker.IGoDockerPlugin import IGoDockerPlugin

class IStatusPlugin(IGoDockerPlugin):
    '''
    Status plugins interface
    '''

    def keep_alive(self, name, proctype=None):
        '''
        Ping/trigger/record process status as being *ON*

        :param name: process identifier
        :type name: str
        :param proctype: process type
        :type proctype: str
        :return: bool return False in case of failure
        '''
        return True

    def status(self):
        '''
        Get processes status

        :return: list List of status information for all processes
        '''
        return []
