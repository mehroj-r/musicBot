from typing import ClassVar, Self

from pydantic import BaseModel
from pymongo import ReturnDocument
from pymongo.asynchronous.collection import AsyncCollection

from core.orm.descriptors import CollectionDescriptor


class BaseORMModel(BaseModel):
    db_collection: ClassVar[str] = '_'
    collection: ClassVar[AsyncCollection] = CollectionDescriptor()

    @classmethod
    async def get(cls, **kwargs) -> Self | None:

        if not kwargs:
            raise ValueError(f"{cls.__name__}: No criteria provided for retrieval.")

        # Handle soft deletion fields
        if hasattr(cls, 'deleted_at') and 'deleted_at' not in kwargs:
            kwargs['deleted_at'] = None
        elif hasattr(cls, 'is_deleted') and 'is_deleted' not in kwargs:
            kwargs['is_deleted'] = False

        document = await cls.collection.find_one(kwargs)
        return cls.model_validate(document) if document else None

    @classmethod
    async def filter(
            cls,
            query: dict,
            projection: dict = None,
            sort: list = None,
            limit: int = None
    ) -> list[Self]:

        if not query:
            raise ValueError(f"{cls.__name__}: No criteria provided for filtering.")

        # Handle soft deletion fields
        if hasattr(cls, 'deleted_at') and 'deleted_at' not in query:
            query['deleted_at'] = None
        elif hasattr(cls, 'is_deleted') and 'is_deleted' not in query:
            query['is_deleted'] = False

        cursor = cls.collection.find(query, projection=projection)
        if sort:
            cursor = cursor.sort(sort)
        if limit:
            cursor = cursor.limit(limit)

        document = await cursor.to_list(length=None)
        return [cls.model_validate(doc) for doc in document] if document else []

    @classmethod
    async def create(cls, **kwargs) -> Self:

        if not kwargs:
            raise ValueError(f"{cls.__name__}: No data provided for creation.")

        obj = cls(**kwargs) # noqa
        await cls.collection.insert_one(obj.model_dump())
        return obj

    @classmethod
    async def update(cls, query: dict, update_data: dict) -> Self | None:

        if not query:
            raise ValueError(f"{cls.__name__}: No criteria provided for update.")

        if not update_data:
            raise ValueError("No update data provided.")

        document = await cls.collection.find_one_and_update(
            filter=query,
            update={'$set': update_data},
            return_document=ReturnDocument.AFTER
        )
        return cls.model_validate(document) if document else None

    @classmethod
    async def delete(cls, many=False, **kwargs) -> int:

        if not kwargs:
            raise ValueError(f"{cls.__name__}: No criteria provided for deletion.")

        if hasattr(cls, 'deleted_at'):
            return await cls._soft_delete(many=many, **kwargs)

        return await cls._hard_delete(many=many, **kwargs)

    @classmethod
    async def _hard_delete(cls, many=False, **kwargs) -> int:

        if many:
            result = await cls.collection.delete_many(kwargs)
        else:
            result = await cls.collection.delete_one(kwargs)

        deleted_count = result.deleted_count

        if deleted_count == 0:
            raise ValueError(f"{cls.__name__}: No documents matched the criteria for deletion.")

        return deleted_count

    @classmethod
    async def _soft_delete(cls, many=False, **kwargs) -> int:
        raise NotImplementedError(
            f"{cls.__name__} does not support soft deletion. "
            "Please implement the _soft_delete method if soft deletion is required."
        )

    @classmethod
    async def exists(cls, **kwargs) -> bool:
        if not kwargs:
            raise ValueError(f"{cls.__name__}: No criteria provided for exists check.")

        # Include soft-deletion filtering
        if hasattr(cls, 'deleted_at') and 'deleted_at' not in kwargs:
            kwargs['deleted_at'] = None
        elif hasattr(cls, 'is_deleted') and 'is_deleted' not in kwargs:
            kwargs['is_deleted'] = False

        document = await cls.collection.find_one(kwargs, projection={
            "_id": 1 })
        return document is not None

    @classmethod
    async def get_or_create(cls, defaults: dict = None, **kwargs,):

        if not kwargs:
            raise ValueError(f"{cls.__name__}: No criteria provided for get_or_create.")

        create_data = {**defaults, **kwargs} if defaults else kwargs

        obj = cls(**create_data) # noqa
        document = await cls.collection.find_one_and_update(
            filter=kwargs,
            update={'$setOnInsert': obj.model_dump() or {}},
            upsert=True,
            return_document=ReturnDocument.AFTER
        )
        return cls.model_validate(document) if document else None