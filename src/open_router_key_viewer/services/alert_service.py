from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime
from urllib.request import Request, urlopen

from open_router_key_viewer.state import AppConfig
from open_router_key_viewer.state.app_metadata import DISPLAY_DATETIME_FORMAT


@dataclass(frozen=True, slots=True)
class AlertEvent:
    """A threshold crossing that should be delivered through configured channels."""

    mode: str
    level: str
    target: str
    subject: str
    value: float
    webhook_url: str = ""
    webhook_body: dict[str, object] | None = None


class AlertService:
    """Evaluate threshold alerts and deliver webhook notifications."""

    def __init__(self) -> None:
        self._last_levels = {"key-info": "normal", "credits": "normal"}

    def evaluate(self, mode: str, summary: dict[str, object], config: AppConfig) -> AlertEvent | None:
        target_spec = self._target_spec(mode, summary, config)
        if target_spec is None:
            return None

        value, warning, critical, target, subject, webhook_target = target_spec
        if not isinstance(value, (int, float)):
            return None

        level = classify_threshold_level(float(value), critical, warning)
        if level == "normal":
            self._last_levels[mode] = "normal"
            return None

        if level == self._last_levels.get(mode, "normal"):
            return None

        self._last_levels[mode] = level
        webhook_url = self._webhook_url(mode, level, config)
        webhook_body = (
            {
                "event": f"{webhook_target}_threshold_triggered",
                "level": level,
                "target": webhook_target,
                "current_value": float(value),
                "timestamp": datetime.now().strftime(DISPLAY_DATETIME_FORMAT),
            }
            if webhook_url
            else None
        )
        return AlertEvent(
            mode=mode,
            level=level,
            target=target,
            subject=subject,
            value=float(value),
            webhook_url=webhook_url,
            webhook_body=webhook_body,
        )

    def send_webhook(self, event: AlertEvent) -> None:
        if not event.webhook_url or event.webhook_body is None:
            return
        threading.Thread(
            target=post_webhook,
            args=(event.webhook_url, event.webhook_body),
            daemon=True,
        ).start()

    def _target_spec(
        self,
        mode: str,
        summary: dict[str, object],
        config: AppConfig,
    ) -> tuple[object, object, object, str, str, str] | None:
        if mode == "key-info":
            target = "Key 配额"
            label = summary.get("label")
            subject = f"{target} · {label}" if isinstance(label, str) and label.strip() else target
            return (
                summary.get("limit_remaining"),
                config.key_info_warning_threshold,
                config.key_info_critical_threshold,
                target,
                subject,
                "key_info",
            )
        if mode == "credits":
            target = "账户余额"
            return (
                summary.get("remaining_credits"),
                config.credits_warning_threshold,
                config.credits_critical_threshold,
                target,
                target,
                "credits",
            )
        return None

    @staticmethod
    def _webhook_url(mode: str, level: str, config: AppConfig) -> str:
        if mode == "key-info":
            enabled = config.notify_webhook_key_info_enabled
            url = config.notify_webhook_key_info_url
            only_critical = config.notify_webhook_key_info_only_critical
        else:
            enabled = config.notify_webhook_credits_enabled
            url = config.notify_webhook_credits_url
            only_critical = config.notify_webhook_credits_only_critical

        if not enabled or not isinstance(url, str) or not url.strip():
            return ""
        if only_critical and level != "critical":
            return ""
        return url.strip()


def classify_threshold_level(value: float, critical: object, warning: object) -> str:
    critical_value = _to_float(critical)
    warning_value = _to_float(warning)
    if critical_value >= 0 and value <= critical_value:
        return "critical"
    if warning_value >= 0 and value <= warning_value:
        return "warning"
    return "normal"


def post_webhook(url: str, body: dict[str, object]) -> None:
    data = json.dumps(body).encode("utf-8")
    request = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=10):
            pass
    except Exception:
        pass


def _to_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return -1.0
