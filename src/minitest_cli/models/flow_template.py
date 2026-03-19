"""Pydantic models for the flow-template API, mirroring testing-service schemas."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


def _to_camel(string: str) -> str:
    components = string.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


class CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)


class FlowType(StrEnum):
    login = "login"
    registration = "registration"
    checkout = "checkout"
    onboarding = "onboarding"
    search = "search"
    settings = "settings"
    navigation = "navigation"
    form = "form"
    profile = "profile"
    other = "other"


class AcceptanceCriteriaResponse(CamelModel):
    id: str
    flow_template_id: str
    content: str
    created_at: datetime


class FlowTemplateResponse(CamelModel):
    id: str
    app_id: str
    name: str
    description: str | None = None
    type: FlowType
    created_at: datetime


class FlowTemplateDetailResponse(FlowTemplateResponse):
    acceptance_criteria: list[AcceptanceCriteriaResponse] = []


class FlowTemplateListResponse(CamelModel):
    items: list[FlowTemplateResponse]
    total: int
    page: int
    page_size: int


class CreateFlowTemplateRequest(CamelModel):
    name: str
    description: str | None = None
    type: FlowType = FlowType.other  # type: ignore[assignment]
    acceptance_criteria: list[str] = []


class UpdateFlowTemplateRequest(CamelModel):
    name: str | None = None
    description: str | None = None
    type: FlowType | None = None
    acceptance_criteria: list[str] | None = None

    def has_changes(self) -> bool:
        return any(v is not None for v in self.model_dump(exclude_none=False).values())

    def to_payload(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=True)
