"""Pydantic models for the user-story API, mirroring testing-service schemas."""

from datetime import datetime
from typing import Any

from minitest_cli.models.base import CamelModel


class AcceptanceCriteriaResponse(CamelModel):
    id: str
    user_story_id: str
    content: str
    created_at: datetime


class UserStoryResponse(CamelModel):
    id: str
    app_id: str
    name: str
    description: str | None = None
    type: str
    created_at: datetime


class UserStoryDetailResponse(UserStoryResponse):
    acceptance_criteria: list[AcceptanceCriteriaResponse] = []


class UserStoryListResponse(CamelModel):
    items: list[UserStoryResponse]
    total: int
    page: int
    page_size: int


class CreateUserStoryRequest(CamelModel):
    name: str
    description: str | None = None
    type: str = "other"
    acceptance_criteria: list[str] = []


class UpdateUserStoryRequest(CamelModel):
    name: str | None = None
    description: str | None = None
    type: str | None = None
    acceptance_criteria: list[str] | None = None

    def has_changes(self) -> bool:
        return any(v is not None for v in self.model_dump(exclude_none=False).values())

    def to_payload(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=True)
