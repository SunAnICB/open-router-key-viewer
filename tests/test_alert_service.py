from __future__ import annotations

from open_router_key_viewer.services.alert_service import AlertService, classify_threshold_level
from open_router_key_viewer.state import AppConfig


def test_classify_threshold_level() -> None:
    assert classify_threshold_level(0.5, critical=1.0, warning=5.0) == "critical"
    assert classify_threshold_level(3.0, critical=1.0, warning=5.0) == "warning"
    assert classify_threshold_level(6.0, critical=1.0, warning=5.0) == "normal"
    assert classify_threshold_level(3.0, critical="bad", warning="bad") == "normal"


def test_alert_service_deduplicates_until_recovery() -> None:
    service = AlertService()
    config = AppConfig(key_info_warning_threshold=5.0, key_info_critical_threshold=1.0)

    first = service.evaluate("key-info", {"limit_remaining": 3.0, "label": "primary"}, config)
    assert first is not None
    assert first.level == "warning"
    assert first.subject == "Key 配额 · primary"

    assert service.evaluate("key-info", {"limit_remaining": 2.0}, config) is None
    assert service.evaluate("key-info", {"limit_remaining": 8.0}, config) is None

    second = service.evaluate("key-info", {"limit_remaining": 0.5}, config)
    assert second is not None
    assert second.level == "critical"


def test_alert_service_builds_webhook_for_enabled_target() -> None:
    service = AlertService()
    config = AppConfig(
        credits_warning_threshold=10.0,
        credits_critical_threshold=2.0,
        notify_webhook_credits_enabled=True,
        notify_webhook_credits_only_critical=False,
        notify_webhook_credits_url="https://example.com/hook",
    )

    event = service.evaluate("credits", {"remaining_credits": 8.0}, config)

    assert event is not None
    assert event.webhook_url == "https://example.com/hook"
    assert event.webhook_body is not None
    assert event.webhook_body["event"] == "credits_threshold_triggered"
    assert event.webhook_body["current_value"] == 8.0
