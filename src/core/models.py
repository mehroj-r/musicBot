from datetime import timedelta, timezone

import pytz
from bson import ObjectId
from pydantic import GetCoreSchemaHandler, Field, model_validator
from pydantic_core import core_schema
import typing
import datetime

from config import settings
from core.orm.models import BaseORMModel


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
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(pytz.timezone(settings.TIMEZONE)))
    updated_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(pytz.timezone(settings.TIMEZONE)))


class SoftDeleteModel(BaseORMModel):
    deleted_at: datetime.datetime | None = Field(default=None, description="Timestamp when the record was soft deleted")