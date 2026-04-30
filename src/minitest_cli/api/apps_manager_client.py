"""Async HTTP client for the apps-manager service.

Mirrors the shape of :class:`minitest_cli.api.client.ApiClient` but targets a
different base URL (``MINITEST_APPS_MANAGER_URL``). Reuses the same Supabase
JWT auth flow.
"""

from typing import Any

import httpx

from minitest_cli.core.auth import load_token
from minitest_cli.core.config import Settings

CHANNEL_HEADER = "X-Minitest-Channel"
CHANNEL_VALUE = "cli"
DEFAULT_TIMEOUT = 30.0
UPLOAD_TIMEOUT = 300.0  # 5 minutes for large file uploads


class AppsManagerClient:
    """Wraps httpx.AsyncClient pointed at the apps-manager service.

    Auth and channel headers are auto-injected just like
    :class:`minitest_cli.api.client.ApiClient`.

    Usage::

        async with AppsManagerClient(settings) as client:
            response = await client.post("/api/v1/tenants/<id>/apps", data=...)
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "AppsManagerClient":
        token = load_token(self._settings)
        self._client = httpx.AsyncClient(
            base_url=self._settings.apps_manager_url,
            headers={
                "Authorization": f"Bearer {token}",
                CHANNEL_HEADER: CHANNEL_VALUE,
            },
            timeout=DEFAULT_TIMEOUT,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        if self._client:
            await self._client.aclose()

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            msg = "AppsManagerClient must be used as an async context manager"
            raise RuntimeError(msg)
        return self._client

    async def get(self, path: str, **kwargs: Any) -> httpx.Response:
        """Send a GET request."""
        return await self._ensure_client().get(path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> httpx.Response:
        """Send a POST request."""
        return await self._ensure_client().post(path, **kwargs)

    async def upload_form(
        self,
        path: str,
        *,
        data: dict[str, str] | None = None,
        files: dict[str, Any] | None = None,
        timeout: float = UPLOAD_TIMEOUT,
        **kwargs: Any,
    ) -> httpx.Response:
        """Send a POST request with multipart form data and extended timeout."""
        client = self._ensure_client()
        return await client.post(
            path,
            data=data or {},
            files=files or {},
            timeout=timeout,
            **kwargs,
        )
