

class IStorage(object):

    def __init__(self, cfg):
        pass

    def get_task_dir(self, task):
        '''
        Get directory where task files are written
        '''
        return None

    def add_file(self, task, name, content):
        '''
        Add content to a file with content in task directory

        :param task: current task
        :type task: dict
        :param name: name of the file
        :type name: str
        :param content: file content
        :type content: str
        :return: path to the file
        '''
        return None
