try:
    from setuptools import setup, find_packages
except ImportError:
    from distutils.core import setup

config = {
    'description': 'GO Docker scheduler',
    'author': 'Olivier Sallou',
    'url': '',
    'download_url': '',
    'author_email': 'olivier.sallou@irisa.fr',
    'version': '1.3.1',
    'install_requires': ['nose',
                            'PyJWT',
                            'PyYAML',
                            'sphinx',
                            'pymongo',
                            'influxdb',
                            'ldap3',
                            'docker-py',
                            'redis',
                            'yapsy',
                            'iso8601',
                            'mock',
                            'urllib3',
                            'graypy',
                            'python-logstash',
                            'python-etcd',
                            'python-consul',
                            'requests',
                            'strict-rfc3339',
                            'humanfriendly',
                            'pyopenssl',
                            'pysendfile',
                            'pyftpdlib',
                            'protobuf',
                            'bcrypt'],
    'packages': find_packages(),
    'include_package_data': True,
    'scripts': ['go-d-scheduler.py', 'go-d-watcher.py', 'go-d-clean.py', 'go-d-ftp.py', 'go-d-status.py', 'go-d-archive.py'],
    'name': 'godsched'
}

setup(**config)
