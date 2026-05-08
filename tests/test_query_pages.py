from __future__ import annotations

from open_router_key_viewer.state import QueryState
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
