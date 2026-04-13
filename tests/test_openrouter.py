from __future__ import annotations

import json
from urllib.error import HTTPError

import pytest

import open_router_key_viewer.services.openrouter as openrouter_module
from open_router_key_viewer.services.openrouter import (
    OpenRouterAPIError,
    OpenRouterClient,
    _extract_error_message,
    _mask_secret_header,
    _to_bool,
    _to_float,
    _to_int,
)


def test_extract_error_message_prefers_nested_error_message() -> None:
    raw = '{"error": {"message": "invalid key"}}'
    assert _extract_error_message(raw) == "invalid key"


def test_extract_error_message_falls_back_to_top_level_message_or_raw_text() -> None:
    assert _extract_error_message('{"message": "bad request"}') == "bad request"
    assert _extract_error_message("plain text error") == "plain text error"


def test_mask_secret_header_keeps_only_edges_for_long_key() -> None:
    assert _mask_secret_header("sk-or-v1-abcdefghijklmnopqrstuvwxyz") == "Bearer sk-or-...wxyz"
    assert _mask_secret_header("short") == "Bearer ******"


def test_numeric_and_boolean_coercion_helpers() -> None:
    assert _to_float("12.5") == 12.5
    assert _to_float("bad") is None
    assert _to_int("7") == 7
    assert _to_int(3.9) == 3
    assert _to_bool("true") is True
    assert _to_bool("0") is False
    assert _to_bool("unknown") is None


class _FakeResponse:
    def __init__(self, payload: dict, status: int = 200, headers: dict[str, str] | None = None) -> None:
        self._body = json.dumps(payload).encode("utf-8")
        self._status = status
        self.headers = headers or {"Content-Type": "application/json"}

    def read(self) -> bytes:
        return self._body

    def getcode(self) -> int:
        return self._status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_get_current_key_info_parses_summary_and_http_meta(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "data": {
            "label": "main",
            "usage": 1.5,
            "usage_daily": 0.5,
            "usage_weekly": 1.0,
            "usage_monthly": 1.5,
            "limit": 10,
            "limit_remaining": 8.5,
            "limit_reset": "monthly",
            "expires_at": "2026-04-30T00:00:00Z",
            "is_free_tier": False,
            "is_management_key": True,
            "is_provisioning_key": False,
            "rate_limit": {"requests": 60, "interval": "1m"},
        }
    }

    monkeypatch.setattr(openrouter_module, "urlopen", lambda request, timeout=0: _FakeResponse(payload))
    result = OpenRouterClient().get_current_key_info("sk-test-secret")

    assert result.summary["label"] == "main"
    assert result.summary["limit_remaining"] == 8.5
    assert result.summary["rate_limit"] == {"requests": 60, "interval": "1m"}
    assert result.http_meta["request"]["method"] == "GET"
    assert result.http_meta["request"]["headers"]["Authorization"] == "Bearer sk-tes...cret"


def test_get_credits_computes_remaining_credits(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"data": {"total_credits": 25, "total_usage": 3.5}}
    monkeypatch.setattr(openrouter_module, "urlopen", lambda request, timeout=0: _FakeResponse(payload))

    result = OpenRouterClient().get_credits("sk-test-secret")

    assert result.summary == {
        "total_credits": 25.0,
        "total_usage": 3.5,
        "remaining_credits": 21.5,
    }


def test_get_json_raises_api_error_with_http_status(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_http_error(request, timeout=0):
        raise HTTPError(
            url=request.full_url,
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=__import__("io").BytesIO(b'{"error":{"message":"bad token"}}'),
        )

    monkeypatch.setattr(openrouter_module, "urlopen", _raise_http_error)

    with pytest.raises(OpenRouterAPIError) as exc_info:
        OpenRouterClient().get_credits("bad-token")

    assert str(exc_info.value) == "bad token (status=401)"
