"""Rendering of httpx transport failures.

A conductor agent once read ten successful ``run start`` calls as ten failures
because the CLI answered every one of them with a bare ``Network error:`` — the
read timeout stringifies to nothing — and launched ten real test batches while
believing none had been created. These tests pin the two properties that would
have stopped it: the message always says something, and a timeout on a write
says the request may already have landed.
"""

import httpx

from minitest_cli.api.errors import format_network_error


def _timeout(exc_class: type[httpx.TimeoutException], method: str) -> httpx.TimeoutException:
    request = httpx.Request(method, "https://testing-service.app.minitap.ai/api/v1/apps/a/batches")
    return exc_class("", request=request)


class TestFormatNetworkError:
    def test_read_timeout_on_write_names_the_failure_and_warns_it_may_have_landed(self) -> None:
        message = format_network_error(_timeout(httpx.ReadTimeout, "POST"))

        assert "ReadTimeout" in message
        assert "POST https://testing-service.app.minitap.ai/api/v1/apps/a/batches" in message
        assert "may well have been applied" in message

    def test_connect_timeout_does_not_claim_the_request_landed(self) -> None:
        """Nothing was sent, so retrying is safe and must not be discouraged."""
        message = format_network_error(_timeout(httpx.ConnectTimeout, "POST"))

        assert "ConnectTimeout" in message
        assert "may well have been applied" not in message

    def test_read_timeout_on_a_read_does_not_warn(self) -> None:
        message = format_network_error(_timeout(httpx.ReadTimeout, "GET"))

        assert "may well have been applied" not in message

    def test_error_without_a_request_still_reports_a_reason(self) -> None:
        message = format_network_error(httpx.ReadTimeout(""))

        assert message == "Network error: ReadTimeout"

    def test_action_is_woven_into_the_label(self) -> None:
        message = format_network_error(httpx.ConnectError("refused"), action="fetching skill")

        assert message == "Network error fetching skill: refused"
