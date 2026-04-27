from __future__ import annotations

from open_router_key_viewer.state import QueryState, build_query_page_render_model, build_query_result_view_model


def test_key_info_view_model_formats_core_rows() -> None:
    view_model = build_query_result_view_model(
        "key-info",
        {
            "limit_remaining": 8.5,
            "usage": 1.5,
            "label": "main",
            "is_management_key": True,
            "expires_at": "2026-04-30T00:00:00Z",
            "rate_limit": {"requests": 60, "interval": "1m"},
        },
    )

    assert view_model.hero_title == "剩余配额"
    assert view_model.hero_value == "$8.5000"
    assert ("标签", "main", "OpenRouter 返回的 key 标签") in view_model.rows
    assert ("管理 Key", "是", "当前 key 是否具备 management 能力") in view_model.rows
    assert ("速率限制", "60", "1m") in view_model.rows


def test_credits_view_model_formats_remaining_credits() -> None:
    view_model = build_query_result_view_model(
        "credits",
        {
            "remaining_credits": 21.5,
            "total_credits": 25.0,
            "total_usage": 3.5,
        },
    )

    assert view_model.hero_title == "剩余余额"
    assert view_model.hero_value == "$21.5000"
    assert view_model.rows == [
        ("剩余余额", "$21.5000", "按 total_credits - total_usage 计算"),
        ("总余额", "$25.0000", "账户累计 credits"),
        ("已用余额", "$3.5000", "账户累计使用"),
    ]


def test_unknown_query_mode_returns_empty_view_model() -> None:
    view_model = build_query_result_view_model("unknown", {})

    assert view_model.hero_title == "结果"
    assert view_model.rows == [("状态", "无数据", "")]


def test_query_page_render_model_uses_query_state() -> None:
    state = QueryState("credits")
    state.succeed(
        {
            "summary": {"remaining_credits": 10.0},
            "http_meta": {"request": {"method": "GET"}, "response": {"status": 200}},
            "raw_response": {"data": {"remaining_credits": 10.0}},
        },
        "2026-04-27 10:00:00",
    )

    view_model = build_query_page_render_model("credits", state)

    assert view_model.status == "success"
    assert view_model.hero_value == "$10.0000"
    assert view_model.last_success_time == "2026-04-27 10:00:00"
    assert '"method": "GET"' in view_model.raw_http_text
