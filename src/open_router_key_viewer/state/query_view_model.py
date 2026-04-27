from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

DISPLAY_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


@dataclass(slots=True)
class QueryResultViewModel:
    hero_title: str
    hero_value: str
    hero_note: str
    rows: list[tuple[str, str, str]]


def build_query_result_view_model(mode: str, payload: dict[str, object]) -> QueryResultViewModel:
    if mode == "key-info":
        return _build_key_info_view_model(payload)
    if mode == "credits":
        return _build_credits_view_model(payload)
    return QueryResultViewModel("结果", "-", "无数据", [("状态", "无数据", "")])


def _build_key_info_view_model(payload: dict[str, object]) -> QueryResultViewModel:
    rate_limit = payload.get("rate_limit")
    requests = "-"
    interval = ""
    if isinstance(rate_limit, dict):
        requests = _display_value(rate_limit.get("requests"))
        interval = _display_value(rate_limit.get("interval"))

    return QueryResultViewModel(
        "剩余配额",
        _format_currency_value(payload.get("limit_remaining")),
        "当前 key 还能继续使用的额度",
        [
            ("剩余配额", _format_currency_value(payload.get("limit_remaining")), "当前 key 还能使用的额度"),
            ("已用额度", _format_currency_value(payload.get("usage")), "当前 key 已累计使用"),
            ("总额度", _format_currency_value(payload.get("limit")), "当前 key 的限制上限"),
            ("今日使用", _format_currency_value(payload.get("usage_daily")), "当天累计使用"),
            ("本周使用", _format_currency_value(payload.get("usage_weekly")), "最近一周累计使用"),
            ("本月使用", _format_currency_value(payload.get("usage_monthly")), "最近一月累计使用"),
            ("标签", _display_value(payload.get("label")), "OpenRouter 返回的 key 标签"),
            ("重置周期", _display_value(payload.get("limit_reset")), "配额按该周期重置"),
            ("过期时间", _display_datetime(payload.get("expires_at")), "key 的过期时间"),
            ("免费层", _display_bool(payload.get("is_free_tier")), "是否属于 free tier"),
            ("管理 Key", _display_bool(payload.get("is_management_key")), "当前 key 是否具备 management 能力"),
            ("Provisioning Key", _display_bool(payload.get("is_provisioning_key")), "当前 key 是否具备 provisioning 能力"),
            ("速率限制", requests, interval),
        ],
    )


def _build_credits_view_model(payload: dict[str, object]) -> QueryResultViewModel:
    return QueryResultViewModel(
        "剩余余额",
        _format_currency_value(payload.get("remaining_credits")),
        "按 total_credits - total_usage 计算",
        [
            ("剩余余额", _format_currency_value(payload.get("remaining_credits")), "按 total_credits - total_usage 计算"),
            ("总余额", _format_currency_value(payload.get("total_credits")), "账户累计 credits"),
            ("已用余额", _format_currency_value(payload.get("total_usage")), "账户累计使用"),
        ],
    )


def _display_value(value: object) -> str:
    if value is None:
        return "-"
    return str(value)


def _format_currency_value(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"${value:.4f}"
    return "-"


def _display_bool(value: object) -> str:
    if value is True:
        return "是"
    if value is False:
        return "否"
    return "-"


def _display_datetime(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        return "-"

    normalized = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return value.strip()

    return dt.strftime(DISPLAY_DATETIME_FORMAT)
