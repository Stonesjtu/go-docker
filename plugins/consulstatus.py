from godocker.iStatusPlugin import IStatusPlugin
import consul
import socket


class ConsulStatusAuth(IStatusPlugin):

    services = {}

    def get_name(self):
        return "consul"

    def get_type(self):
        return "Status"

    def keep_alive(self, name, proctype=None):
        '''
        Ping/trigger/record process status as being *ON*

        :param name: process identifier
        :type name: str
        :param proctype: process type
        :type proctype: str
        :return: bool return False in case of failure
        '''
        if proctype is None:
            proctype = 'undefined'

        if 'web_endpoint' not in self.cfg:
            self.cfg['web_endpoint'] = 'http://127.0.0.1:6543'

        try:
            c = consul.Consul()
            if proctype == 'web':
                if name not in ConsulStatusAuth.services:
                    c.agent.service.register(proctype, service_id=name, port=6543, tags=[proctype])
                    ConsulStatusAuth.services[name] = True
                    check = consul.Check.http(url=self.cfg['web_endpoint'], interval=20)
                    c.agent.check.register(name + '_check', check=check, service_id=name)
            elif proctype == 'ftp':
                if name not in ConsulStatusAuth.services:
                    hostname = socket.gethostbyaddr(socket.gethostname())[0]
                    c.agent.service.register(proctype, service_id=name, port=self.cfg['ftp']['port'], tags=[proctype])
                    ConsulStatusAuth.services[name] = True
                    check = consul.Check.tcp(host=hostname, port=self.cfg['ftp']['port'], interval=20)
                    c.agent.check.register(name + '_check', check=check, service_id=name)
            else:
                if name not in ConsulStatusAuth.services:
                    c.agent.service.register(proctype, service_id=name, tags=[proctype])
                    ConsulStatusAuth.services[name] = True
                    check = consul.Check.ttl('1m')
                    c.agent.check.register(name + '_check', check=check, service_id=name)

                c.agent.check.ttl_pass(name + '_check')

        except Exception as e:
            self.logger.error('Consul:Keep-Alive:Error:' + str(e))
            return False
        return True

    def status(self):
        '''
        Get processes status

        :return: list List of status information for all processes
        '''
        procs_status = []
        try:
            c = consul.Consul()
            checks = c.agent.checks()
            for check in list(checks.keys()):
                status = {
                'name': checks[check]['ServiceID'],
                'type': checks[check]['ServiceName']
                }
                if checks[check]['Status'] == 'passing':
                    status['status'] = True
                else:
                    status['status'] = False
                procs_status.append(status)
        except Exception as e:
            self.logger.error('Consul:Status:Error:' + str(e))
        return procs_status
