from __future__ import annotations

from open_router_key_viewer.app import _safe_interval_seconds


def test_safe_interval_seconds_accepts_valid_int_values() -> None:
    assert _safe_interval_seconds("120") == 120
    assert _safe_interval_seconds(45) == 45


def test_safe_interval_seconds_clamps_or_falls_back_for_invalid_values() -> None:
    assert _safe_interval_seconds(0) == 1
    assert _safe_interval_seconds("-8") == 1
    assert _safe_interval_seconds("bad", default=300) == 300
    assert _safe_interval_seconds(None, default=60) == 60
