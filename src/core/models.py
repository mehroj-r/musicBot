from bson import ObjectId
import typing
import datetime

from pydantic import GetCoreSchemaHandler, Field
from pydantic_core import core_schema

from core.orm.models import BaseORMModel
from core.utils import get_current_time


class PyObjectId(ObjectId):
    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: type, handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, v: typing.Any) -> ObjectId:
        if isinstance(v, ObjectId):
            return v
        try:
            return ObjectId(str(v))
        except Exception:
            raise ValueError("Invalid ObjectId")


class TimestampedModel(BaseORMModel):
    created_at: datetime.datetime = Field(default_factory=lambda: get_current_time())
    updated_at: datetime.datetime = Field(default_factory=lambda: get_current_time())

    @classmethod
    async def update(cls, query: dict, update_data: dict) -> typing.Self | None:

        if not update_data:
            raise ValueError(f"{cls.__name__}: No update data provided.")

        update_data['updated_at'] = get_current_time()
        return await super().update(query, update_data)


class SoftDeleteModel(BaseORMModel):
    deleted_at: datetime.datetime | None = Field(default=None, description="Timestamp when the record was soft deleted")

    @classmethod
    async def _soft_delete(cls, many=False, **kwargs) -> int:
        update_data = {
            '$set': {'deleted_at': get_current_time() }
        }

        if many:
            result = await cls.collection.update_many(kwargs, update_data)
        else:
            result = await cls.collection.update_one(kwargs, update_data)

        count = result.modified_count
        if count == 0:
            raise ValueError(f"{cls.__name__}: No documents matched the criteria for soft deletion.")
        return count