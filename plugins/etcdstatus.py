from godocker.iStatusPlugin import IStatusPlugin
import logging
import etcd
import datetime
import time
import socket

class EtcdStatusAuth(IStatusPlugin):
    def get_name(self):
        return "etcd"

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
        try:
            client = etcd.Client(host=self.cfg['etcd_host'],
                                 port=self.cfg['etcd_port'])
            etcd_prefix = 'godocker'
            if self.cfg['etcd_prefix']:
                etcd_prefix = str(self.cfg['etcd_prefix'])
                if not etcd_prefix.startswith('/'):
                    etcd_prefix = '/'+etcd_prefix
            dt = datetime.datetime.now()
            timestamp = int(time.mktime(dt.timetuple()))
            if proctype is None:
                proctype = 'undefined'
            client.write(etcd_prefix+'/process/'+proctype+'/'+str(name),str(timestamp), ttl=3600)
            hostname = socket.gethostbyaddr(socket.gethostname())[0]
            client.write(etcd_prefix+'/hosts/'+proctype+'/'+str(name),str(hostname), ttl=3600)
        except Exception as e:
            self.logger.error('Etcd:Keep-Alive:Error:'+str(e))
            return False
        return True

    def status(self):
        '''
        Get processes status

        :return: list List of status information for all processes
        '''
        procs_status = []
        try:
            host = '127.0.0.1'
            if self.cfg['etcd_host']:
                host = self.cfg['etcd_host']
            port = 4001
            if self.cfg['etcd_port']:
                port = self.cfg['etcd_port']
            client = etcd.Client(host=host,
                                 port=self.cfg['etcd_port'])
            etcd_prefix = 'godocker'
            if self.cfg['etcd_prefix']:
                etcd_prefix = str(self.cfg['etcd_prefix'])
                if not etcd_prefix.startswith('/'):
                    etcd_prefix = '/'+etcd_prefix

            r = client.read(etcd_prefix+'/process')
            for child in r.children:
                procs = client.read(child.key)
                proc_type = child.key
                for proc in procs.children:
                    procs_status.append({'name': proc.key.split('/')[-1],
                                        'timestamp': int(proc.value),
                                        'type': proc_type})

        except Exception as e:
            self.logger.error('Etcd:Status:Error:'+str(e))
        return procs_status
