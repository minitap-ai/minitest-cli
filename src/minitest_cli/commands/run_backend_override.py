"""One-run backend API URL flags shared by the commands that start runs."""

from typing import Annotated

import typer

from minitest_cli.models.batch import BackendApiRunOverride

BackendBaseUrlOpt = Annotated[
    str | None,
    typer.Option(
        "--backend-base-url",
        help="Backend API base URL for this run only (the app's backend API must be on).",
    ),
]
BackendOpenapiUrlOpt = Annotated[
    str | None,
    typer.Option(
        "--backend-openapi-url",
        help="OpenAPI document URL for this run only (the app's backend API must be on).",
    ),
]


def backend_api_override(
    base_url: str | None, openapi_url: str | None
) -> BackendApiRunOverride | None:
    if base_url is None and openapi_url is None:
        return None
    return BackendApiRunOverride(base_url=base_url, openapi_url=openapi_url)
