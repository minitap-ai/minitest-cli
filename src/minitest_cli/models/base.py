"""Shared base model for camelCase API responses."""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Base model that accepts camelCase JSON and exposes snake_case fields."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )
