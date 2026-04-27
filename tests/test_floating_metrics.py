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
