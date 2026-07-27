"""Pydantic model for custom flow (user-story) types, mirroring testing-service."""

from datetime import datetime

from minitest_cli.models.base import CamelModel


class CustomFlowType(CamelModel):
    id: str
    tenant_id: str
    name: str
    icon: str
    color: str
    usage_prompt: str | None = None
    created_at: datetime


class FlowTypeListItem(CamelModel):
    """One entry of ``flow-types list``: a built-in value or a custom type.

    Built-ins carry only a name; the presentation fields are custom-type only.
    """

    name: str
    custom: bool
    id: str | None = None
    icon: str | None = None
    color: str | None = None
    usage_prompt: str | None = None

    @classmethod
    def builtin(cls, name: str) -> "FlowTypeListItem":
        return cls(name=name, custom=False)

    @classmethod
    def from_custom(cls, custom_type: CustomFlowType) -> "FlowTypeListItem":
        return cls(
            name=custom_type.name,
            custom=True,
            id=custom_type.id,
            icon=custom_type.icon,
            color=custom_type.color,
            usage_prompt=custom_type.usage_prompt,
        )
