from __future__ import annotations

import io
import json
from collections.abc import Callable
from contextlib import redirect_stdout
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFrame, QVBoxLayout, QWidget

with redirect_stdout(io.StringIO()):
    from qfluentwidgets import (
        FluentIcon,
        InfoBar,
        InfoBarPosition,
        SingleDirectionScrollArea,
        TitleLabel,
    )

from open_router_key_viewer.i18n import tr
from open_router_key_viewer.services.config_store import ConfigStore
from open_router_key_viewer.ui.controllers.query_controller import QueryExecutionController
from open_router_key_viewer.ui.pages.query_widgets import QueryResultCard, SecretInputCard
from open_router_key_viewer.ui.runtime import (
    DISPLAY_DATETIME_FORMAT,
    format_currency_value,
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
        config_store: ConfigStore,
        on_cache_changed: Callable[[], None],
        on_query_success: Callable[[str, dict[str, object]], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.config_store = config_store
        self.on_cache_changed = on_cache_changed
        self.on_query_success = on_query_success
        self._summary_payload: dict[str, object] = {}
        self._http_meta: dict[str, object] = {}
        self._raw_payload: dict[str, object] = {}
        self._last_success_time = "-"
        self._status_message = _tr("等待查询")
        self.query_controller = QueryExecutionController(
            self.mode,
            self,
            on_started=self._handle_query_started,
            on_succeeded=self._handle_success,
            on_failed=self._handle_failure,
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
        self.result_output.setPlainText(
            json.dumps({"message": _tr("在上方输入 key 后开始查询")}, ensure_ascii=False, indent=2)
        )
        root.addWidget(self.result_card, 1)
        self._show_result_mode("summary")
        self._render_summary_placeholder()

    def _set_busy(self, busy: bool, message: str) -> None:
        self._status_message = message
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

        self.config_store.save_value(self.config_key, secret)
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
        self.config_store.delete_value(self.config_key)
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
        if self.query_controller.is_running():
            self._show_error(_tr("已有请求正在执行，请稍候"))
            return
        self.query_controller.run(secret)

    def _handle_query_started(self) -> None:
        self._set_busy(True, _tr("查询中..."))
        self.status_badge.set_status("loading", _tr("查询中"))
        self._summary_payload = {}
        self._http_meta = {}
        self._raw_payload = {}
        self._render_summary_placeholder(_tr("查询中..."))
        self.result_output.setPlainText("{\n  \"loading\": true\n}")

    def _handle_success(self, payload: dict) -> None:
        self._last_success_time = datetime.now().strftime(DISPLAY_DATETIME_FORMAT)
        self._update_time_label()
        self.status_badge.set_status("success", _tr("查询成功"))
        self._summary_payload = payload.get("summary", {})
        self._http_meta = payload.get("http_meta", {})
        self._raw_payload = payload.get("raw_response", {})
        self._render_summary()
        if self.on_query_success:
            self.on_query_success(self.mode, payload)
        self.result_output.setPlainText(
            json.dumps(
                {
                    "request": self._http_meta.get("request", {}),
                    "response": {
                        **self._http_meta.get("response", {}),
                        "body": self._raw_payload,
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
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
        self._update_time_label()
        self.status_badge.set_status("error", _tr("查询失败"))
        self._summary_payload = {}
        self._http_meta = {}
        self._raw_payload = {"error": message}
        self._render_summary_placeholder(_tr("查询失败"))
        self.result_output.setPlainText(json.dumps({"error": message}, ensure_ascii=False, indent=2))
        self._show_error(message)

    def _handle_finished(self) -> None:
        self._set_busy(False, self.status_badge.title_label.text())

    def _show_error(self, message: str) -> None:
        show_error_bar(self.window(), _tr("请求失败"), message)

    def _show_result_mode(self, mode: str) -> None:
        self.result_card.show_mode(mode)

    def _render_summary_placeholder(self, message: str = "等待查询") -> None:
        self.hero_card.set_content(_tr("状态"), message, _tr("查询成功后会在这里显示关键结果"))
        self.detail_card.set_rows([(_tr("说明"), _tr("暂无结果"), _tr("先输入 key，再执行查询"))])

    def _render_summary(self) -> None:
        hero_title, hero_value, hero_note, rows = self.build_result_model(self._summary_payload)
        self.hero_card.set_content(hero_title, hero_value, hero_note)
        self.detail_card.set_rows(rows)

    def _update_time_label(self) -> None:
        if self._last_success_time == "-":
            self.time_label.setText(_tr("最近成功: -"))
            return
        self.time_label.setText(f"{_tr('最近成功:')} {self._last_success_time}")

    def retranslate_ui(self) -> None:
        self.title_label.setText(_tr(self.page_title))
        self.input_card.retranslate_ui(_tr(self.input_label), _tr(self.input_placeholder))
        self.result_card.retranslate_ui(_tr(self.button_text))
        self._update_time_label()
        if self._summary_payload:
            self._render_summary()
        else:
            self._render_summary_placeholder(self.status_badge.title_label.text())
            if not self._raw_payload:
                self.result_output.setPlainText(
                    json.dumps({"message": _tr("在上方输入 key 后开始查询")}, ensure_ascii=False, indent=2)
                )

    def build_result_model(self, payload: dict[str, object]) -> tuple[str, str, str, list[tuple[str, str, str]]]:
        return (_tr("结果"), "-", _tr("无数据"), [(_tr("状态"), _tr("无数据"), "")])

    def load_cached_secret(self) -> None:
        payload = self.config_store.load()
        if not payload:
            self.secret_input.clear()
            return
        cached = payload.get(self.config_key)
        if isinstance(cached, str):
            self.secret_input.setText(cached)
        else:
            self.secret_input.clear()

    def auto_query_if_possible(self) -> None:
        secret = self.secret_input.text().strip()
        if not secret:
            return
        if self.query_controller.is_running():
            return
        self._run_query(self.mode, secret)

    def run_query_if_possible(self) -> None:
        self.auto_query_if_possible()

    def latest_success_time(self) -> str:
        return self._last_success_time

    def _display_amount(self, value: object) -> str:
        return format_currency_value(value)

    def stop_worker(self) -> None:
        self.query_controller.stop()


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
        config_store: ConfigStore,
        on_cache_changed: Callable[[], None],
        on_query_success: Callable[[str, dict[str, object]], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(config_store, on_cache_changed, on_query_success, parent)
        self.setObjectName("key-info-page")

    def build_result_model(
        self,
        payload: dict[str, object],
    ) -> tuple[str, str, str, list[tuple[str, str, str]]]:
        rate_limit = payload.get("rate_limit")
        requests = "-"
        interval = ""
        if isinstance(rate_limit, dict):
            requests = self._display_value(rate_limit.get("requests"))
            interval = self._display_value(rate_limit.get("interval"))

        return (
            _tr("剩余配额"),
            self._display_amount(payload.get("limit_remaining")),
            _tr("当前 key 还能继续使用的额度"),
            [
                (_tr("剩余配额"), self._display_amount(payload.get("limit_remaining")), _tr("当前 key 还能使用的额度")),
                (_tr("已用额度"), self._display_amount(payload.get("usage")), _tr("当前 key 已累计使用")),
                (_tr("总额度"), self._display_amount(payload.get("limit")), _tr("当前 key 的限制上限")),
                (_tr("今日使用"), self._display_amount(payload.get("usage_daily")), _tr("当天累计使用")),
                (_tr("本周使用"), self._display_amount(payload.get("usage_weekly")), _tr("最近一周累计使用")),
                (_tr("本月使用"), self._display_amount(payload.get("usage_monthly")), _tr("最近一月累计使用")),
                (_tr("标签"), self._display_value(payload.get("label")), _tr("OpenRouter 返回的 key 标签")),
                (_tr("重置周期"), self._display_value(payload.get("limit_reset")), _tr("配额按该周期重置")),
                (_tr("过期时间"), self._display_datetime(payload.get("expires_at")), _tr("key 的过期时间")),
                (_tr("免费层"), self._display_bool(payload.get("is_free_tier")), _tr("是否属于 free tier")),
                (_tr("管理 Key"), self._display_bool(payload.get("is_management_key")), _tr("当前 key 是否具备 management 能力")),
                (_tr("Provisioning Key"), self._display_bool(payload.get("is_provisioning_key")), _tr("当前 key 是否具备 provisioning 能力")),
                (_tr("速率限制"), requests, interval),
            ],
        )

    def _display_value(self, value: object) -> str:
        if value is None:
            return "-"
        return str(value)

    def _display_bool(self, value: object) -> str:
        if value is True:
            return _tr("是")
        if value is False:
            return _tr("否")
        return "-"

    def _display_datetime(self, value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            return "-"

        normalized = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(normalized)
        except ValueError:
            return value.strip()

        return dt.strftime(DISPLAY_DATETIME_FORMAT)


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
        config_store: ConfigStore,
        on_cache_changed: Callable[[], None],
        on_query_success: Callable[[str, dict[str, object]], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(config_store, on_cache_changed, on_query_success, parent)
        self.setObjectName("credits-page")

    def build_result_model(
        self,
        payload: dict[str, object],
    ) -> tuple[str, str, str, list[tuple[str, str, str]]]:
        return (
            _tr("剩余余额"),
            self._display_amount(payload.get("remaining_credits")),
            _tr("按 total_credits - total_usage 计算"),
            [
                (_tr("剩余余额"), self._display_amount(payload.get("remaining_credits")), _tr("按 total_credits - total_usage 计算")),
                (_tr("总余额"), self._display_amount(payload.get("total_credits")), _tr("账户累计 credits")),
                (_tr("已用余额"), self._display_amount(payload.get("total_usage")), _tr("账户累计使用")),
            ],
        )
