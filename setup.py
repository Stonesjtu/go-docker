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
    'version': '1.0.2',
    'install_requires': ['nose',
                            'sphinx',
                            'pymongo',
                            'influxdb',
                            'python-ldap',
                            'docker-py',
                            'redis',
                            'yapsy',
                            'iso8601',
                            'mock',
                            'urllib3',
                            'gelfHandler',
                            'python-logstash',
                            'config',
                            'python-etcd',
                            'bcrypt' ],
    'packages': find_packages(),
    'include_package_data': True,
    'scripts': ['go-d-scheduler.py','go-d-watcher.py', 'go-d-clean.py'],
    'name': 'godsched'
}

setup(**config)
