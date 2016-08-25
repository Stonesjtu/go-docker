from godocker.iNetworkPlugin import INetworkPlugin


class CalicoNetwork(INetworkPlugin):

    available_networks = {}

    def get_name(self):
        return "calico"

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
        if 'public' not in CalicoNetwork.available_networks:
            if 'cni_public_network_name' in self.cfg['network']:
                CalicoNetwork.available_networks['public'] = {'name': self.cfg['network']['cni_public_network_name']}
        if name not in CalicoNetwork.available_networks:
            return None
        return CalicoNetwork.available_networks[name]['name']

    def create_network(self, network):
        '''
        Create a new network for user or project.

        Public network is already created
        Not supported by this calico plugin.

        :param network: name of the new network
        :type network: str
        :return: bool according to creation status
        '''
        return True

    def delete_network(self, network):
        '''
        Delete a network for user or project.

        Public network cannot be deleted
        Not supported by this calico plugin.

        :param network: name of the new network
        :type network: str
        :return: bool according to deletion status
        '''
        return True
