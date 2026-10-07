import json

import httpx
import pytest
import typer
from pydantic import ValidationError
from typer.testing import CliRunner

from minitest_cli.commands.run import app
from minitest_cli.commands.run_display import display_run_result
from minitest_cli.commands.run_targets import build_targets
from minitest_cli.commands.verdicts_projection import project_story, project_target
from minitest_cli.core.config import Settings
from minitest_cli.models.batch import BatchTargetView, CreateBatchRequest
from minitest_cli.models.story_run import StoryRunResponse
from minitest_cli.models.targets import BatchTarget, DeviceType, target_label

STORY_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
SHA = "a" * 40
IPHONE_WARNING = (
    "This iPhone-only build may run on iPad in compatibility mode; "
    "the run does not establish native tablet-layout coverage."
)
UNKNOWN_WARNING = (
    "iPad support is unknown for this build; "
    "the run does not establish native tablet-layout coverage."
)
RUN = {
    "id": "11111111-2222-3333-4444-555555555555",
    "userStoryId": STORY_ID,
    "createdAt": "2026-10-07T10:00:00Z",
    "platforms": [],
}


@pytest.fixture
def requests(monkeypatch, tmp_path):
    settings = Settings(
        api_url="https://testing.example",
        token="test-token",
        app_id="app-123",
        config_dir=tmp_path,
    )
    monkeypatch.setattr(typer.Context, "settings", settings, raising=False)
    monkeypatch.setattr(typer.Context, "json_mode", True, raising=False)
    monkeypatch.setattr(typer.Context, "app_flag", None, raising=False)
    captured = []

    def handle(request):
        captured.append(request)
        if request.url.path.endswith("/tags"):
            return httpx.Response(200, json=[{"id": "tag-1", "name": "smoke"}])
        if request.url.path.endswith("/user-stories"):
            assert request.url.params.get_list("tagId") == ["tag-1"]
            return httpx.Response(200, json={"items": [{"id": STORY_ID}], "total": 1})
        if request.method == "POST":
            assert request.url.path == "/api/v1/apps/app-123/batches"
            body = json.loads(request.content)
            ready = not body.get("commitSha")
        else:
            assert request.url.path == "/api/v1/apps/app-123/batches/batch-1"
            body = json.loads(next(r for r in captured if r.method == "POST").content)
            ready = True
        targets = []
        for target in body.get("targets", []):
            tablet = target.get("deviceType") == "tablet" and target["platform"] == "ios"
            warning = (
                UNKNOWN_WARNING if target.get("buildId") == "unknown-build" else IPHONE_WARNING
            )
            targets.append(
                {
                    **target,
                    "id": f"target-{target['platform']}",
                    "label": target_label(target["platform"], None, None, target.get("deviceType")),
                    "compatibilityWarnings": [warning] if ready and tablet else [],
                }
            )
        return httpx.Response(
            200,
            json={
                "id": "batch-1",
                "appId": "app-123",
                "tenantId": "tenant-1",
                "source": "api",
                "status": "completed" if request.method == "GET" else "pending",
                "createdAt": RUN["createdAt"],
                "commitSha": body.get("commitSha"),
                "storyRuns": [RUN],
                "targets": targets,
            },
        )

    async_client = httpx.AsyncClient

    def transport_client(**kwargs):
        return async_client(**kwargs, transport=httpx.MockTransport(handle))

    monkeypatch.setattr(httpx, "AsyncClient", transport_client)
    return captured


