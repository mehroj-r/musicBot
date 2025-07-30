from pymongo.asynchronous.collection import AsyncCollection

from core.db import db

class CollectionDescriptor:

    def __get__(self, instance, owner) -> AsyncCollection:
        if owner.db_collection == '_':
            raise ValueError("db_collection must be set in the model class")
        return db[owner.db_collection]