import sys
import signal
import os

from godocker.godarchiver import GoDArchiver

'''
Daemon in charge of archiving old jobs.

Sets status to archived and delete files in job directory.
'''

if __name__ == "__main__":
        pid_file = '/tmp/godarchiver.pid'
        if 'GOD_PID' in os.environ:
            pid_file = os.environ['GOD_PID']
        daemon = GoDArchiver(pid_file)
        config_file = 'go-d.ini'
        if 'GOD_CONFIG' in os.environ:
            config_file = os.environ['GOD_CONFIG']
        daemon.load_config(config_file)
        signal.signal(signal.SIGINT, daemon.signal_handler)
        daemon.stop_daemon = False
        if len(sys.argv) == 2:
                if 'start' == sys.argv[1]:
                        daemon.start()
                elif 'stop' == sys.argv[1]:
                        daemon.stop_daemon = True
                        daemon.stop()
                elif 'restart' == sys.argv[1]:
                        daemon.restart()
                elif 'run' == sys.argv[1]:
                        daemon.run()
                elif 'once' == sys.argv[1]:
                        daemon.run(False)
                elif 'status' == sys.argv[1]:
                        status = daemon.status()
                        print("Last keep-alive: %s" % str(status))
                elif 'config-reload' == sys.argv[1]:
                        daemon.ask_reload_config()
                        sys.exit(0)
                else:
                        print("Unknown command")
                        sys.exit(2)
                sys.exit(0)
        else:
                print("usage: %s start|stop|restart|once|config-reload" % sys.argv[0])
                sys.exit(2)