class TestNativeDeviceTypes:
    @pytest.mark.parametrize(
        "build,warning", [("ios-build", IPHONE_WARNING), ("unknown-build", UNKNOWN_WARNING)]
    )
    def test_launch_warning_is_nonblocking_and_keeps_json_stdout_clean(
        self, requests, build, warning
    ):
        result = CliRunner().invoke(
            app,
            ["start", STORY_ID, "--no-watch", "--ios-build", build, "--ios-device-type", "tablet"],
        )

        assert result.exit_code == 0, result.output
        assert warning in " ".join(result.stderr.split())
        assert json.loads(result.stdout)["runId"] == RUN["id"]
        assert [r.method for r in requests] == ["POST"]

    def test_commit_reports_compatibility_when_the_build_becomes_ready(self, requests):
        result = CliRunner().invoke(
            app, ["from-commit", SHA, "--platform", "ios", "--ios-device-type", "tablet"]
        )

        assert result.exit_code == 0, result.output
        assert IPHONE_WARNING in " ".join(result.stderr.split())
        assert result.stderr.count("This iPhone-only build") == 1
        assert json.loads(result.stdout)["status"] == "completed"
        assert [(r.method, r.url.path) for r in requests] == [
            ("POST", "/api/v1/apps/app-123/batches"),
            ("GET", "/api/v1/apps/app-123/batches/batch-1"),
        ]

    def test_omitted_types_preserve_phone_request_payload(self):
        body = CreateBatchRequest(targets=build_targets("ios-build", "android-build", True))
        assert body.model_dump(mode="json", by_alias=True, exclude_none=True) == {
            "targets": [
                {"platform": "ios", "buildId": "ios-build"},
                {"platform": "android", "buildId": "android-build"},
                {"platform": "web"},
            ]
        }
        assert target_label("ios", None, None) == "iOS"
        assert target_label("android", None, None, "phone") == "Android"

    @pytest.mark.parametrize(
        "args,expected",
        [
            (["start", STORY_ID, "--no-watch"], {"userStoryIds": [STORY_ID]}),
            (["start", "--tag", "smoke"], {"userStoryIds": [STORY_ID]}),
            (["all"], {}),
        ],
    )
    def test_commands_forward_selected_tablet_targets(self, requests, args, expected):
        result = CliRunner().invoke(
            app,
            [
                *args,
                "--ios-build",
                "ios-build",
                "--ios-device-type",
                "tablet",
                "--android-build",
                "android-build",
                "--android-device-type",
                "phone",
            ],
        )
        assert result.exit_code == 0, result.output
        assert json.loads(requests[-1].content) == {
            **expected,
            "targets": [
                {"platform": "ios", "buildId": "ios-build", "deviceType": "tablet"},
                {"platform": "android", "buildId": "android-build", "deviceType": "phone"},
            ],
        }

    @pytest.mark.parametrize(
        "options,expected",
        [
            ([], {"commitSha": SHA}),
            (["--platform", "web"], {"commitSha": SHA, "platforms": ["web"]}),
            (
                ["--ios-device-type", "tablet"],
                {
                    "commitSha": SHA,
                    "targets": [
                        {"platform": "ios", "deviceType": "tablet"},
                        {"platform": "android"},
                    ],
                },
            ),
            (
                ["--platform", "android", "--android-device-type", "tablet"],
                {"commitSha": SHA, "targets": [{"platform": "android", "deviceType": "tablet"}]},
            ),
        ],
    )
    def test_commit_sends_bare_targets_only_for_explicit_device_types(
        self, requests, options, expected
    ):
        result = CliRunner().invoke(app, ["from-commit", SHA, "--no-watch", *options])
        assert result.exit_code == 0, result.output
        assert json.loads(requests[-1].content) == expected

    @pytest.mark.parametrize(
        "args,flag",
        [
            (["all", "--web", "--ios-device-type", "phone"], "--ios-device-type"),
            (
                ["start", STORY_ID, "--android-build", "build", "--ios-device-type", "tablet"],
                "--ios-device-type",
            ),
            (
                [
                    "start",
                    "--tag",
                    "smoke",
                    "--ios-build",
                    "build",
                    "--android-device-type",
                    "phone",
                ],
                "--android-device-type",
            ),
            (
                ["from-commit", SHA, "--platform", "web", "--android-device-type", "tablet"],
                "--android-device-type",
            ),
            (["all", "--android-device-type", "tablet"], "--android-device-type"),
        ],
    )
    def test_device_option_cannot_select_an_os(self, requests, args, flag):
        result = CliRunner().invoke(app, args)
        assert result.exit_code == 1
        assert flag in result.output
        assert "lane to be selected" in result.output
        assert requests == []

    @pytest.mark.parametrize(
        "target",
        [
            {"platform": "web"},
            {"platform": "mobileweb"},
            {"platform": "ios", "backend": "physical"},
            {"platform": "android", "backend": "edge"},
            {"platform": "android", "browser": "chrome", "url": "https://example.com"},
        ],
    )
    def test_device_types_are_native_cloud_only(self, target):
        with pytest.raises(ValidationError):
            BatchTarget.model_validate({**target, "deviceType": "phone"})

    def test_outputs_keep_tablet_identity_and_prefer_server_labels(self, capsys):
        target = BatchTargetView.model_validate(
            {
                "id": "target-1",
                "platform": "ios",
                "deviceType": "tablet",
                "label": "iOS · Tablet",
                "buildContext": {"deviceFamily": [1], "tabletCompatibility": "incompatible"},
            }
        )
        context = target.model_dump(mode="json", by_alias=True)["buildContext"]
        assert context["deviceFamily"] == [1]
        assert context["tabletCompatibility"] == "incompatible"
        projected = project_target(target).model_dump(mode="json", by_alias=True, exclude_none=True)
        assert projected["deviceType"] == "tablet"
        assert projected["label"] == "iOS · Tablet"
        run = StoryRunResponse.model_validate(
            {
                **RUN,
                "platforms": [
                    {"platform": "ios", "deviceType": "tablet", "label": "Server iPad label"},
                    {"platform": "android", "deviceType": "tablet"},
                ],
                "results": [
                    {
                        "id": "result-1",
                        "storyRunId": RUN["id"],
                        "criterionVersionId": "criterion-1",
                        "platform": "ios",
                        "success": True,
                        "createdAt": RUN["createdAt"],
                    }
                ],
            }
        )
        display_run_result(run, json_mode=False)
        output = capsys.readouterr()
        assert "Server iPad label" in output.out
        assert "Android · Tablet" in output.out + output.err
        story = project_story(run, platform=None, only_failed=False, verbose=False)
        assert story and story.platforms[0].device_type == DeviceType.tablet
        assert story.platforms[0].label == "Server iPad label"
