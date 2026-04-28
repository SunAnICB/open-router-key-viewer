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


def test_app_config_normalizes_metric_display_config() -> None:
    config = AppConfig.from_raw(
        {
            "floating_metrics": ["key_usage_daily", "missing", "key_usage_daily"],
            "panel_metrics": [],
            "floating_metric_order": ["credits_remaining", "unknown", "key_usage_daily"],
            "panel_metric_order": ["credits_remaining", "unknown", "key_remaining"],
            "metric_labels": {
                "key_usage_daily": {"floating": "今日", "panel": ""},
                "unknown": {"floating": "x"},
            },
            "panel_rotation_interval_seconds": 999,
        }
    )

    assert config.floating_metrics == ["key_usage_daily"]
    assert config.panel_metrics == ["credits_remaining", "key_remaining"]
    assert config.floating_metric_order[:2] == ["credits_remaining", "key_usage_daily"]
    assert config.panel_metric_order[:2] == ["credits_remaining", "key_remaining"]
    assert set(config.floating_metric_order) == {
        "key_remaining",
        "key_usage_daily",
        "key_usage_weekly",
        "key_usage_monthly",
        "credits_remaining",
    }
    assert config.metric_labels["key_usage_daily"]["floating"] == "今日"
    assert config.metric_labels["key_usage_daily"]["panel"] == "今日"
    assert config.panel_rotation_interval_seconds == 60
