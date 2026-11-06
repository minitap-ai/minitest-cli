"""`--target` / `--targets-file` on the run commands, against a fake batches API."""

import json
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from minitest_cli.commands.run import app as run_app
from tests._commit_transport import cli_context, make_settings, routed

runner = CliRunner()

APP = "a0d9820f-5136-4f70-b46b-e5966f56bfb5"
BATCHES = f"/api/v1/apps/{APP}/batches"
SIM = "5c4ed000-0000-4000-8000-00000000b001"
DEVICE = "5c4ed000-0000-4000-8000-00000000b002"
APK = "5c4ed000-0000-4000-8000-00000000b003"
SHA = "a" * 40


def _batch(targets: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": "batch-1",
        "appId": APP,
        "tenantId": "tenant-1",
        "source": "cli",
        "status": "pending",
        "createdAt": "2026-11-06T10:00:00Z",
        "storyRuns": [],
        "targets": [
            {**t, "id": f"t{i}", "label": "iOS", "backend": t.get("backend", "cloud")}
            for i, t in enumerate(targets)
        ],
    }


class FakeBatches:
    def __init__(self, refusal: httpx.Response | None = None) -> None:
        self.refusal = refusal
        self.bodies: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.url.path == BATCHES and request.method == "POST"
        body = json.loads(request.content)
        self.bodies.append(body)
        return self.refusal or httpx.Response(201, json=_batch(body.get("targets", [])))


def _run(tmp_path, args: list[str], backend: FakeBatches | None = None, json_mode=True):
    backend = backend or FakeBatches()
    with cli_context(make_settings(tmp_path), json_mode=json_mode), routed(backend):
        result = runner.invoke(run_app, args)
    return result, backend


class TestTargetsInTheBatchBody:
    def test_two_ios_versions_share_the_ios_build(self, tmp_path):
        result, backend = _run(
            tmp_path,
            ["all", "--ios-build", SIM, "--target", "platform=ios,os=26",
             "--target", "platform=ios,os=27.0"],
        )  # fmt: skip

        assert result.exit_code == 0, result.output
        assert backend.bodies[0]["targets"] == [
            {"platform": "ios", "buildId": SIM, "osVersion": "26"},
            {"platform": "ios", "buildId": SIM, "osVersion": "27"},
        ]

    def test_physical_model_web_versions_and_legacy_android_combine(self, tmp_path):
        result, backend = _run(
            tmp_path,
            ["all", "--android-build", APK,
             "--target", f"platform=ios,backend=physical,model=iPhone 13,build={DEVICE}",
             "--target", "platform=web,browser=chrome,version=157,viewport=desktop",
             "--target", "Platform=Web, Browser=Chrome, Version=156"],
        )  # fmt: skip

        assert result.exit_code == 0, result.output
        assert backend.bodies[0]["targets"] == [
            {"platform": "android", "buildId": APK},
            {
                "platform": "ios",
                "buildId": DEVICE,
                "backend": "physical",
                "deviceModels": ["iPhone 13"],
            },
            {
                "platform": "web",
                "browser": "chrome",
                "browserVersionRequested": "157",
                "viewport": "pc",
            },
            {"platform": "web", "browser": "chrome", "browserVersionRequested": "156"},
        ]

    def test_targets_file_reads_the_same_keys(self, tmp_path):
        path = tmp_path / "targets.json"
        path.write_text(
            json.dumps(
                [
                    {"platform": "android", "device": "tablet", "os": 15},
                    {"platform": "android", "device": "tv"},
                ]
            )
        )

        result, backend = _run(
            tmp_path,
            ["all", "--android-build", APK, "--targets-file", str(path)],
        )

        assert result.exit_code == 0, result.output
        assert backend.bodies[0]["targets"] == [
            {"platform": "android", "buildId": APK, "deviceType": "tablet", "osVersion": "15"},
            {"platform": "android", "buildId": APK, "deviceType": "tv"},
        ]

    def test_legacy_flags_send_what_they_always_sent(self, tmp_path):
        result, backend = _run(tmp_path, ["all", "--ios-build", SIM, "--android-build", APK])

        assert result.exit_code == 0, result.output
        assert backend.bodies[0]["targets"] == [
            {"platform": "ios", "buildId": SIM},
            {"platform": "android", "buildId": APK},
        ]


