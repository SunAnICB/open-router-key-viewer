from __future__ import annotations

from open_router_key_viewer.state import AppConfig


def test_app_config_accepts_valid_interval_values() -> None:
    config = AppConfig.from_raw({"poll_key_info_interval_seconds": "120", "poll_credits_interval_seconds": 45})

    assert config.poll_key_info_interval_seconds == 120
    assert config.poll_credits_interval_seconds == 45


def test_app_config_clamps_or_falls_back_for_invalid_interval_values() -> None:
    config = AppConfig.from_raw({"poll_key_info_interval_seconds": 0, "poll_credits_interval_seconds": "bad"})

    assert config.poll_key_info_interval_seconds == 1
    assert config.poll_credits_interval_seconds == 300
