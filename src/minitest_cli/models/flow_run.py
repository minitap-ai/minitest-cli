"""Pydantic models for the flow-run API (test execution)."""

from datetime import datetime
from enum import StrEnum

from minitest_cli.models.base import CamelModel


class RunStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class AcceptanceCriteriaResult(CamelModel):
    """A single acceptance-criteria evaluation result."""

    id: str
    flow_id: str
    acceptance_criteria_id: str
    platform: str
    success: bool
    fail_reason: str | None = None
    created_at: datetime


class FlowRunResponse(CamelModel):
    """Response from POST /flows or GET /flows/{id}."""

    id: str
    flow_template_id: str
    flow_template_name: str | None = None
    tenant_id: str | None = None
    status: RunStatus
    ios_build_id: str | None = None
    android_build_id: str | None = None
    ios_recording_path: str | None = None
    android_recording_path: str | None = None
    ios_recording_url: str | None = None
    android_recording_url: str | None = None
    ios_error_message: str | None = None
    android_error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    results: list[AcceptanceCriteriaResult] = []


class CreateFlowRunRequest(CamelModel):
    """Request body for POST /flows."""

    flow_template_id: str
    ios_build_id: str | None = None
    android_build_id: str | None = None


class FlowRunListResponse(CamelModel):
    """Paginated response from GET /flow-templates/{id}/flows."""

    items: list[FlowRunResponse]
    total: int
    page: int
    page_size: int


class BatchFlowRunRequest(CamelModel):
    """Request body for POST /flows/batch."""

    ios_build_id: str | None = None
    android_build_id: str | None = None


class BatchFlowRunResponse(CamelModel):
    """Response from POST /flows/batch."""

    flows: list[FlowRunResponse]
    message: str | None = None
