from pymongo import AsyncMongoClient
from pymongo.server_api import ServerApi


class MongoService:
    def __init__(self, uri: str, db_name: str):
        self._client = AsyncMongoClient(uri, server_api=ServerApi('1'), tz_aware=True)
        self._db_name = db_name

    async def init_db(self):
        await self._client.admin.command('ping')

    @property
    def db(self):
        return getattr(self._client, self._db_name)