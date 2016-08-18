from godocker.IGoDockerPlugin import IGoDockerPlugin


class INetworkPlugin(IGoDockerPlugin):
    def networks(self):
        '''
        Get supported features

        :return: list of available networks within public/user/project
        '''
        return []

    def default_network(self):
        '''
        Default network label to use
        '''
        return 'public'

    def network(self, name):
        '''
        Get network name to use with executor

        :param name: label of the network
        :type name: str
        :return: str
        '''
        return None

    def create_network(self, network):
        '''
        Create a new network, if it does not exists, for user or project.

        Public network is already created

        :param network: name of the new network
        :type network: str
        :return: bool according to creation status
        '''
        return False

    def delete_network(self, network):
        '''
        Delete a network for user or project.

        Public network cannot be deleted

        :param network: name of the new network
        :type network: str
        :return: bool according to deletion status
        '''
        return False
