"""Pydantic models for the app env-vars API (apps-manager)."""

from datetime import datetime

from minitest_cli.models.base import CamelModel


class AppEnvVarsResponse(CamelModel):
    """Response from the apps-manager env-vars endpoints.

    ``env_vars`` values are decrypted plaintext, so treat the whole payload
    as secret material.
    """

    id: str
    app_id: str
    tenant_id: str
    env_vars: dict[str, str]
    updated_at: datetime | None = None
