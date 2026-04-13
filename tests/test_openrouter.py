from __future__ import annotations

from open_router_key_viewer.services.openrouter import (
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
