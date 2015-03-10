import sys
import signal
import os

from godocker.godscheduler import GoDScheduler


if __name__ == "__main__":
        daemon = GoDScheduler('/tmp/godsched.pid')
        config_file = 'go-d.ini'
        if 'GOD_CONFIG' in os.environ:
            config_file = os.environ['GOD_CONFIG']
        daemon.load_config(config_file)
        signal.signal(signal.SIGINT, daemon.signal_handler)

        if len(sys.argv) == 2:
                if 'start' == sys.argv[1]:
                        daemon.start()
                elif 'stop' == sys.argv[1]:
                        daemon.stop()
                elif 'restart' == sys.argv[1]:
                        daemon.restart()
                elif 'run' == sys.argv[1]:
                        daemon.run()
                elif 'init' == sys.argv[1]:
                        daemon.init()
                elif 'once' == sys.argv[1]:
                        daemon.run(False)
                else:
                        print "Unknown command"
                        sys.exit(2)
                sys.exit(0)
        else:
                print "usage: %s start|stop|restart|init|once" % sys.argv[0]
                sys.exit(2)
