from godocker.iWatcherPlugin import IWatcherPlugin
import logging
from godocker.utils import is_array_child_task, is_array_task
import datetime
import time

class FakeWatcher(IWatcherPlugin):
    def get_name(self):
        return "fake"

    def get_type(self):
        return "Watcher"

    def can_start(self, task):
        '''
        Checks if task can be scheduled for running now
        '''
        if task['meta']['name'] == 'norun':
            return False
        return True

    def can_run(self, task):
        '''
        Checks if task can continue to run. If task cannot run, this method must kill itself the task.

        Workflow:
          check if task is still running
          for each watcher, test watcher.can_run(task):
              if returns None
                  stop and remove from running tasks

        :param task: current task
        :type task: Task
        :return: Task or None if running checks should continue
        '''
        self.logger.debug('MaxLifespanWatcher:MaxReached:Test:'+str(task['id']))
        if 'maxlifespan' not in self.cfg:
            self.logger.error('maxlifespan not defined in config')
            return task
        maxlifespan = self.cfg.maxlifespan
        if 'maxlifespan' in task['requirements'] and task['requirements']['maxlifespan'] is not None:
            maxlifespan = task['requirements']['maxlifespan']
        dt = datetime.datetime.now()
        timestamp = time.mktime(dt.timetuple())
        running_date = task['status']['date_running']
        duration = self._get_duration(maxlifespan)
        if duration > -1 and timestamp - running_date > duration:
            self.logger.debug('MaxLifespanWatcher:MaxReached:Kill:'+str(task['id']))
            task['status']['reason'] = 'Max duration reached'
            self.kill_tasks([task])
            return None
        return task
