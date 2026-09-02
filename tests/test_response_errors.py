"""Tests for minitest_cli.commands._response_errors — shared HTTP error handling."""

import json
from unittest.mock import MagicMock

import httpx
import pytest
from click.exceptions import Exit

from minitest_cli.commands._response_errors import (
    extract_detail,
    format_validation_field_errors,
    handle_response_error,
)

_STOCK_FASTAPI_BODY = {
    "detail": [
        {
            "loc": ["query", "status", 3],
            "msg": "Input should be 'pending', 'completed', 'failed' or 'cancelled'",
            "type": "enum",
        },
        {"loc": ["query", "page_size"], "msg": "Input should be less than or equal to 100"},
    ]
}

_MINITAP_OBSERVABILITY_BODY = {
    "error": "validation_error",
    "message": "Request validation failed",
    "details": {
        "errors": [
            {
                "field": "query.status.3",
                "message": "Input should be 'pending', 'completed', 'failed' or 'cancelled'",
                "type": "enum",
            },
        ]
    },
}


def _mock_response(status_code: int = 422, json_data: object = None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = json.dumps(json_data) if json_data is not None else ""
    return resp


class TestFormatValidationFieldErrors:
    def test_stock_fastapi_shape_renders_field_and_message(self) -> None:
        result = format_validation_field_errors(_STOCK_FASTAPI_BODY)
        assert result == (
            "status.3: Input should be 'pending', 'completed', 'failed' or 'cancelled'; "
            "page_size: Input should be less than or equal to 100"
        )

    def test_minitap_observability_shape_renders_field_and_message(self) -> None:
        result = format_validation_field_errors(_MINITAP_OBSERVABILITY_BODY)
        assert result == (
            "status.3: Input should be 'pending', 'completed', 'failed' or 'cancelled'"
        )

    def test_non_dict_body_returns_none(self) -> None:
        assert format_validation_field_errors(["not", "a", "dict"]) is None

    def test_plain_error_body_returns_none(self) -> None:
        assert format_validation_field_errors({"detail": "app not found"}) is None

    def test_empty_details_returns_none(self) -> None:
        assert format_validation_field_errors({"message": "oops", "details": {}}) is None


class TestExtractDetail:
    def test_stock_fastapi_validation_body_renders_field_errors(self) -> None:
        resp = _mock_response(422, _STOCK_FASTAPI_BODY)
        assert "status.3:" in extract_detail(resp)

    def test_minitap_observability_validation_body_renders_field_errors(self) -> None:
        resp = _mock_response(422, _MINITAP_OBSERVABILITY_BODY)
        assert extract_detail(resp) == (
            "status.3: Input should be 'pending', 'completed', 'failed' or 'cancelled'"
        )

    def test_plain_detail_string_passthrough(self) -> None:
        resp = _mock_response(404, {"detail": "app not found"})
        assert extract_detail(resp) == "app not found"

    def test_plain_message_fallback(self) -> None:
        resp = _mock_response(500, {"message": "something wrong"})
        assert extract_detail(resp) == "something wrong"

    def test_non_json_body_falls_back_to_text(self) -> None:
        resp = MagicMock(spec=httpx.Response)
        resp.json.side_effect = ValueError("not json")
        resp.text = "plain text error"
        assert extract_detail(resp) == "plain text error"


class TestHandleResponseError:
    def test_validation_error_message_includes_field_detail(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        resp = _mock_response(422, _MINITAP_OBSERVABILITY_BODY)

        with pytest.raises(Exit) as exc_info:
            handle_response_error(resp)

        assert exc_info.value.exit_code == 3
        err = " ".join(capsys.readouterr().err.split())
        assert "status.3" in err
        assert "Input should be 'pending', 'completed', 'failed' or 'cancelled'" in err
