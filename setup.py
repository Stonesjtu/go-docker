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
    'version': '1.0.3',
    'install_requires': ['nose',
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
                            'config',
                            'python-etcd',
                            'python-consul',
                            'bcrypt' ],
    'packages': find_packages(),
    'include_package_data': True,
    'scripts': ['go-d-scheduler.py','go-d-watcher.py', 'go-d-clean.py'],
    'name': 'godsched'
}

setup(**config)
