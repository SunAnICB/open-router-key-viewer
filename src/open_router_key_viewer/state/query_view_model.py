from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from open_router_key_viewer.state.app_metadata import DISPLAY_DATETIME_FORMAT


@dataclass(slots=True)
class QueryResultViewModel:
    hero_title: str
    hero_value: str
    hero_note: str
    rows: list[tuple[str, str, str]]


@dataclass(frozen=True, slots=True)
class QueryPageRenderModel:
    status: str
    status_message: str
    hero_title: str
    hero_value: str
    hero_note: str
    rows: list[tuple[str, str, str]]
    raw_http_text: str
    last_success_time: str


def build_query_result_view_model(mode: str, payload: dict[str, object]) -> QueryResultViewModel:
    if mode == "key-info":
        return _build_key_info_view_model(payload)
    if mode == "credits":
        return _build_credits_view_model(payload)
    return QueryResultViewModel("结果", "-", "无数据", [("状态", "无数据", "")])


def build_query_page_render_model(mode: str, state) -> QueryPageRenderModel:
    if state.status == "success":
        result = build_query_result_view_model(mode, state.summary)
        status = "success"
        status_message = "查询成功"
    elif state.status == "loading":
        result = _placeholder_result("查询中...")
        status = "loading"
        status_message = "查询中"
    elif state.status == "error":
        result = _placeholder_result("查询失败")
        status = "error"
        status_message = "查询失败"
    else:
        result = _placeholder_result("等待查询")
        status = "idle"
        status_message = "等待查询"

    return QueryPageRenderModel(
        status=status,
        status_message=status_message,
        hero_title=result.hero_title,
        hero_value=result.hero_value,
        hero_note=result.hero_note,
        rows=result.rows,
        raw_http_text=_json_text(state.raw_http_payload()),
        last_success_time=state.last_success_time,
    )


def build_initial_raw_http_text(message: str) -> str:
    return _json_text({"message": message})


def build_loading_raw_http_text() -> str:
    return _json_text({"loading": True})


def normalize_query_error(error: object, default_message: str) -> tuple[str, object, object]:
    if isinstance(error, dict):
        return str(error.get("message") or default_message), error.get("http_meta"), error.get("raw_response")
    message = str(error)
    return message, {}, {"error": message}


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


def _placeholder_result(message: str) -> QueryResultViewModel:
    return QueryResultViewModel(
        "状态",
        message,
        "查询成功后会在这里显示关键结果",
        [("说明", "暂无结果", "先输入 key，再执行查询")],
    )


def _json_text(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
