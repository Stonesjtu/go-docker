import os
import shutil
import logging
import re
from godocker.IStorage import IStorage


class PairtreeObject(object):

    def __init__(self, path):
        self.path = path
        if not os.path.exists(self.path):
            os.makedirs(self.path)

    def add_bytestream(self, name, content, path=None):
        dir_path = self.path
        if path is not None:
            dir_path = os.path.join(self.path, path)
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)
        objfile = open(os.path.join(dir_path, name), "w")
        objfile.write(content)
        objfile.close()
        return


class PairtreeStorageFactory(object):
    '''
    Code from https://github.com/edsu/ptree

    Derived from work:
        ptree draws from Ben O'Steen's PairTree Python module, which provides a lot more functionality for storing bitstreams on disk. ptree intentionally focuses soley on the identifier/filepath mapping, and leaves IO operations up to you. The unit tests were shamlessly stolen from John Kunze's File::PairTree.

    License: CC0
    '''
    _encode_regex = re.compile(r"[\"*+,<=>?\\^|]|[^\x21-\x7e]", re.U)
    _decode_regex = re.compile(r"\^(..)", re.U)
    _encode_map = { '/' : '=',  ':' : '+',  '.' : ','  } # not easy on the eyes
    _decode_map = dict([(v, k) for k, v in list(_encode_map.items())]) # reversed

    def get_store(self, store_dir, uri_base='file://'):
        '''
        Get a pairtree manager
        :return: self
        '''
        self.store_dir  = os.path.join(store_dir, 'pairtree_root')
        logging.warn("Create storage directory: "+self.store_dir)
        if not os.path.exists(self.store_dir):
            logging.info("Create storage directory: "+self.store_dir)
            os.makedirs(self.store_dir)
        self.uri_base = uri_base
        return self


    def id2ptree(self, id, sep="/", relpath=False):
        """Pass in a identifier and get back a PairTree path. Optionally
        you can pass in the path separator (default is /). Set relpath=True to
        omit the leading separator.
        """
        if sep == "": sep = "/"
        return (not relpath and sep or "") + sep.join(self._split_id(id)) + (not relpath and sep or "")


    def ptree2id(self, path, sep="/"):
        """Pass in a PairTree path and get back the identifier that it maps to.
        """
        parts = path.strip().split(sep)
        id_parts = []
        for part in parts:
            if len(part) == 2:
                id_parts.append(part)
            elif len(part) == 1:
                if id_parts:
                    id_parts.append(part)
                    break
            elif len(part) > 2:
                if id_parts:
                    break
        return self._decode("".join(id_parts))


    def _split_id(self, id):
        encoded_id = self._encode(id)
        parts = []
        while encoded_id:
            parts.append(encoded_id[:2])
            encoded_id = encoded_id[2:]
        return parts


    def _encode(self, s):
        #s = s.encode('utf-8')

        s = self._encode_regex.sub(self._char2hex, s)
        parts = []
        for char in s:
            parts.append(PairtreeStorageFactory._encode_map.get(char, char))
        return "".join(parts)


    def _decode(self, id):
        parts = []
        for char in id:
            parts.append(PairtreeStorageFactory._decode_map.get(char, char))
        dec_id = "".join(parts)
        return PairtreeStorageFactory._decode_regex.sub(self._hex2char, dec_id).decode("utf-8")


    def _char2hex(self, m):
        return "^%02x"%ord(m.group(0))


    def _hex2char(self, m):
        return chr(int(m.group(1), 16))


    def id2path(self, path):
        return os.path.join(self.id2ptree(path, relpath=True), 'obj')

    def create_object(self, id):
        obj_path = os.path.join(self.store_dir, self.id2path(id))
        return PairtreeObject(obj_path)

    def get_object(self, id):
        obj_path = os.path.join(self.store_dir, self.id2path(id))
        if not os.path.exists(obj_path):
            logging.debug('Requested object does not exists')
            return None
        return PairtreeObject(obj_path)


class PairtreeStorage(IStorage):
    '''
    Manage the storage directories of tasks in a pairtree structure
    '''

    def __init__(self, cfg):
        self.cfg = cfg
        if not self.cfg['shared_dir']:
            dirname, filename = os.path.split(os.path.abspath(__file__))
            self.cfg['shared_dir'] = os.path.join(dirname, '..', 'godshared')
            if not os.path.exists(self.cfg['shared_dir']):
                os.makedirs(self.cfg['shared_dir'])

        #f = pairtree.PairtreeStorageFactory()
        f = PairtreeStorageFactory()
        self.store = f.get_store(store_dir=os.path.join(self.cfg['shared_dir'],'tasks'), uri_base="http://")

    def get_task_dir(self, task):
        '''
        Get directory where task files are written
        '''
        task_dir = os.path.join(self.cfg['shared_dir'],'tasks','pairtree_root',self.store.id2path(str(task['id'])),'task')
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
        os.chmod(task_dir, 0o777)
        return os.path.join(task_dir, path, name)


    def clean(self, task):
        '''
        Cleanup task directory

        :param task: current task
        :type task: dict
        '''
        job_dir = self.get_task_dir(task)
        if os.path.exists(job_dir):
            shutil.rmtree(job_dir)
