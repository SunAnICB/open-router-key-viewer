from __future__ import annotations

import io
from collections.abc import Callable
from contextlib import redirect_stdout

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFrame, QVBoxLayout, QWidget

with redirect_stdout(io.StringIO()):
    from qfluentwidgets import (
        FluentIcon,
        InfoBar,
        InfoBarPosition,
        SingleDirectionScrollArea,
        SmoothMode,
        TitleLabel,
    )

from open_router_key_viewer.core.query_coordinator import QueryCoordinator
from open_router_key_viewer.core.secret_coordinator import SecretCoordinator
from open_router_key_viewer.i18n import tr
from open_router_key_viewer.state import (
    QueryPageRenderModel,
    QueryState,
    build_initial_raw_http_text,
    build_loading_raw_http_text,
    build_query_page_render_model,
)
from open_router_key_viewer.ui.pages.query_widgets import QueryResultCard, SecretInputCard
from open_router_key_viewer.ui.runtime import (
    show_error_bar,
)

_tr = tr


class BaseQueryPage(QWidget):
    page_title = ""
    input_label = ""
    input_placeholder = ""
    button_text = ""
    button_icon = FluentIcon.INFO
    mode = ""
    missing_secret_message = "请输入 key"
    config_key = ""
    save_button_text = "保存到本地缓存"

    def __init__(
        self,
        secret_coordinator: SecretCoordinator,
        query_state: QueryState,
        on_cache_changed: Callable[[], None],
        on_query_success: Callable[[str, dict[str, object]], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.secret_coordinator = secret_coordinator
        self.query_state = query_state
        self.on_cache_changed = on_cache_changed
        self.on_query_success = on_query_success
        self._result_mode = "summary"
        self._raw_http_text = ""
        self._rendered_raw_http_text = ""
        self.query_coordinator = QueryCoordinator(
            self.mode,
            self.query_state,
            self,
            on_started=self._handle_query_started,
            on_state_changed=self._render_query_state,
            on_failed=self._handle_failure,
            on_succeeded=self._handle_success,
            on_finished=self._handle_finished,
        )
        self._build_ui()
        self.load_cached_secret()

    def _build_ui(self) -> None:
        existing_layout = self.layout()
        if isinstance(existing_layout, QVBoxLayout):
            outer = existing_layout
        else:
            outer = QVBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)

        self.scroll_area = SingleDirectionScrollArea(self, Qt.Vertical)
        self.scroll_area.setSmoothMode(SmoothMode.NO_SMOOTH)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(self.scroll_area)

        content = QWidget(self.scroll_area)
        self.scroll_area.setWidget(content)
        self.scroll_area.enableTransparentBackground()
        content.setStyleSheet("background: transparent;")

        root = QVBoxLayout(content)
        root.setContentsMargins(36, 28, 36, 36)
        root.setSpacing(18)

        self.title_label = TitleLabel(_tr(self.page_title), self)
        root.addWidget(self.title_label)

        self.input_card = SecretInputCard(_tr(self.input_label), _tr(self.input_placeholder), self)
        self.secret_input = self.input_card.secret_input
        self.input_label_widget = self.input_card.input_label_widget
        self.paste_button = self.input_card.paste_button
        self.copy_button = self.input_card.copy_button
        self.save_button = self.input_card.save_button
        self.clear_saved_button = self.input_card.clear_saved_button
        self.paste_button.clicked.connect(self._paste_secret)
        self.copy_button.clicked.connect(self._copy_secret)
        self.save_button.clicked.connect(self._save_secret)
        self.clear_saved_button.clicked.connect(self._clear_saved_secret)
        root.addWidget(self.input_card)

        self.result_card = QueryResultCard(
            _tr(self.button_text),
            self.button_icon,
            lambda: self._show_result_mode("summary"),
            lambda: self._show_result_mode("raw"),
            self,
        )
        self.query_button = self.result_card.query_button
        self.status_badge = self.result_card.status_badge
        self.time_label = self.result_card.time_label
        self.result_mode_switch = self.result_card.result_mode_switch
        self.summary_container = self.result_card.summary_container
        self.hero_card = self.result_card.hero_card
        self.detail_card = self.result_card.detail_card
        self.result_output = self.result_card.result_output
        self.query_button.clicked.connect(self._query)
        root.addWidget(self.result_card)
        root.addStretch(1)
        self._show_result_mode("summary")
        self._render_query_state(raw_http_text=build_initial_raw_http_text(_tr("在上方输入 key 后开始查询")))

    def _set_busy(self, busy: bool, message: str) -> None:
        _ = message
        self.input_card.set_busy(busy)
        self.result_card.set_busy(busy)

    def _query(self) -> None:
        secret = self.secret_input.text().strip()
        if not secret:
            self._show_error(_tr(self.missing_secret_message))
            return
        self._run_query(self.mode, secret)

    def _save_secret(self) -> None:
        secret = self.secret_input.text().strip()
        if not secret:
            self._show_error(_tr(self.missing_secret_message))
            return

        result = self.secret_coordinator.save_secret(self.config_key, secret)
        if not result.ok:
            self._show_error(result.message)
            return
        self.on_cache_changed()
        InfoBar.success(
            title=_tr("已保存"),
            content=_tr("已写入本地缓存"),
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2000,
            parent=self.window(),
        )

    def _paste_secret(self) -> None:
        text = QApplication.clipboard().text().strip()
        if not text:
            self._show_error(_tr("剪贴板里没有可用内容"))
            return

        self.secret_input.setText(text)
        InfoBar.success(
            title=_tr("已粘贴"),
            content=_tr("已从剪贴板填入当前 key"),
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=1500,
            parent=self.window(),
        )

    def _copy_secret(self) -> None:
        secret = self.secret_input.text().strip()
        if not secret:
            self._show_error(_tr(self.missing_secret_message))
            return

        QApplication.clipboard().setText(secret)
        InfoBar.success(
            title=_tr("已复制"),
            content=_tr("当前 key 已复制到剪贴板"),
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=1500,
            parent=self.window(),
        )

    def _clear_saved_secret(self) -> None:
        result = self.secret_coordinator.delete_secret(self.config_key)
        if not result.ok:
            self._show_error(result.message)
            return
        self.secret_input.clear()
        self.on_cache_changed()
        InfoBar.success(
            title=_tr("已清除"),
            content=_tr("对应缓存已删除"),
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2000,
            parent=self.window(),
        )

    def _run_query(self, mode: str, secret: str) -> None:
        _ = mode
        if self.query_coordinator.is_running():
            self._show_error(_tr("已有请求正在执行，请稍候"))
            return
        self.query_coordinator.run(secret)

    def _handle_query_started(self) -> None:
        self._set_busy(True, _tr("查询中..."))
        self._render_query_state(raw_http_text=build_loading_raw_http_text())

    def _handle_success(self, summary: dict[str, object]) -> None:
        if self.on_query_success:
            self.on_query_success(self.mode, summary)
        InfoBar.success(
            title=_tr("请求成功"),
            content=_tr("OpenRouter 返回了查询结果"),
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2000,
            parent=self.window(),
        )

    def _handle_failure(self, message: str) -> None:
        self._show_error(message)

    def _handle_finished(self) -> None:
        self._set_busy(False, self.status_badge.title_label.text())

    def _show_error(self, message: str) -> None:
        show_error_bar(self.window(), _tr("请求失败"), message)

    def _show_result_mode(self, mode: str) -> None:
        self._result_mode = mode
        self.result_card.show_mode(mode)
        if mode == "raw":
            self._sync_raw_http_text()

    def _render_query_state(self, raw_http_text: str | None = None) -> None:
        view_model = build_query_page_render_model(self.mode, self.query_state)
        self._apply_query_render_model(view_model, raw_http_text=raw_http_text)

    def _apply_query_render_model(self, view_model: QueryPageRenderModel, *, raw_http_text: str | None = None) -> None:
        self.status_badge.set_status(view_model.status, _tr(view_model.status_message))
        self.hero_card.set_content(_tr(view_model.hero_title), _tr(view_model.hero_value), _tr(view_model.hero_note))
        self.detail_card.set_rows([(_tr(label), _tr(value), _tr(note)) for label, value, note in view_model.rows])
        self._raw_http_text = raw_http_text or view_model.raw_http_text
        if self._result_mode == "raw":
            self._sync_raw_http_text()
        self.time_label.setText(
            _tr("最近成功: -")
            if view_model.last_success_time == "-"
            else f"{_tr('最近成功:')} {view_model.last_success_time}"
        )

    def _sync_raw_http_text(self) -> None:
        if self._rendered_raw_http_text == self._raw_http_text:
            return
        self.result_output.setPlainText(self._raw_http_text)
        self._rendered_raw_http_text = self._raw_http_text

    def retranslate_ui(self) -> None:
        self.title_label.setText(_tr(self.page_title))
        self.input_card.retranslate_ui(_tr(self.input_label), _tr(self.input_placeholder))
        self.result_card.retranslate_ui(_tr(self.button_text))
        self._render_query_state(
            raw_http_text=(
                build_initial_raw_http_text(_tr("在上方输入 key 后开始查询"))
                if self.query_state.status == "idle"
                else None
            )
        )

    def load_cached_secret(self) -> None:
        cached = self.secret_coordinator.load_secret(self.config_key)
        if not cached:
            self.secret_input.clear()
            return
        self.secret_input.setText(cached)

    def auto_query_if_possible(self) -> None:
        secret = self.secret_input.text().strip()
        if not secret:
            return
        if self.query_coordinator.is_running():
            return
        self._run_query(self.mode, secret)

    def run_query_if_possible(self) -> None:
        self.auto_query_if_possible()

    def stop_worker(self) -> None:
        self.query_coordinator.stop()


class KeyInfoPage(BaseQueryPage):
    page_title = "Key 配额"
    input_label = "OpenRouter API Key"
    input_placeholder = "输入 API Key"
    button_text = "查询配额"
    button_icon = FluentIcon.SEARCH
    mode = "key-info"
    missing_secret_message = "请输入 OpenRouter API Key"
    config_key = "api_key"

    def __init__(
        self,
        secret_coordinator: SecretCoordinator,
        query_state: QueryState,
        on_cache_changed: Callable[[], None],
        on_query_success: Callable[[str, dict[str, object]], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(secret_coordinator, query_state, on_cache_changed, on_query_success, parent)
        self.setObjectName("key-info-page")


class CreditsPage(BaseQueryPage):
    page_title = "账户余额"
    input_label = "OpenRouter Management Key"
    input_placeholder = "输入 Management Key"
    button_text = "查询余额"
    button_icon = FluentIcon.SEARCH
    mode = "credits"
    missing_secret_message = "请输入 OpenRouter Management Key"
    config_key = "management_key"

    def __init__(
        self,
        secret_coordinator: SecretCoordinator,
        query_state: QueryState,
        on_cache_changed: Callable[[], None],
        on_query_success: Callable[[str, dict[str, object]], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(secret_coordinator, query_state, on_cache_changed, on_query_success, parent)
        self.setObjectName("credits-page")
