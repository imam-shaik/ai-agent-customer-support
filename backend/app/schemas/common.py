"""Shared schema base.

API payloads use camelCase (matching the existing frontend mock
contracts exactly) while Python code stays snake_case. Both spellings
are accepted on input via populate_by_name.
"""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
    )
