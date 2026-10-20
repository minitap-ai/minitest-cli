"""Build models: uploaded artifacts and builds produced from a GitHub commit."""

from datetime import datetime
from typing import Literal

from minitest_cli.models.base import CamelModel


class BuildVariant(CamelModel):
    """One member of an .aab bundle group: the emulator (x86_64) or the phone (arm64) build."""

    id: str
    status: str | None = None
    abis: list[str] | None = None
    device_build: bool = False
    supported_backends: list[str] | None = None
    error_summary: str | None = None


class BuildResponse(CamelModel):
    id: str
    app_id: str
    kind: str | None = None
    platform: str | None = None
    status: str | None = None
    storage_path: str | None = None
    original_name: str | None = None
    size_bytes: int | None = None
    commit_sha: str | None = None
    commit_title: str | None = None
    app_version: str | None = None
    build_number: str | None = None
    verification_status: str | None = None
    verification_reason: str | None = None
    error_class: str | None = None
    error_summary: str | None = None
    error_remediation: str | None = None
    error_fix_prompt: str | None = None
    error_raw: str | None = None
    created_at: datetime
    validation_warnings: list[dict] | None = None
    # .aab bundle groups (absent on older backends): the head build's native ABIs,
    # the group it belongs to, the backends its completed members can run on, and
    # every member of the group.
    abis: list[str] | None = None
    bundle_group_id: str | None = None
    supported_backends: list[str] | None = None
    variants: list[BuildVariant] | None = None


class BuildListResponse(CamelModel):
    items: list[BuildResponse]
    total: int
    page: int
    page_size: int


class BuildContext(CamelModel):
    commit_sha: str | None = None
    commit_title: str | None = None
    app_version: str | None = None
    build_number: str | None = None
    device_family: list[int] | None = None
    tablet_compatibility: Literal["supported", "incompatible", "unknown"] | None = None
    status: str | None = None
    error_class: str | None = None
    error_summary: str | None = None
    error_remediation: str | None = None
    error_fix_prompt: str | None = None
