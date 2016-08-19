from godocker.iNetworkPlugin import INetworkPlugin


class WeaveNetwork(INetworkPlugin):

    available_networks = {
        'public': {
            'name': 'weave'
        }
    }

    def get_name(self):
        return "weave"

    def get_type(self):
        return "Network"

    def features(self):
        '''
        Get supported features

        :return: list of features
        '''
        return ['ip_per_container']

    def networks(self):
        '''
        Get supported features

        :return: list of available networks within public/user/project
        '''
        return ['public']

    def network(self, name, user_info=None):
        '''
        Get network name to use with executor

        :param name: label of the network
        :type name: str
        :param user_info: user information from job
        :type user_info: dict
        :return: str
        '''
        if name not in WeaveNetwork.available_networks:
            return None
        return WeaveNetwork.available_networks[name]['name']

    def create_network(self, network):
        '''
        Create a new network for user or project.

        Public network is already created
        Not supported by this weave plugin.

        :param network: name of the new network
        :type network: str
        :return: bool according to creation status
        '''
        return True

    def delete_network(self, network):
        '''
        Delete a network for user or project.

        Public network cannot be deleted
        Not supported by this weave plugin.

        :param network: name of the new network
        :type network: str
        :return: bool according to deletion status
        '''
        return True
