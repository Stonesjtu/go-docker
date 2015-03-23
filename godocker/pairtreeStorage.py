import os
import pairtree
from godocker.IStorage import IStorage

class PairtreeStorage(IStorage):
    '''
    Manage the storage directories of tasks in a pairtree structure
    '''

    def __init__(self, cfg):
        self.cfg = cfg
        if not self.cfg.shared_dir:
            dirname, filename = os.path.split(os.path.abspath(__file__))
            self.cfg.shared_dir = os.path.join(dirname, '..', 'godshared')
            if not os.path.exists(self.cfg.shared_dir):
                os.makedirs(self.cfg.shared_dir)

        f = pairtree.PairtreeStorageFactory()
        self.store = f.get_store(store_dir=os.path.join(self.cfg.shared_dir,'tasks'), uri_base="http://")

    def get_task_dir(self, task):
        '''
        Get directory where task files are written
        '''
        task_dir = os.path.join(self.cfg.shared_dir,'tasks','pairtree_root',pairtree.id2path(str(task['id'])),'task')
        return task_dir

    def add_file(self, task, name, content, path=''):
        '''
        Add content to a file with content in task directory

        :param task: current task
        :type task: dict
        :param name: name of the file
        :type name: str
        :param content: file content
        :type content: str
        :param path: relative sub path
        :type path: str
        :return: path to the file
        '''
        task_dir = self.get_task_dir(task)
        if not os.path.exists(task_dir):
            task_obj = self.store.create_object(str(task['id']))
        else:
            task_obj = self.store.get_object(str(task['id']))

        subpath = 'task'
        if path:
            subpath = os.path.join(subpath, path)
        task_obj.add_bytestream(name, content, path=subpath)
        os.chmod(task_dir, 0777)
        return os.path.join(task_dir, path, name)
