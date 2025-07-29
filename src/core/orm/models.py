from typing import ClassVar

from pydantic import BaseModel
from pymongo import ReturnDocument

from core.db import db


class BaseORMModel(BaseModel):
    db_collection: ClassVar[str] = 'default_collection'

    @classmethod
    async def get(cls, **kwargs): # noqa
        document = await db[cls.db_collection].find_one(kwargs)
        return cls(**document) if document else None # noqa

    @classmethod
    async def find(cls, query: dict):
        document = await db[cls.db_collection].find(query)
        return [cls(**doc) for doc in await document.to_list(length=None)] if document else [] # noqa

    @classmethod
    async def create(cls, **kwargs):
        obj = cls(**kwargs) # noqa
        await db[cls.db_collection].insert_one(obj.model_dump())
        return obj

    @classmethod
    async def get_or_create(cls, defaults: dict = None, **kwargs,):

        if defaults:
            kwargs.update(defaults)

        obj = cls(**kwargs)  # noqa
        document = await db[cls.db_collection].find_one_and_update(
            kwargs,
            {'$setOnInsert': obj.model_dump() or {}},
            upsert=True,
            return_document=ReturnDocument.AFTER
        )
        return cls(**document) if document else obj # noqa