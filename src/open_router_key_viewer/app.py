from __future__ import annotations

import io
import json
import sys
import threading
from collections.abc import Callable
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtGui import QCloseEvent, QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

with redirect_stdout(io.StringIO()):
    from qfluentwidgets import (
        BodyLabel,
        CaptionLabel,
        ElevatedCardWidget,
        FluentIcon,
        FluentWindow,
        InfoBar,
        InfoBarPosition,
        MessageBox,
        LineEdit,
        PasswordLineEdit,
        PrimaryPushSettingCard,
        PrimaryPushButton,
        PushButton,
        PushSettingCard,
        SettingCardGroup,
        SingleDirectionScrollArea,
        StrongBodyLabel,
        SwitchButton,
        TextEdit,
        TitleLabel,
        setThemeColor,
    )

from open_router_key_viewer.services.config_store import ConfigStore
from open_router_key_viewer.services.openrouter import OpenRouterAPIError, OpenRouterClient

APP_DISPLAY_NAME = "OpenRouter Key Viewer"


class QueryWorker(QThread):
    succeeded = Signal(dict)
    failed = Signal(str)

    def __init__(self, mode: str, secret: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.mode = mode
        self.secret = secret
        self.client = OpenRouterClient()

    def run(self) -> None:
        try:
            if self.mode == "key-info":
                result = self.client.get_current_key_info(self.secret)
            elif self.mode == "credits":
                result = self.client.get_credits(self.secret)
            else:
                raise OpenRouterAPIError(f"Unsupported query mode: {self.mode}")
        except OpenRouterAPIError as exc:
            self.failed.emit(str(exc))
            return

        self.succeeded.emit(result.to_dict())


class MetricCard(ElevatedCardWidget):
    def __init__(self, title: str, value: str = "-", note: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(6)

        self.title_label = CaptionLabel(title, self)
        self.value_label = TitleLabel(value, self)
        self.note_label = BodyLabel(note, self)
        self.note_label.setWordWrap(True)

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.note_label)

    def set_value(self, value: str, note: str = "") -> None:
        self.value_label.setText(value)
        self.note_label.setText(note)


class PathActionCard(ElevatedCardWidget):
    def __init__(
        self,
        title: str,
        button_text: str,
        button_icon: FluentIcon,
        on_click: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(8)

        self.title_label = CaptionLabel(title, self)
        self.value_label = TitleLabel("-", self)
        self.note_label = BodyLabel("", self)
        self.note_label.setWordWrap(True)
        self.path_label = CaptionLabel("", self)
        self.path_label.setWordWrap(True)

        self.button = PushButton(button_text, self)
        self.button.setIcon(button_icon)
        self.button.clicked.connect(on_click)

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.note_label)
        layout.addWidget(self.path_label)
        layout.addWidget(self.button)

    def set_content(self, value: str, note: str, path: str, enabled: bool) -> None:
        self.value_label.setText(value)
        self.note_label.setText(note)
        self.path_label.setText(path)
        self.button.setEnabled(enabled)


class ResultCard(ElevatedCardWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(8)

        self.eyebrow = CaptionLabel("结果摘要", self)
        self.value_label = TitleLabel("-", self)
        self.note_label = BodyLabel("查询成功后会在这里显示关键结果", self)
        self.note_label.setWordWrap(True)

        layout.addWidget(self.eyebrow)
        layout.addWidget(self.value_label)
        layout.addWidget(self.note_label)

    def set_content(self, title: str, value: str, note: str) -> None:
        self.eyebrow.setText(title)
        self.value_label.setText(value)
        self.note_label.setText(note)


class DetailCard(ElevatedCardWidget):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(24, 22, 24, 22)
        self.layout_.setSpacing(10)
        self.title_label = StrongBodyLabel(title, self)
        self.layout_.addWidget(self.title_label)

    def set_rows(self, rows: list[tuple[str, str, str]]) -> None:
        while self.layout_.count() > 1:
            item = self.layout_.takeAt(1)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for label, value, note in rows:
            row = QWidget(self)
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(0, 10, 0, 10)
            row_layout.setSpacing(0)

            top_row = QHBoxLayout()
            top_row.setContentsMargins(0, 0, 0, 0)
            top_row.setSpacing(12)

            label_widget = CaptionLabel(label, row)
            label_widget.setMinimumWidth(96)
            top_row.addWidget(label_widget)

            value_widget = StrongBodyLabel(value, row)
            value_widget.setMinimumWidth(120)
            top_row.addWidget(value_widget)

            if note:
                note_label = CaptionLabel(note, row)
                note_label.setWordWrap(False)
                note_label.setStyleSheet("color: rgba(0, 0, 0, 0.62);")
                note_label.setMinimumWidth(220)
                top_row.addWidget(note_label, 1)
            else:
                top_row.addStretch(1)

            row_layout.addLayout(top_row)
            self.layout_.addWidget(row)
        self.layout_.addStretch(1)


class StatusBadge(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(0)

        self.title_label = CaptionLabel("等待查询", self)
        layout.addWidget(self.title_label)
        self.set_status("idle", "等待查询")

    def set_status(self, kind: str, title: str, detail: str = "") -> None:
        self.title_label.setText(title)

        styles = {
            "idle": ("#F3F7FB", "#D7E3F1", "#16324F"),
            "loading": ("#FFF7E8", "#F3D19C", "#6B4F00"),
            "success": ("#EAF7EF", "#A9D8B8", "#0E4F2F"),
            "error": ("#FDEEEE", "#E7A6A6", "#7A1F1F"),
        }
        bg, border, text = styles.get(kind, styles["idle"])
        self.setStyleSheet(
            "QWidget {"
            f"background-color: {bg};"
            "border-radius: 999px;"
            "}"
            f"QLabel {{ color: {text}; background: transparent; }}"
        )


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
        self._worker: QueryWorker | None = None
        self._summary_payload: dict[str, object] = {}
        self._http_meta: dict[str, object] = {}
        self._raw_payload: dict[str, object] = {}
        self._last_success_time = "-"
        self._build_ui()
        self.load_cached_secret()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.scroll_area = SingleDirectionScrollArea(self, Qt.Vertical)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.enableTransparentBackground()
        outer.addWidget(self.scroll_area)

        content = QWidget(self.scroll_area)
        self.scroll_area.setWidget(content)

        root = QVBoxLayout(content)
        root.setContentsMargins(36, 28, 36, 36)
        root.setSpacing(18)

        title = TitleLabel(self.page_title, self)
        root.addWidget(title)

        input_card = ElevatedCardWidget(self)
        input_layout = QVBoxLayout(input_card)
        input_layout.setContentsMargins(24, 22, 24, 22)
        input_layout.setSpacing(10)
        input_row = QHBoxLayout()
        input_row.setSpacing(12)
        input_label = StrongBodyLabel(self.input_label, input_card)
        input_label.setMinimumWidth(210)
        input_row.addWidget(input_label)

        self.secret_input = PasswordLineEdit(input_card)
        self.secret_input.setPlaceholderText(self.input_placeholder)
        input_row.addWidget(self.secret_input, 1)

        self.paste_button = PushButton("粘贴", input_card)
        self.paste_button.setIcon(FluentIcon.PASTE)
        self.paste_button.clicked.connect(self._paste_secret)
        input_row.addWidget(self.paste_button)

        self.copy_button = PushButton("复制", input_card)
        self.copy_button.setIcon(FluentIcon.COPY)
        self.copy_button.clicked.connect(self._copy_secret)
        input_row.addWidget(self.copy_button)

        self.save_button = PushButton("保存缓存", input_card)
        self.save_button.setIcon(FluentIcon.SAVE)
        self.save_button.clicked.connect(self._save_secret)
        input_row.addWidget(self.save_button)

        self.clear_saved_button = PushButton("删除缓存", input_card)
        self.clear_saved_button.setIcon(FluentIcon.DELETE)
        self.clear_saved_button.clicked.connect(self._clear_saved_secret)
        input_row.addWidget(self.clear_saved_button)

        input_layout.addLayout(input_row)
        root.addWidget(input_card)

        result_card = ElevatedCardWidget(self)
        result_layout = QVBoxLayout(result_card)
        result_layout.setContentsMargins(24, 22, 24, 22)
        result_layout.setSpacing(16)

        result_header = QHBoxLayout()
        result_header.setSpacing(12)

        self.query_button = PrimaryPushButton(self.button_text, result_card)
        self.query_button.setIcon(self.button_icon)
        self.query_button.clicked.connect(self._query)
        result_header.addWidget(self.query_button)

        self.status_badge = StatusBadge(result_card)
        result_header.addWidget(self.status_badge)
        result_header.addStretch(1)

        self.time_label = CaptionLabel("最近成功: -", result_card)
        result_header.addWidget(self.time_label)

        self.summary_toggle = PushButton("卡片", result_card)
        self.summary_toggle.clicked.connect(lambda: self._show_result_mode("summary"))
        result_header.addWidget(self.summary_toggle)

        self.raw_toggle = PushButton("原始 JSON", result_card)
        self.raw_toggle.clicked.connect(lambda: self._show_result_mode("raw"))
        result_header.addWidget(self.raw_toggle)

        result_layout.addLayout(result_header)

        self.summary_container = QWidget(result_card)
        self.summary_layout = QVBoxLayout(self.summary_container)
        self.summary_layout.setContentsMargins(0, 0, 0, 0)
        self.summary_layout.setSpacing(12)
        self.hero_card = ResultCard(self.summary_container)
        self.detail_card = DetailCard("详细信息", self.summary_container)
        self.summary_layout.addWidget(self.hero_card)
        self.summary_layout.addWidget(self.detail_card)
        result_layout.addWidget(self.summary_container)

        self.result_output = TextEdit(result_card)
        self.result_output.setReadOnly(True)
        self.result_output.setMinimumHeight(320)
        mono = QFont("JetBrains Mono")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.result_output.setFont(mono)
        self.result_output.setPlainText("{\n  \"message\": \"在上方输入 key 后开始查询\"\n}")
        result_layout.addWidget(self.result_output)

        root.addWidget(result_card, 1)
        self._show_result_mode("summary")
        self._render_summary_placeholder()

    def _set_busy(self, busy: bool, message: str) -> None:
        self.secret_input.setEnabled(not busy)
        self.query_button.setEnabled(not busy)
        self.paste_button.setEnabled(not busy)
        self.copy_button.setEnabled(not busy)
        self.save_button.setEnabled(not busy)
        self.clear_saved_button.setEnabled(not busy)

    def _query(self) -> None:
        secret = self.secret_input.text().strip()
        if not secret:
            self._show_error(self.missing_secret_message)
            return
        self._run_query(self.mode, secret)

    def _save_secret(self) -> None:
        secret = self.secret_input.text().strip()
        if not secret:
            self._show_error(self.missing_secret_message)
            return

        self.config_store.save_value(self.config_key, secret)
        self.on_cache_changed()
        InfoBar.success(
            title="已保存",
            content="已写入本地缓存",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2000,
            parent=self.window(),
        )

    def _paste_secret(self) -> None:
        text = QApplication.clipboard().text().strip()
        if not text:
            self._show_error("剪贴板里没有可用内容")
            return

        self.secret_input.setText(text)
        InfoBar.success(
            title="已粘贴",
            content="已从剪贴板填入当前 key",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=1500,
            parent=self.window(),
        )

    def _copy_secret(self) -> None:
        secret = self.secret_input.text().strip()
        if not secret:
            self._show_error(self.missing_secret_message)
            return

        QApplication.clipboard().setText(secret)
        InfoBar.success(
            title="已复制",
            content="当前 key 已复制到剪贴板",
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
            title="已清除",
            content="对应缓存已删除",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2000,
            parent=self.window(),
        )

    def _run_query(self, mode: str, secret: str) -> None:
        if self._worker and self._worker.isRunning():
            self._show_error("已有请求正在执行，请稍候")
            return

        self._set_busy(True, "查询中...")
        self.status_badge.set_status("loading", "查询中")
        self._summary_payload = {}
        self._http_meta = {}
        self._raw_payload = {}
        self._render_summary_placeholder("查询中...")
        self.result_output.setPlainText("{\n  \"loading\": true\n}")

        self._worker = QueryWorker(mode, secret, self)
        self._worker.succeeded.connect(self._handle_success)
        self._worker.failed.connect(self._handle_failure)
        self._worker.finished.connect(self._handle_finished)
        self._worker.start()

    def _handle_success(self, payload: dict) -> None:
        self._last_success_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.time_label.setText(f"最近成功: {self._last_success_time}")
        self.status_badge.set_status("success", "查询成功")
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
            title="请求成功",
            content="OpenRouter 返回了查询结果",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2000,
            parent=self.window(),
        )

    def _handle_failure(self, message: str) -> None:
        self.time_label.setText(f"最近成功: {self._last_success_time}")
        self.status_badge.set_status("error", "查询失败")
        self._summary_payload = {}
        self._http_meta = {}
        self._raw_payload = {"error": message}
        self._render_summary_placeholder("查询失败")
        self.result_output.setPlainText(json.dumps({"error": message}, ensure_ascii=False, indent=2))
        self._show_error(message)

    def _handle_finished(self) -> None:
        self._set_busy(False, self.status_badge.title_label.text())
        self._worker = None

    def _show_error(self, message: str) -> None:
        InfoBar.error(
            title="请求失败",
            content=message,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3000,
            parent=self.window(),
        )

    def _show_result_mode(self, mode: str) -> None:
        showing_summary = mode == "summary"
        self.summary_container.setVisible(showing_summary)
        self.result_output.setVisible(not showing_summary)
        self.summary_toggle.setEnabled(not showing_summary)
        self.raw_toggle.setEnabled(showing_summary)

    def _render_summary_placeholder(self, message: str = "等待查询") -> None:
        self.hero_card.set_content("状态", message, "查询成功后会在这里显示关键结果")
        self.detail_card.set_rows([("说明", "暂无结果", "先输入 key，再执行查询")])

    def _render_summary(self) -> None:
        hero_title, hero_value, hero_note, rows = self.build_result_model(self._summary_payload)
        self.hero_card.set_content(hero_title, hero_value, hero_note)
        self.detail_card.set_rows(rows)

    def build_result_model(self, payload: dict[str, object]) -> tuple[str, str, str, list[tuple[str, str, str]]]:
        return ("结果", "-", "无数据", [("状态", "无数据", "")])

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
        if self._worker and self._worker.isRunning():
            return
        self._run_query(self.mode, secret)

    def stop_worker(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.wait(3000)


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
            "剩余配额",
            self._display_amount(payload.get("limit_remaining")),
            "当前 key 还能继续使用的额度",
            [
                ("剩余配额", self._display_amount(payload.get("limit_remaining")), "当前 key 还能使用的额度"),
                ("已用额度", self._display_amount(payload.get("usage")), "当前 key 已累计使用"),
                ("总额度", self._display_amount(payload.get("limit")), "当前 key 的限制上限"),
                ("今日使用", self._display_amount(payload.get("usage_daily")), "当天累计使用"),
                ("本周使用", self._display_amount(payload.get("usage_weekly")), "最近一周累计使用"),
                ("本月使用", self._display_amount(payload.get("usage_monthly")), "最近一月累计使用"),
                ("标签", self._display_value(payload.get("label")), "OpenRouter 返回的 key 标签"),
                ("重置周期", self._display_value(payload.get("limit_reset")), "配额按该周期重置"),
                ("过期时间", self._display_datetime(payload.get("expires_at")), "key 的过期时间"),
                ("免费层", self._display_bool(payload.get("is_free_tier")), "是否属于 free tier"),
                ("管理 Key", self._display_bool(payload.get("is_management_key")), "当前 key 是否具备 management 能力"),
                ("Provisioning Key", self._display_bool(payload.get("is_provisioning_key")), "当前 key 是否具备 provisioning 能力"),
                ("速率限制", requests, interval),
            ],
        )

    def _display_amount(self, value: object) -> str:
        if isinstance(value, (int, float)):
            return f"${value:.4f}"
        return "-"

    def _display_value(self, value: object) -> str:
        if value is None:
            return "-"
        return str(value)

    def _display_bool(self, value: object) -> str:
        if value is True:
            return "是"
        if value is False:
            return "否"
        return "-"

    def _display_datetime(self, value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            return "-"

        normalized = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(normalized)
        except ValueError:
            return value.strip()

        return dt.strftime("%Y-%m-%d %H:%M:%S")


class CreditsPage(BaseQueryPage):
    page_title = "账户余额"
    input_label = "OpenRouter Management Key"
    input_placeholder = "输入 Management Key"
    button_text = "查询余额"
    button_icon = FluentIcon.INFO
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
            "剩余余额",
            self._display_amount(payload.get("remaining_credits")),
            "按 total_credits - total_usage 计算",
            [
            ("剩余余额", self._display_amount(payload.get("remaining_credits")), "按 total_credits - total_usage 计算"),
            ("总余额", self._display_amount(payload.get("total_credits")), "账户累计 credits"),
            ("已用余额", self._display_amount(payload.get("total_usage")), "账户累计使用"),
            ],
        )

    def _display_amount(self, value: object) -> str:
        if isinstance(value, (int, float)):
            return f"${value:.4f}"
        return "-"


class CachePage(QWidget):
    def __init__(
        self,
        config_store: ConfigStore,
        on_cache_changed: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("cache-page")
        self.config_store = config_store
        self.on_cache_changed = on_cache_changed
        self._build_ui()
        self.refresh_view()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.scroll_area = SingleDirectionScrollArea(self, Qt.Vertical)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.enableTransparentBackground()
        outer.addWidget(self.scroll_area)

        content = QWidget(self.scroll_area)
        self.scroll_area.setWidget(content)

        root = QVBoxLayout(content)
        root.setContentsMargins(36, 28, 36, 36)
        root.setSpacing(18)

        root.addWidget(TitleLabel("配置", self))

        summary_card = ElevatedCardWidget(self)
        summary_layout = QGridLayout(summary_card)
        summary_layout.setContentsMargins(24, 24, 24, 24)
        summary_layout.setHorizontalSpacing(12)
        summary_layout.setVerticalSpacing(12)

        self.dir_exists_card = PathActionCard(
            "缓存目录",
            "删除整个缓存目录",
            FluentIcon.DELETE,
            self._delete_config_dir,
            summary_card,
        )
        self.config_exists_card = PathActionCard(
            "配置文件",
            "删除配置文件",
            FluentIcon.DELETE,
            self._delete_config_file,
            summary_card,
        )
        self.entry_count_card = MetricCard("已缓存项目", "-", "", summary_card)
        self.file_count_card = MetricCard("目录内文件", "-", "", summary_card)

        summary_layout.addWidget(self.dir_exists_card, 0, 0)
        summary_layout.addWidget(self.config_exists_card, 0, 1)
        summary_layout.addWidget(self.entry_count_card, 1, 0)
        summary_layout.addWidget(self.file_count_card, 1, 1)
        root.addWidget(summary_card)

        auto_query_card = ElevatedCardWidget(self)
        auto_query_layout = QVBoxLayout(auto_query_card)
        auto_query_layout.setContentsMargins(24, 22, 24, 22)
        auto_query_layout.setSpacing(12)
        auto_query_layout.addWidget(StrongBodyLabel("启动行为", auto_query_card))

        self.auto_key_row = self._create_switch_row(
            "启动时自动查询 Key 配额",
            "auto_query_key_info",
            auto_query_card,
        )
        auto_query_layout.addWidget(self.auto_key_row)

        self.auto_credits_row = self._create_switch_row(
            "启动时自动查询账户余额",
            "auto_query_credits",
            auto_query_card,
        )
        auto_query_layout.addWidget(self.auto_credits_row)
        root.addWidget(auto_query_card)

        polling_card = ElevatedCardWidget(self)
        polling_layout = QVBoxLayout(polling_card)
        polling_layout.setContentsMargins(24, 22, 24, 22)
        polling_layout.setSpacing(12)
        polling_layout.addWidget(StrongBodyLabel("定时查询", polling_card))

        self.poll_key_switch_row = self._create_switch_row(
            "启用 Key 配额定时查询",
            "poll_key_info_enabled",
            polling_card,
        )
        polling_layout.addWidget(self.poll_key_switch_row)
        self.poll_key_interval_row = self._create_input_row(
            "Key 配额间隔（秒）",
            "poll_key_info_interval_seconds",
            "300",
            polling_card,
        )
        polling_layout.addWidget(self.poll_key_interval_row)

        self.poll_credits_switch_row = self._create_switch_row(
            "启用账户余额定时查询",
            "poll_credits_enabled",
            polling_card,
        )
        polling_layout.addWidget(self.poll_credits_switch_row)
        self.poll_credits_interval_row = self._create_input_row(
            "账户余额间隔（秒）",
            "poll_credits_interval_seconds",
            "300",
            polling_card,
        )
        polling_layout.addWidget(self.poll_credits_interval_row)
        root.addWidget(polling_card)

        alerts_card = ElevatedCardWidget(self)
        alerts_layout = QVBoxLayout(alerts_card)
        alerts_layout.setContentsMargins(24, 22, 24, 22)
        alerts_layout.setSpacing(12)
        alerts_layout.addWidget(StrongBodyLabel("告警与通知", alerts_card))

        self.notify_in_app_row = self._create_switch_row(
            "启用应用内通知",
            "notify_in_app",
            alerts_card,
        )
        alerts_layout.addWidget(self.notify_in_app_row)
        self.notify_system_row = self._create_switch_row(
            "启用系统通知",
            "notify_system",
            alerts_card,
        )
        alerts_layout.addWidget(self.notify_system_row)

        self.key_warning_row = self._create_input_row(
            "Key 配额 Warning 阈值",
            "key_info_warning_threshold",
            "5.0",
            alerts_card,
        )
        alerts_layout.addWidget(self.key_warning_row)
        self.key_critical_row = self._create_input_row(
            "Key 配额 Critical 阈值",
            "key_info_critical_threshold",
            "1.0",
            alerts_card,
        )
        alerts_layout.addWidget(self.key_critical_row)
        self.credits_warning_row = self._create_input_row(
            "账户余额 Warning 阈值",
            "credits_warning_threshold",
            "10.0",
            alerts_card,
        )
        alerts_layout.addWidget(self.credits_warning_row)
        self.credits_critical_row = self._create_input_row(
            "账户余额 Critical 阈值",
            "credits_critical_threshold",
            "2.0",
            alerts_card,
        )
        alerts_layout.addWidget(self.credits_critical_row)

        self.webhook_key_switch_row = self._create_switch_row(
            "启用 Key 配额 Webhook",
            "notify_webhook_key_info_enabled",
            alerts_card,
        )
        alerts_layout.addWidget(self.webhook_key_switch_row)
        self.webhook_key_only_critical_row = self._create_switch_row(
            "Key 配额仅 Critical Webhook",
            "notify_webhook_key_info_only_critical",
            alerts_card,
        )
        alerts_layout.addWidget(self.webhook_key_only_critical_row)
        self.webhook_key_url_row = self._create_input_row(
            "Key 配额 Webhook URL",
            "notify_webhook_key_info_url",
            "https://example.com/key",
            alerts_card,
        )
        alerts_layout.addWidget(self.webhook_key_url_row)

        self.webhook_credits_switch_row = self._create_switch_row(
            "启用账户余额 Webhook",
            "notify_webhook_credits_enabled",
            alerts_card,
        )
        alerts_layout.addWidget(self.webhook_credits_switch_row)
        self.webhook_credits_only_critical_row = self._create_switch_row(
            "账户余额仅 Critical Webhook",
            "notify_webhook_credits_only_critical",
            alerts_card,
        )
        alerts_layout.addWidget(self.webhook_credits_only_critical_row)
        self.webhook_credits_url_row = self._create_input_row(
            "账户余额 Webhook URL",
            "notify_webhook_credits_url",
            "https://example.com/credits",
            alerts_card,
        )
        alerts_layout.addWidget(self.webhook_credits_url_row)
        root.addWidget(alerts_card)

        content_card = ElevatedCardWidget(self)
        content_layout = QVBoxLayout(content_card)
        content_layout.setContentsMargins(24, 24, 24, 24)
        content_layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(12)

        self.status_label = BodyLabel("", content_card)
        header.addWidget(self.status_label)
        header.addStretch(1)

        self.refresh_button = PrimaryPushButton("刷新", content_card)
        self.refresh_button.setIcon(FluentIcon.SYNC)
        self.refresh_button.clicked.connect(self.refresh_view)
        header.addWidget(self.refresh_button)

        self.data_toggle = PushButton("解析数据", content_card)
        self.data_toggle.clicked.connect(lambda: self._show_mode("data"))
        header.addWidget(self.data_toggle)

        self.file_toggle = PushButton("原始文件", content_card)
        self.file_toggle.clicked.connect(lambda: self._show_mode("file"))
        header.addWidget(self.file_toggle)

        content_layout.addLayout(header)

        self.parsed_container = QWidget(content_card)
        self.parsed_layout = QVBoxLayout(self.parsed_container)
        self.parsed_layout.setContentsMargins(0, 0, 0, 0)
        self.parsed_layout.setSpacing(10)
        self.parsed_title = StrongBodyLabel("已解析的数据", self.parsed_container)
        self.parsed_layout.addWidget(self.parsed_title)
        self.parsed_rows = QWidget(self.parsed_container)
        self.parsed_rows_layout = QVBoxLayout(self.parsed_rows)
        self.parsed_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.parsed_rows_layout.setSpacing(10)
        self.parsed_layout.addWidget(self.parsed_rows)
        content_layout.addWidget(self.parsed_container)

        self.content_output = TextEdit(content_card)
        self.content_output.setReadOnly(True)
        mono = QFont("JetBrains Mono")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.content_output.setFont(mono)
        self.content_output.setMinimumHeight(420)
        content_layout.addWidget(self.content_output)

        root.addWidget(content_card, 1)
        self._show_mode("data")

    def refresh_view(self) -> None:
        snapshot = self.config_store.inspect()
        loaded_config = snapshot.get("loaded_config")
        payload = loaded_config if isinstance(loaded_config, dict) else {}
        files = snapshot.get("files", [])
        file_count = sum(1 for item in files if item.get("type") == "file")
        entry_count = len(payload)

        self.dir_exists_card.set_content(
            "已存在" if snapshot["dir_exists"] else "不存在",
            "缓存目录路径",
            str(snapshot["config_dir"]),
            bool(snapshot["dir_exists"]),
        )
        self.config_exists_card.set_content(
            "已存在" if snapshot["config_exists"] else "不存在",
            "config.json 文件路径",
            str(snapshot["config_path"]),
            bool(snapshot["config_exists"]),
        )
        self.entry_count_card.set_value(str(entry_count), "当前解析出的缓存键数量")
        self.file_count_card.set_value(str(file_count), "缓存目录内的文件数量")

        self.status_label.setText(
            "已解析本地缓存" if snapshot["config_exists"] else "未找到配置文件"
        )
        self._sync_switch_state(self.auto_key_row, bool(payload.get("auto_query_key_info", False)))
        self._sync_switch_state(self.auto_credits_row, bool(payload.get("auto_query_credits", False)))
        self._sync_switch_state(self.notify_in_app_row, bool(payload.get("notify_in_app", True)))
        self._sync_switch_state(self.notify_system_row, bool(payload.get("notify_system", True)))
        self._sync_switch_state(self.poll_key_switch_row, bool(payload.get("poll_key_info_enabled", False)))
        self._sync_switch_state(self.poll_credits_switch_row, bool(payload.get("poll_credits_enabled", False)))
        self._sync_switch_state(
            self.webhook_key_switch_row,
            bool(payload.get("notify_webhook_key_info_enabled", False)),
        )
        self._sync_switch_state(
            self.webhook_key_only_critical_row,
            bool(payload.get("notify_webhook_key_info_only_critical", True)),
        )
        self._sync_switch_state(
            self.webhook_credits_switch_row,
            bool(payload.get("notify_webhook_credits_enabled", False)),
        )
        self._sync_switch_state(
            self.webhook_credits_only_critical_row,
            bool(payload.get("notify_webhook_credits_only_critical", True)),
        )

        self._sync_input_row(self.poll_key_interval_row, payload.get("poll_key_info_interval_seconds", 300))
        self._sync_input_row(self.poll_credits_interval_row, payload.get("poll_credits_interval_seconds", 300))
        self._sync_input_row(self.key_warning_row, payload.get("key_info_warning_threshold", 5.0))
        self._sync_input_row(self.key_critical_row, payload.get("key_info_critical_threshold", 1.0))
        self._sync_input_row(self.credits_warning_row, payload.get("credits_warning_threshold", 10.0))
        self._sync_input_row(self.credits_critical_row, payload.get("credits_critical_threshold", 2.0))
        self._sync_input_row(self.webhook_key_url_row, payload.get("notify_webhook_key_info_url", ""))
        self._sync_input_row(self.webhook_credits_url_row, payload.get("notify_webhook_credits_url", ""))

        self._render_parsed_data(payload)
        self._file_text = self.config_store.read_raw_config() or "未找到 config.json 文件"
        self.content_output.setPlainText(self._file_text)
        self._show_mode(self._mode)

    def _show_mode(self, mode: str) -> None:
        self._mode = mode
        showing_data = mode == "data"
        self.data_toggle.setEnabled(not showing_data)
        self.file_toggle.setEnabled(showing_data)
        self.parsed_container.setVisible(showing_data)
        self.content_output.setVisible(not showing_data)

    def _display_config_key(self, key: str) -> str:
        mapping = {
            "api_key": "OpenRouter API Key",
            "management_key": "OpenRouter Management Key",
            "auto_query_key_info": "启动时自动查询 Key 配额",
            "auto_query_credits": "启动时自动查询账户余额",
            "poll_key_info_enabled": "启用 Key 配额定时查询",
            "poll_key_info_interval_seconds": "Key 配额间隔（秒）",
            "poll_credits_enabled": "启用账户余额定时查询",
            "poll_credits_interval_seconds": "账户余额间隔（秒）",
            "notify_in_app": "启用应用内通知",
            "notify_system": "启用系统通知",
            "key_info_warning_threshold": "Key 配额 Warning 阈值",
            "key_info_critical_threshold": "Key 配额 Critical 阈值",
            "credits_warning_threshold": "账户余额 Warning 阈值",
            "credits_critical_threshold": "账户余额 Critical 阈值",
            "notify_webhook_key_info_enabled": "启用 Key 配额 Webhook",
            "notify_webhook_key_info_only_critical": "Key 配额仅 Critical Webhook",
            "notify_webhook_key_info_url": "Key 配额 Webhook URL",
            "notify_webhook_credits_enabled": "启用账户余额 Webhook",
            "notify_webhook_credits_only_critical": "账户余额仅 Critical Webhook",
            "notify_webhook_credits_url": "账户余额 Webhook URL",
        }
        return mapping.get(key, key)

    def _render_parsed_data(self, loaded_config: object) -> None:
        if not isinstance(loaded_config, dict) or not loaded_config:
            rows = [("状态", "暂无数据", "")]
        else:
            rows = [
                (self._display_config_key(key), str(value), "")
                for key, value in loaded_config.items()
            ]
        self._render_property_rows(self.parsed_rows_layout, rows)

    def _render_property_rows(
        self,
        layout: QVBoxLayout,
        rows: list[tuple[str, str, str]],
    ) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for label, value, note in rows:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(12)

            label_widget = CaptionLabel(label, row)
            label_widget.setMinimumWidth(96)
            row_layout.addWidget(label_widget)

            value_widget = StrongBodyLabel(value, row)
            value_widget.setMinimumWidth(280)
            row_layout.addWidget(value_widget, 1)

            if note:
                note_widget = CaptionLabel(note, row)
                note_widget.setStyleSheet("color: rgba(0, 0, 0, 0.62);")
                note_widget.setMinimumWidth(180)
                row_layout.addWidget(note_widget, 1)

            layout.addWidget(row)
        layout.addStretch(1)

    def _create_switch_row(self, text: str, config_key: str, parent: QWidget) -> QWidget:
        row = QWidget(parent)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        label = StrongBodyLabel(text, row)
        layout.addWidget(label)
        layout.addStretch(1)

        switch = SwitchButton(row)
        switch.checkedChanged.connect(
            lambda checked, key=config_key, button=switch: self._toggle_auto_query(key, button, checked)
        )
        layout.addWidget(switch)

        row._switch = switch  # type: ignore[attr-defined]
        return row

    def _create_input_row(self, text: str, config_key: str, placeholder: str, parent: QWidget) -> QWidget:
        row = QWidget(parent)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        label = StrongBodyLabel(text, row)
        label.setMinimumWidth(220)
        layout.addWidget(label)

        line_edit = LineEdit(row)
        line_edit.setPlaceholderText(placeholder)
        layout.addWidget(line_edit, 1)

        save_button = PushButton("保存", row)
        save_button.clicked.connect(
            lambda: self._save_input_value(config_key, line_edit.text().strip(), placeholder)
        )
        layout.addWidget(save_button)

        row._line_edit = line_edit  # type: ignore[attr-defined]
        return row

    def _toggle_auto_query(self, config_key: str, button: SwitchButton, checked: bool) -> None:
        self.config_store.save_flag(config_key, checked)
        self._sync_switch_button(button, checked)
        self.on_cache_changed()

    def _sync_switch_state(self, row: QWidget, checked: bool) -> None:
        button = row._switch  # type: ignore[attr-defined]
        button.blockSignals(True)
        button.setChecked(checked)
        button.blockSignals(False)
        self._sync_switch_button(button, checked)

    def _sync_switch_button(self, button: SwitchButton, checked: bool) -> None:
        button.setOnText("开启")
        button.setOffText("关闭")

    def _save_input_value(self, config_key: str, raw_value: str, placeholder: str) -> None:
        if not raw_value:
            self.config_store.delete_value(config_key)
        else:
            value: object = raw_value
            if config_key.endswith("_interval_seconds"):
                try:
                    value = max(1, int(raw_value))
                except ValueError:
                    self._show_error("间隔必须是整数秒")
                    return
            elif config_key.endswith("_threshold"):
                try:
                    value = float(raw_value)
                except ValueError:
                    self._show_error("阈值必须是数字")
                    return
            self.config_store.save_value(config_key, value)

        self.on_cache_changed()
        InfoBar.success(
            title="已保存",
            content="配置已更新",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=1500,
            parent=self.window(),
        )

    def _sync_input_row(self, row: QWidget, value: object) -> None:
        line_edit = row._line_edit  # type: ignore[attr-defined]
        line_edit.setText("" if value is None else str(value))

    def _show_error(self, message: str) -> None:
        InfoBar.error(
            title="配置无效",
            content=message,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3000,
            parent=self.window(),
        )

    def _delete_config_file(self) -> None:
        if not self._confirm("删除配置文件", "确认删除 config.json 吗？"):
            return
        self.config_store.delete_config_file()
        self.on_cache_changed()
        InfoBar.success(
            title="已删除",
            content="配置文件已删除",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2000,
            parent=self.window(),
        )

    def _delete_config_dir(self) -> None:
        if not self._confirm("删除缓存目录", "确认删除整个 ~/.config/open-router-key-viewer 目录吗？"):
            return
        self.config_store.delete_config_dir()
        self.on_cache_changed()
        InfoBar.success(
            title="已删除",
            content="缓存目录已删除",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2000,
            parent=self.window(),
        )

    def _confirm(self, title: str, message: str) -> bool:
        box = MessageBox(title, message, self.window())
        box.yesButton.setText("确认")
        box.cancelButton.setText("取消")
        return bool(box.exec())


class MainWindow(FluentWindow):
    def __init__(self) -> None:
        super().__init__()
        self.config_store = ConfigStore()
        self._alert_state = {"key-info": "normal", "credits": "normal"}
        self._tray_icon: QSystemTrayIcon | None = None
        self.key_timer = QTimer(self)
        self.key_timer.timeout.connect(self.key_info_page_auto_query)
        self.credits_timer = QTimer(self)
        self.credits_timer.timeout.connect(self.credits_page_auto_query)
        self.key_info_page = KeyInfoPage(
            self.config_store,
            self.refresh_cache_views,
            self.handle_query_success,
            self,
        )
        self.credits_page = CreditsPage(
            self.config_store,
            self.refresh_cache_views,
            self.handle_query_success,
            self,
        )
        self.cache_page = CachePage(self.config_store, self.refresh_cache_views, self)
        self.addSubInterface(self.key_info_page, FluentIcon.SEARCH, "Key 配额")
        self.addSubInterface(self.credits_page, FluentIcon.INFO, "账户余额")
        self.addSubInterface(self.cache_page, FluentIcon.FOLDER, "配置")
        self.navigationInterface.setReturnButtonVisible(False)
        self.resize(960, 640)
        self.setWindowTitle(APP_DISPLAY_NAME)
        self._setup_tray_icon()
        QTimer.singleShot(0, self._run_startup_queries)

    def refresh_cache_views(self) -> None:
        self.key_info_page.load_cached_secret()
        self.credits_page.load_cached_secret()
        self.cache_page.refresh_view()
        self._apply_polling_settings()

    def _run_startup_queries(self) -> None:
        payload = self.config_store.load() or {}
        if payload.get("auto_query_key_info") and payload.get("api_key"):
            self.key_info_page.auto_query_if_possible()
        if payload.get("auto_query_credits") and payload.get("management_key"):
            self.credits_page.auto_query_if_possible()
        self._apply_polling_settings()

    def _apply_polling_settings(self) -> None:
        payload = self.config_store.load() or {}
        self._apply_timer(
            self.key_timer,
            bool(payload.get("poll_key_info_enabled")) and bool(payload.get("api_key")),
            int(payload.get("poll_key_info_interval_seconds", 300)),
        )
        self._apply_timer(
            self.credits_timer,
            bool(payload.get("poll_credits_enabled")) and bool(payload.get("management_key")),
            int(payload.get("poll_credits_interval_seconds", 300)),
        )

    def _apply_timer(self, timer: QTimer, enabled: bool, interval_seconds: int) -> None:
        if enabled:
            timer.start(max(1, interval_seconds) * 1000)
        else:
            timer.stop()

    def key_info_page_auto_query(self) -> None:
        self.key_info_page.auto_query_if_possible()

    def credits_page_auto_query(self) -> None:
        self.credits_page.auto_query_if_possible()

    def handle_query_success(self, mode: str, payload: dict[str, object]) -> None:
        summary = payload.get("summary", {})
        if not isinstance(summary, dict):
            return
        self._evaluate_thresholds(mode, summary)

    def _evaluate_thresholds(self, mode: str, summary: dict[str, object]) -> None:
        payload = self.config_store.load() or {}
        if mode == "key-info":
            value = summary.get("limit_remaining")
            warning = payload.get("key_info_warning_threshold")
            critical = payload.get("key_info_critical_threshold")
            target = "Key 配额"
            label = summary.get("label")
            subject = f"{target} · {label}" if isinstance(label, str) and label.strip() else target
        else:
            value = summary.get("remaining_credits")
            warning = payload.get("credits_warning_threshold")
            critical = payload.get("credits_critical_threshold")
            target = "账户余额"
            subject = target

        if not isinstance(value, (int, float)):
            return

        level = self._classify_level(float(value), critical, warning)
        previous = self._alert_state.get(mode, "normal")
        if level == "normal":
            self._alert_state[mode] = "normal"
            return
        if level == previous:
            return

        self._alert_state[mode] = level
        if payload.get("notify_in_app", True):
            self._notify_in_app(level, target, subject, float(value))
        if payload.get("notify_system", True):
            self._notify_system(level, target, subject, float(value))
        self._maybe_send_webhook(mode, level, float(value))

    def _classify_level(self, value: float, critical: object, warning: object) -> str:
        try:
            critical_value = float(critical)
        except (TypeError, ValueError):
            critical_value = -1.0
        try:
            warning_value = float(warning)
        except (TypeError, ValueError):
            warning_value = -1.0

        if critical_value >= 0 and value <= critical_value:
            return "critical"
        if warning_value >= 0 and value <= warning_value:
            return "warning"
        return "normal"

    def _notify_in_app(self, level: str, target: str, subject: str, value: float) -> None:
        title = APP_DISPLAY_NAME
        content = (
            f"{target} {'Critical' if level == 'critical' else 'Warning'} 告警\n"
            f"{subject} 当前值 {value:.4f}"
        )
        factory = InfoBar.error if level == "critical" else InfoBar.warning
        factory(
            title=title,
            content=content,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=-1,
            parent=self,
        )

    def _notify_system(self, level: str, target: str, subject: str, value: float) -> None:
        if self._tray_icon is None or not self._tray_icon.isVisible():
            return

        title = APP_DISPLAY_NAME
        content = (
            f"{target} {'Critical' if level == 'critical' else 'Warning'} 告警\n"
            f"{subject} 当前值 {value:.4f}"
        )
        icon = (
            QSystemTrayIcon.MessageIcon.Critical
            if level == "critical"
            else QSystemTrayIcon.MessageIcon.Warning
        )
        self._tray_icon.showMessage(title, content, icon, 5000)

    def _setup_tray_icon(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        tray_icon = QSystemTrayIcon(self)
        icon = self._load_app_icon()
        if icon.isNull():
            icon = QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.setWindowIcon(icon)
        QApplication.instance().setWindowIcon(icon)
        tray_icon.setIcon(icon)
        tray_icon.setToolTip(APP_DISPLAY_NAME)
        tray_icon.show()
        self._tray_icon = tray_icon

    def _load_app_icon(self) -> QIcon:
        candidates = [
            Path(__file__).resolve().parents[2] / "assets" / "open-router-key-viewer.svg",
            Path(sys.argv[0]).resolve().parent / "assets" / "open-router-key-viewer.svg",
        ]
        for path in candidates:
            if path.exists():
                return QIcon(str(path))
        return QIcon()

    def _maybe_send_webhook(self, mode: str, level: str, value: float) -> None:
        payload = self.config_store.load() or {}
        if mode == "key-info":
            enabled = bool(payload.get("notify_webhook_key_info_enabled"))
            url = payload.get("notify_webhook_key_info_url")
            only_critical = bool(payload.get("notify_webhook_key_info_only_critical", True))
            target = "key_info"
        else:
            enabled = bool(payload.get("notify_webhook_credits_enabled"))
            url = payload.get("notify_webhook_credits_url")
            only_critical = bool(payload.get("notify_webhook_credits_only_critical", True))
            target = "credits"

        if not enabled or not isinstance(url, str) or not url.strip():
            return
        if only_critical and level != "critical":
            return

        body = {
            "event": f"{target}_threshold_triggered",
            "level": level,
            "target": target,
            "current_value": value,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        threading.Thread(target=self._post_webhook, args=(url, body), daemon=True).start()

    def _post_webhook(self, url: str, body: dict[str, object]) -> None:
        data = json.dumps(body).encode("utf-8")
        request = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(request, timeout=10):
                pass
        except Exception:
            pass

    def closeEvent(self, event: QCloseEvent) -> None:
        self.key_timer.stop()
        self.credits_timer.stop()
        self.key_info_page.stop_worker()
        self.credits_page.stop_worker()
        if self._tray_icon is not None:
            self._tray_icon.hide()
        super().closeEvent(event)


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    setThemeColor("#0F6CBD")

    window = MainWindow()
    window.show()
    return app.exec()
