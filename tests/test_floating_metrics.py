from __future__ import annotations

from open_router_key_viewer.state.floating_metrics import FloatingMetricsState


def test_floating_metrics_updates_each_query_target() -> None:
    metrics = FloatingMetricsState()

    metrics.update("key-info", {"limit_remaining": 8.5}, "2026-04-27 10:00:00")
    metrics.update("credits", {"remaining_credits": 21.25}, "2026-04-27 10:01:00")

    assert metrics.key_value == "$8.5000"
    assert metrics.key_time == "2026-04-27 10:00:00"
    assert metrics.credits_value == "$21.2500"
    assert metrics.credits_time == "2026-04-27 10:01:00"


def test_floating_metrics_renders_configured_metrics() -> None:
    metrics = FloatingMetricsState()
    metrics.update(
        "key-info",
        {"limit_remaining": 8.5, "usage_daily": 1.25},
        "2026-04-27 10:00:00",
    )

    rendered = metrics.render(
        ["key_usage_daily", "credits_remaining"],
        {"key_usage_daily": {"floating": "今天", "panel": "今"}},
        "floating",
        ["key_remaining", "credits_remaining"],
    )

    assert [(item.label, item.value, item.refreshed_at) for item in rendered] == [
        ("今天", "$1.2500", "2026-04-27 10:00:00"),
        ("账户余额", "-", "-"),
    ]
