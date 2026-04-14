"""Models for maintenance check responses."""

from minitest_cli.models.base import CamelModel


class MaintenanceCheckResponse(CamelModel):
    """Response from creating a maintenance check acknowledgment."""

    id: str
    app_id: str
    commit_sha: str
    created_at: str
