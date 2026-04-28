from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MetricTarget = Literal["floating", "panel"]

DEFAULT_FLOATING_METRICS = ["key_remaining", "credits_remaining"]
DEFAULT_PANEL_METRICS = ["key_remaining", "credits_remaining"]
DEFAULT_METRIC_ORDER = [
    "key_remaining",
    "key_usage_daily",
    "key_usage_weekly",
    "key_usage_monthly",
    "credits_remaining",
]
DEFAULT_PANEL_ROTATION_INTERVAL_SECONDS = 4
MIN_PANEL_ROTATION_INTERVAL_SECONDS = 2
MAX_PANEL_ROTATION_INTERVAL_SECONDS = 60


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    id: str
    source: Literal["key-info", "credits"]
    value_key: str
    default_floating_label: str
    default_panel_label: str


@dataclass(frozen=True, slots=True)
class RenderedMetric:
    id: str
    label: str
    value: str
    refreshed_at: str


METRIC_DEFINITIONS: tuple[MetricDefinition, ...] = (
    MetricDefinition("key_remaining", "key-info", "limit_remaining", "剩余配额", "配额"),
    MetricDefinition("key_usage_daily", "key-info", "usage_daily", "今日使用", "今日"),
    MetricDefinition("key_usage_weekly", "key-info", "usage_weekly", "本周使用", "本周"),
    MetricDefinition("key_usage_monthly", "key-info", "usage_monthly", "本月使用", "本月"),
    MetricDefinition("credits_remaining", "credits", "remaining_credits", "账户余额", "余额"),
)
METRIC_DEFINITION_BY_ID = {definition.id: definition for definition in METRIC_DEFINITIONS}
METRIC_DEFINITION_IDS = tuple(definition.id for definition in METRIC_DEFINITIONS)


@dataclass(slots=True)
class FloatingMetricsState:
    key_value: str = "-"
    key_time: str = "-"
    credits_value: str = "-"
    credits_time: str = "-"
    key_summary: dict[str, object] | None = None
    credits_summary: dict[str, object] | None = None

    def update(self, mode: str, summary: dict[str, object], success_time: str) -> None:
        if mode == "key-info":
            self.key_summary = dict(summary)
            self.key_value = format_currency_value(summary.get("limit_remaining"))
            self.key_time = success_time
            return
        if mode == "credits":
            self.credits_summary = dict(summary)
            self.credits_value = format_currency_value(summary.get("remaining_credits"))
            self.credits_time = success_time

    def render(
        self,
        metric_ids: list[str],
        labels: dict[str, dict[str, str]],
        target: MetricTarget,
        fallback: list[str],
    ) -> list[RenderedMetric]:
        rendered: list[RenderedMetric] = []
        for metric_id in normalize_metric_ids(metric_ids, fallback):
            definition = METRIC_DEFINITION_BY_ID[metric_id]
            summary = self.key_summary if definition.source == "key-info" else self.credits_summary
            refreshed_at = self.key_time if definition.source == "key-info" else self.credits_time
            default_label = (
                definition.default_floating_label if target == "floating" else definition.default_panel_label
            )
            label = metric_label(labels, metric_id, target, default_label)
            value = format_currency_value(summary.get(definition.value_key) if summary is not None else None)
            rendered.append(RenderedMetric(metric_id, label, value, refreshed_at))
        return rendered


def format_currency_value(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"${value:.4f}"
    return "-"


def normalize_metric_ids(value: object, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        value = fallback
    seen: set[str] = set()
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or item not in METRIC_DEFINITION_BY_ID or item in seen:
            continue
        normalized.append(item)
        seen.add(item)
    return normalized or list(fallback)


def normalize_metric_labels(value: object) -> dict[str, dict[str, str]]:
    if not isinstance(value, dict):
        value = {}
    labels: dict[str, dict[str, str]] = {}
    for definition in METRIC_DEFINITIONS:
        raw_item = value.get(definition.id)
        item = raw_item if isinstance(raw_item, dict) else {}
        floating_label = item.get("floating")
        panel_label = item.get("panel")
        labels[definition.id] = {
            "floating": floating_label.strip() if isinstance(floating_label, str) and floating_label.strip() else definition.default_floating_label,
            "panel": panel_label.strip() if isinstance(panel_label, str) and panel_label.strip() else definition.default_panel_label,
        }
    return labels


def normalize_metric_order(value: object) -> list[str]:
    if not isinstance(value, list):
        value = DEFAULT_METRIC_ORDER
    ordered = normalize_metric_ids(value, DEFAULT_METRIC_ORDER)
    for metric_id in DEFAULT_METRIC_ORDER:
        if metric_id not in ordered:
            ordered.append(metric_id)
    return ordered


def order_metric_ids(metric_ids: list[str], metric_order: list[str], fallback: list[str]) -> list[str]:
    selected = set(normalize_metric_ids(metric_ids, fallback))
    ordered = [metric_id for metric_id in normalize_metric_order(metric_order) if metric_id in selected]
    for metric_id in metric_ids:
        if metric_id in selected and metric_id not in ordered:
            ordered.append(metric_id)
    return ordered


def metric_label(
    labels: dict[str, dict[str, str]],
    metric_id: str,
    target: MetricTarget,
    default: str,
) -> str:
    item = labels.get(metric_id)
    if not isinstance(item, dict):
        return default
    label = item.get(target)
    return label if isinstance(label, str) and label.strip() else default


def clamp_panel_rotation_interval(value: object) -> int:
    try:
        interval = int(value)
    except (TypeError, ValueError):
        return DEFAULT_PANEL_ROTATION_INTERVAL_SECONDS
    return min(MAX_PANEL_ROTATION_INTERVAL_SECONDS, max(MIN_PANEL_ROTATION_INTERVAL_SECONDS, interval))
