

import json
import redis


# the helper object that helps scheduler to communicate with Mongo database
# optional cache with redis

class RedisHelper(object):

    def __init__(self, config):
        '''

        :param config: addict.Dict() object containing redis config
        '''
        self.redis = redis.StrictRedis(
            host=config.host,
            port=config.port,
            db=config.db,
            decode_responses=True
            )
        self.prefix = config.prefix


    def _get(self, item):
        return self.redis.get(self.prefix + ':' + item)

    def _set(self, item, value):
        return self.redis.set(self.prefix + ':' + item, value)

    def _pop(self, item):
        return self.redis.lpop(self.prefix + ':' + item)

    def _push(self, item, value):
        return self.redis.rpush(self.prefix + ':' + item, value)

    def get(self, item):
        return self._get(item)

    def set(self, item, value):
        return self._set(item, value)

    def push(self, item, value):
        return self._push(item, value)

    def getTasks(self, status):
        tasks = []
        task = self._pop(status)
        while task is not None:
            task = json.loads(task)
            tasks.append(task)
            task = self._pop(status)
        return tasks

    def setStatus(self, task_id, status):
        return self.set('over' + str(task_id), status)


class MongoHelper(object):

    def __init__(self, config):
        pass

    def update(self, target):
        pass