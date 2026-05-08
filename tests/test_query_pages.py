from __future__ import annotations

from open_router_key_viewer.state import QueryState
from open_router_key_viewer.state.query_view_model import QueryPageRenderModel
from open_router_key_viewer.ui.pages.query_pages import KeyInfoPage


class _FakeSecretCoordinator:
    def load_secret(self, _key: str) -> str:
        return ""


def test_query_feedback_is_suppressed_when_window_is_hidden(qapp) -> None:
    _ = qapp
    page = KeyInfoPage(_FakeSecretCoordinator(), QueryState("key-info"), lambda: None)

    page.hide()

    assert page._should_show_query_feedback() is False


def test_query_feedback_is_available_when_window_is_visible(qapp) -> None:
    app = qapp
    page = KeyInfoPage(_FakeSecretCoordinator(), QueryState("key-info"), lambda: None)

    page.show()
    app.processEvents()

    assert page._should_show_query_feedback() is True

    page.hide()


def test_query_render_is_deferred_when_window_is_hidden(qapp) -> None:
    _ = qapp
    page = KeyInfoPage(_FakeSecretCoordinator(), QueryState("key-info"), lambda: None)
    calls: list[tuple[QueryPageRenderModel, str | None]] = []

    page._apply_query_render_model = lambda view_model, *, raw_http_text=None: calls.append((view_model, raw_http_text))

    page.set_background_render_deferred(True)
    page.hide()
    page._render_query_state(raw_http_text="hidden raw")

    assert calls == []
    assert page.has_pending_render() is True


def test_pending_query_render_flushes_latest_state_when_visible(qapp) -> None:
    app = qapp
    state = QueryState("key-info")
    page = KeyInfoPage(_FakeSecretCoordinator(), state, lambda: None)
    calls: list[tuple[QueryPageRenderModel, str | None]] = []

    page._apply_query_render_model = lambda view_model, *, raw_http_text=None: calls.append((view_model, raw_http_text))

    page.set_background_render_deferred(True)
    page.hide()
    page._handle_query_started()
    state.succeed({"summary": {"limit_remaining": 12.5}}, "2026-05-08 12:00:00")

    page.set_background_render_deferred(False)
    page.show()
    app.processEvents()
    page.flush_pending_render()

    assert len(calls) == 1
    assert calls[0][0].status == "success"
    assert calls[0][0].hero_value == "$12.5000"
    assert calls[0][1] is None
    assert page.has_pending_render() is False

    page.hide()


def test_query_render_applies_immediately_when_visible(qapp) -> None:
    app = qapp
    page = KeyInfoPage(_FakeSecretCoordinator(), QueryState("key-info"), lambda: None)
    calls: list[tuple[QueryPageRenderModel, str | None]] = []

    page._apply_query_render_model = lambda view_model, *, raw_http_text=None: calls.append((view_model, raw_http_text))

    page.show()
    app.processEvents()
    page._render_query_state()

    assert len(calls) == 1
    assert page.has_pending_render() is False

    page.hide()


def test_hidden_query_render_applies_before_background_defer_is_enabled(qapp) -> None:
    _ = qapp
    page = KeyInfoPage(_FakeSecretCoordinator(), QueryState("key-info"), lambda: None)
    calls: list[tuple[QueryPageRenderModel, str | None]] = []

    page._apply_query_render_model = lambda view_model, *, raw_http_text=None: calls.append((view_model, raw_http_text))

    page.hide()
    page._render_query_state(raw_http_text="startup raw")

    assert len(calls) == 1
    assert calls[0][1] == "startup raw"
    assert page.has_pending_render() is False
