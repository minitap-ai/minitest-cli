"""`minitest run all`: every scenario of the app."""

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.batch_helpers import post_batch
from minitest_cli.commands.run_backend_override import (
    BackendBaseUrlOpt,
    BackendOpenapiUrlOpt,
    backend_api_override,
)
from minitest_cli.commands.run_helpers import resolve_app, run_api_call
from minitest_cli.commands.run_tagged import print_batch_started
from minitest_cli.commands.run_targets import (
    AndroidBuildOpt,
    AndroidDeviceTypeOpt,
    AndroidPhysicalOpt,
    IosBuildOpt,
    IosDeviceTypeOpt,
    IosPhysicalOpt,
    WebOpt,
    build_targets,
)
from minitest_cli.commands.target_spec import TargetOpt, TargetsFileOpt, collect_specs
from minitest_cli.models.batch import BatchResponse, CreateBatchRequest


def run_all(
    ios_build: IosBuildOpt = None,
    android_build: AndroidBuildOpt = None,
    web: WebOpt = False,
    ios_device_type: IosDeviceTypeOpt = None,
    android_device_type: AndroidDeviceTypeOpt = None,
    ios_physical: IosPhysicalOpt = False,
    android_physical: AndroidPhysicalOpt = False,
    target: TargetOpt = None,
    targets_file: TargetsFileOpt = None,
    backend_base_url: BackendBaseUrlOpt = None,
    backend_openapi_url: BackendOpenapiUrlOpt = None,
) -> None:
    """Start a run covering every scenario of the app."""
    settings, app_id, json_mode = resolve_app()
    targets = build_targets(
        ios_build,
        android_build,
        web,
        ios_device_type,
        android_device_type,
        ios_physical,
        android_physical,
        collect_specs(target, targets_file),
    )

    async def _run_all() -> BatchResponse:
        async with ApiClient(settings) as client:
            body = CreateBatchRequest(
                targets=targets,
                backend_api_override=backend_api_override(backend_base_url, backend_openapi_url),
            )
            return await post_batch(client, app_id, body)

    print_batch_started(run_api_call(_run_all()), json_mode)