class TestTargetsRefusedLocally:
    @pytest.mark.parametrize(
        "args,message",
        [
            (["--target", "platform=ios,model=iPhone 13"], "model needs backend=physical"),
            (["--target", "platform=ios,device=tv"], "device=tv needs platform=android"),
            (["--target", "platform=web,version=157"], "version needs browser="),
            (
                ["--target", "platform=web,browser=chrome,version=157,viewport=mobile"],
                "viewport=mobile",
            ),
            (["--target", "platform=ios,colour=red"], "unknown key 'colour'"),
            (["--target", "platform=android,os=15"], "needs a build"),
            (["--target", "platform=ios", "--target", "platform=ios"], "listed twice"),
            (
                ["--ios-device-type", "tablet", "--target", "platform=ios"],
                "cannot be combined with --target platform=ios",
            ),
            (
                [
                    "--target",
                    f"platform=ios,os=26,build={SIM}",
                    "--target",
                    f"platform=ios,os=27,build={DEVICE}",
                ],
                "install different builds",
            ),
        ],
    )
    def test_invalid_target_never_reaches_the_api(self, tmp_path, args, message):
        result, backend = _run(tmp_path, ["all", "--ios-build", SIM, *args])

        assert result.exit_code == 1
        assert message in " ".join(result.output.split())
        assert backend.bodies == []


class TestTargetsRefusedByTheServer:
    @pytest.mark.parametrize(
        "status,detail,expected",
        [
            (
                422,
                [{"loc": ["body", "targets"], "msg": "Value error, Duplicate target 'ios'/None"
                  "/None: each (platform, browser, viewport) may appear at most once per batch"}],
                "Several devices per platform are not enabled for this workspace.",
            ),
            (403, "Android TV testing is not enabled for this tenant", "Android TV is not enabled"),
            (
                422,
                [{"loc": ["body", "targets", 0], "msg": "Value error, browser_version_requested is "
                  "not available for this workspace yet"}],
                "Browser versions are not enabled for this workspace.",
            ),
            (409, "Build is no longer available in TestFlight", "The run was refused"),
        ],
    )  # fmt: skip
    def test_refusal_reads_as_a_sentence_not_a_traceback(self, tmp_path, status, detail, expected):
        refusal = httpx.Response(status, json={"detail": detail})
        result, _ = _run(
            tmp_path,
            [
                "all",
                "--ios-build",
                SIM,
                "--target",
                "platform=ios,os=26",
                "--target",
                "platform=ios,os=27",
            ],
            FakeBatches(refusal),
        )

        assert result.exit_code == 3
        assert expected in " ".join(result.output.split())
        assert "Traceback" not in result.output


class TestCommitTargets:
    def test_commit_builds_the_platforms_its_targets_name(self, tmp_path):
        result, backend = _run(
            tmp_path,
            ["from-commit", SHA, "--no-watch", "--target", "platform=ios,os=27",
             "--target", "platform=ios,backend=physical,model=iPhone 13",
             "--target", f"platform=android,build={APK}"],
        )  # fmt: skip

        assert result.exit_code == 0, result.output
        assert backend.bodies == [
            {
                "commitSha": SHA,
                "platforms": ["ios"],
                "targets": [
                    {"platform": "ios", "osVersion": "27"},
                    {"platform": "ios", "backend": "physical", "deviceModels": ["iPhone 13"]},
                    {"platform": "android", "buildId": APK},
                ],
            }
        ]

    def test_pinning_a_build_on_a_commit_built_platform_is_refused(self, tmp_path):
        result, backend = _run(
            tmp_path,
            ["from-commit", SHA, "--platform", "ios", "--target", f"platform=ios,build={SIM}"],
        )

        assert result.exit_code == 1
        assert "is built from the commit" in " ".join(result.output.split())
        assert backend.bodies == []
