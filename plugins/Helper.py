
# the helper object that helps scheduler to communicate with Mongo database
# optional cache with redis

class RedisHelper(Object):

	def __init__(self, config):
		self.redis = redis.StrictRedis(
			host=config.host,
			port=config.port,
			db=config.db,
			decode_responses=True
			)
		self.prefix = config.prefix

	def _getTasks(self, condition):
		