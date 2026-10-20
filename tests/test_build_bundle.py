"""``build upload <file>.aab``: wait for every build of the bundle group and show them all."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import typer
from click.exceptions import Exit
from typer.testing import CliRunner

from minitest_cli.commands._response_errors import handle_response_error
from minitest_cli.commands.build import app as build_app
from minitest_cli.commands.run import app as run_app
from minitest_cli.core.config import Settings

HEAD = {
    "id": "head-1",
    "appId": "app-123",
    "platform": "android",
    "originalName": "app.aab",
    "createdAt": "2026-10-20T10:00:00Z",
}
STORY_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
ABI_DETAIL = (
    "This Android build only contains x86_64 native libraries and cannot run on physical"
    " devices (needs arm64-v8a or armeabi-v7a). Upload the .aab, which converts for both"
    " cloud and physical devices, or a build for physical devices."
)


def _variant(build_id: str, status: str, *, phone: bool, error: str | None = None) -> dict:
    return {
        "id": build_id,
        "status": status,
        "abis": ["arm64-v8a"] if phone else ["x86_64"],
        "deviceBuild": phone,
        "supportedBackends": (["physical"] if phone else ["cloud"])
        if status == "completed"
        else [],
        "errorSummary": error,
    }


def _head(head: str, phone: str, *, phone_error: str | None = None, **extra) -> dict:
    variants = [_variant("head-1", head, phone=False), _variant("phone-1", phone, phone=True)]
    variants[1]["errorSummary"] = phone_error
    backends = [b for v in variants for b in v["supportedBackends"]]
    return {
        **HEAD,
        "status": head,
        "abis": ["x86_64"],
        "bundleGroupId": "group-1",
        "supportedBackends": backends,
        "variants": variants,
        **extra,
    }


def _resp(status_code: int, body: object) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = body
    resp.text = json.dumps(body)
    return resp


def _client(uploaded: dict, *polled: dict) -> AsyncMock:
    client = AsyncMock()
    client.upload_file = AsyncMock(return_value=_resp(201, uploaded))
    client.get = AsyncMock(side_effect=[_resp(200, body) for body in polled])
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def _upload(tmp_path: Path, client: AsyncMock, *flags: str, json_mode: bool = True):
    bundle = tmp_path / "app.aab"
    bundle.write_bytes(b"PK bundle")
    settings = Settings(config_dir=tmp_path, token="t", app_id="app-123")
    with (
        patch.object(typer.Context, "settings", settings, create=True),
        patch.object(typer.Context, "json_mode", json_mode, create=True),
        patch.object(typer.Context, "app_flag", None, create=True),
        patch("minitest_cli.commands.build.ApiClient", return_value=client),
        patch("minitest_cli.commands.build_conversion.CONVERSION_POLL_SECONDS", 0),
    ):
        return CliRunner().invoke(build_app, ["upload", str(bundle), *flags])


def _flat(text: str) -> str:
    return " ".join(text.split())


class TestBundleWait:
    def test_upload_waits_for_the_pending_phone_build(self, tmp_path: Path) -> None:
        client = _client(
            {**HEAD, "status": "pending"},
            _head("completed", "pending"),
            _head("completed", "completed"),
        )

        result = _upload(tmp_path, client)

        assert result.exit_code == 0, result.output
        assert client.get.call_count == 2
        body = json.loads(result.stdout)
        assert body["id"] == "head-1"
        assert body["bundleGroupId"] == "group-1"
        assert body["supportedBackends"] == ["cloud", "physical"]
        assert [v["status"] for v in body["variants"]] == ["completed", "completed"]
        assert body["variants"][1]["deviceBuild"] is True

    def test_upload_succeeds_when_one_build_failed_and_one_completed(self, tmp_path) -> None:
        client = _client(
            {**HEAD, "status": "pending"},
            _head("completed", "failed", phone_error="bundletool failed for arm64"),
        )

        result = _upload(tmp_path, client)

        assert result.exit_code == 0, result.output
        assert "Phone build phone-1 could not be converted" in _flat(result.stderr)
        assert "bundletool failed for arm64" in _flat(result.stderr)
        assert json.loads(result.stdout)["supportedBackends"] == ["cloud"]

    def test_upload_human_output_with_a_failed_phone_build(self, tmp_path: Path) -> None:
        client = _client(
            {**HEAD, "status": "pending"},
            _head("completed", "failed", phone_error="bundletool failed for arm64"),
        )

        result = _upload(tmp_path, client, json_mode=False)

        assert result.exit_code == 0, result.output
        assert "Runs on: cloud emulators" in result.stdout
        assert "physical phones" not in result.stdout
        assert "bundletool failed for arm64" in result.stdout

    def test_upload_fails_when_every_build_failed(self, tmp_path: Path) -> None:
        failed = _head("failed", "failed", phone_error="arm64 broke", errorSummary="x86 broke")
        failed["variants"][0]["errorSummary"] = "x86 broke"

        result = _upload(tmp_path, _client({**HEAD, "status": "pending"}, failed))

        assert result.exit_code == 5
        stderr = _flat(result.stderr)
        assert "The .aab could not be converted: x86 broke" in stderr
        assert "Phone build phone-1: arm64 broke" in stderr

    def test_upload_times_out_naming_the_pending_build(self, tmp_path: Path) -> None:
        client = _client({**HEAD, "status": "pending"}, _head("completed", "pending"))

        clock = MagicMock()
        clock.monotonic.side_effect = [0.0, 0.0, 10.0**9]
        with patch("minitest_cli.commands.build_conversion.time", clock):
            result = _upload(tmp_path, client)

        assert result.exit_code == 1
        assert "Still being converted: phone-1" in _flat(result.stderr)

    def test_upload_old_backend_without_bundle_fields(self, tmp_path: Path) -> None:
        client = _client({**HEAD, "status": "pending"}, {**HEAD, "status": "completed"})

        result = _upload(tmp_path, client, json_mode=False)

        assert result.exit_code == 0, result.output
        assert "status: completed" in result.stdout
        assert "Runs on" not in result.stdout
        assert "converted into" not in result.stdout


class TestBundleOutput:
    def test_upload_human_output_lists_both_builds(self, tmp_path: Path) -> None:
        client = _client(
            {**HEAD, "status": "pending"},
            _head("completed", "completed"),
        )

        result = _upload(tmp_path, client, json_mode=False)

        assert result.exit_code == 0, result.output
        out = result.stdout
        assert "This .aab converted into 2 builds" in out
        assert "Emulator" in out and "Phone" in out
        assert "arm64-v8a" in out and "x86_64" in out
        assert "abis: x86_64" in out
        assert "Runs on: cloud emulators and physical phones" in out
        assert "--android-build head-1" in _flat(out)

    def test_upload_physical_on_aab_prints_a_note_and_keeps_the_field(self, tmp_path) -> None:
        client = _client({**HEAD, "status": "pending"}, _head("completed", "completed"))

        result = _upload(tmp_path, client, "--physical", json_mode=False)

        assert result.exit_code == 0, result.output
        assert "--physical is not needed for .aab uploads" in _flat(result.stderr)
        assert client.upload_file.call_args.kwargs["data"] == {
            "platform": "android",
            "backend": "physical",
        }
        assert "physical devices)" not in result.stderr


class TestAndroidAbiMismatchHint:
    def test_handle_response_error_hints_at_the_aab(self) -> None:
        with pytest.raises(Exit) as exc:
            handle_response_error(_resp(422, {"detail": ABI_DETAIL}), resource="Batch")

        assert exc.value.exit_code == 5

    def test_run_start_physical_with_x86_build_explains_the_fix(self, monkeypatch, tmp_path):
        settings = Settings(api_url="https://t.example", token="t", app_id="app-123")
        settings.config_dir = tmp_path
        monkeypatch.setattr(typer.Context, "settings", settings, raising=False)
        monkeypatch.setattr(typer.Context, "json_mode", False, raising=False)
        monkeypatch.setattr(typer.Context, "app_flag", None, raising=False)
        transport = httpx.MockTransport(lambda r: httpx.Response(422, json={"detail": ABI_DETAIL}))
        real_client = httpx.AsyncClient
        monkeypatch.setattr(
            httpx, "AsyncClient", lambda **kw: real_client(**kw, transport=transport)
        )

        result = CliRunner().invoke(
            run_app,
            ["start", STORY_ID, "--no-watch", "--android-build", "b", "--android-physical"],
        )

        assert result.exit_code == 5
        stderr = _flat(result.stderr)
        assert "cannot run on physical devices" in stderr
        assert "upload the .aab instead" in stderr
        assert "arm64-v8a build for physical devices" in stderr

    def test_other_422_is_not_mistaken_for_an_abi_mismatch(self) -> None:
        with pytest.raises(Exit) as exc:
            handle_response_error(_resp(422, {"detail": "Scenario is archived"}))

        assert exc.value.exit_code == 3
