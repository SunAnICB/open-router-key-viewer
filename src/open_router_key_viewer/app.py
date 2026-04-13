from __future__ import annotations

import io
import json
import os
import sys
import threading
from collections.abc import Callable
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from PySide6.QtCore import QPoint, QThread, QTimer, Qt, QUrl, Signal, qVersion
from PySide6.QtGui import QCloseEvent, QDesktopServices, QFont, QGuiApplication, QIcon, QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QSizePolicy,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

with redirect_stdout(io.StringIO()):
    from qfluentwidgets import (
        BodyLabel,
        CaptionLabel,
        ComboBox,
        ElevatedCardWidget,
        FluentIcon,
        FluentWindow,
        InfoBar,
        InfoBarPosition,
        HyperlinkButton,
        MessageBox,
        LineEdit,
        PasswordLineEdit,
        PrimaryPushButton,
        PushButton,
        SegmentedWidget,
        SingleDirectionScrollArea,
        StrongBodyLabel,
        SwitchButton,
        TextEdit,
        TransparentToolButton,
        TitleLabel,
        setThemeColor,
    )

from open_router_key_viewer import __version__
from open_router_key_viewer.i18n import DictTranslator, LANGUAGE_OPTIONS, resolve_language_code, tr
from open_router_key_viewer.services.build_info import get_build_info
from open_router_key_viewer.services.config_store import ConfigStore
from open_router_key_viewer.services.openrouter import OpenRouterAPIError, OpenRouterClient
from open_router_key_viewer.services.update_checker import (
    BinaryUpdater,
    ReleaseAsset,
    GitHubReleaseChecker,
    UpdateCheckError,
    UpdateInstallError,
    UpdateCheckResult,
)

try:
    from open_router_key_viewer.sni_tray import SNITray
except ImportError:
    SNITray = None  # type: ignore[assignment,misc]

APP_DISPLAY_NAME = "OpenRouter Key Viewer"
APP_AUTHOR = "SunAnICB"
APP_AUTHOR_URL = "https://github.com/SunAnICB"
APP_REPOSITORY_URL = "https://github.com/SunAnICB/open-router-key-viewer"
APP_LICENSE_NAME = "MIT"
APP_DATA_SOURCE_URL = "https://openrouter.ai/docs/api-reference/overview"
DISPLAY_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
BINARY_ASSET_NAME = "open-router-key-viewer"
_tr = tr
DISPLAY_BACKEND_OPTIONS: list[tuple[str, str]] = [
    ("auto", "自动"),
    ("wayland", "Wayland"),
    ("x11", "X11"),
]


def format_currency_value(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"${value:.4f}"
    return "-"


def install_language(app: QApplication, language_code: str) -> None:
    translator = getattr(app, "_dict_translator", None)
    if translator is not None:
        app.removeTranslator(translator)

    new_translator = DictTranslator(language_code)
    app.installTranslator(new_translator)
    app._dict_translator = new_translator  # type: ignore[attr-defined]


def show_error_bar(parent: QWidget, title: str, message: str) -> None:
    InfoBar.error(
        title=title,
        content=message,
        orient=Qt.Orientation.Horizontal,
        isClosable=True,
        position=InfoBarPosition.TOP_RIGHT,
        duration=3000,
        parent=parent,
    )


def stop_thread(thread: QThread | None, timeout_ms: int = 3000) -> None:
    if thread is None or not thread.isRunning():
        return
    if thread.wait(timeout_ms):
        return
    thread.terminate()
    thread.wait(1000)


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


class UpdateCheckWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, checker: GitHubReleaseChecker, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.checker = checker

    def run(self) -> None:
        try:
            result = self.checker.check_latest_release()
        except UpdateCheckError as exc:
            self.failed.emit(str(exc))
            return
        self.succeeded.emit(result)


class UpdateInstallWorker(QThread):
    progress_changed = Signal(int, int)
    succeeded = Signal()
    failed = Signal(str)

    def __init__(
        self,
        updater: BinaryUpdater,
        asset: ReleaseAsset,
        current_pid: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.updater = updater
        self.asset = asset
        self.current_pid = current_pid

    def run(self) -> None:
        try:
            self.updater.install_from_asset(
                self.asset,
                current_pid=self.current_pid,
                progress_callback=self._emit_progress,
            )
        except UpdateInstallError as exc:
            self.failed.emit(str(exc))
            return
        self.succeeded.emit()

    def _emit_progress(self, received: int, total: int | None) -> None:
        self.progress_changed.emit(received, total or 0)


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

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)

    def set_value(self, value: str, note: str = "") -> None:
        self.value_label.setText(value)
        self.note_label.setText(note)


class WarningCard(ElevatedCardWidget):
    def __init__(self, title: str, message: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("warning-card")
        self.setStyleSheet(
            """
            WarningCard {
                background-color: rgba(255, 185, 0, 0.14);
                border: 1px solid rgba(255, 185, 0, 0.42);
                border-radius: 12px;
            }
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        icon_label = BodyLabel("\u26a0", self)
        icon_font = QFont(icon_label.font())
        icon_font.setPointSize(icon_font.pointSize() + 6)
        icon_label.setFont(icon_font)
        layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignTop)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)

        title_label = StrongBodyLabel(title, self)
        text_layout.addWidget(title_label)

        message_label = BodyLabel(message, self)
        message_label.setWordWrap(True)
        text_layout.addWidget(message_label)

        layout.addLayout(text_layout, 1)
        self.title_label = title_label
        self.message_label = message_label
        self._title_text = title
        self._message_text = message

    def retranslate_ui(self, title: str | None = None, message: str | None = None) -> None:
        if title is not None:
            self._title_text = title
        if message is not None:
            self._message_text = message
        self.title_label.setText(self._title_text)
        self.message_label.setText(self._message_text)


class UpdateCard(ElevatedCardWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(12)
        self.header_label = StrongBodyLabel(_tr("更新"), self)
        header.addWidget(self.header_label)
        header.addStretch(1)

        self.check_button = PushButton(_tr("检查更新"), self)
        self.check_button.setIcon(FluentIcon.SYNC)
        header.addWidget(self.check_button)

        self.release_button = PushButton(_tr("打开 Release"), self)
        self.release_button.setIcon(FluentIcon.LINK)
        self.release_button.setVisible(False)
        self.release_button.setEnabled(False)
        header.addWidget(self.release_button)

        self.replace_button = PrimaryPushButton(_tr("下载并替换"), self)
        self.replace_button.setIcon(FluentIcon.DOWNLOAD)
        self.replace_button.setVisible(False)
        self.replace_button.setEnabled(False)
        header.addWidget(self.replace_button)

        layout.addLayout(header)

        self.status_label = TitleLabel("-", self)
        layout.addWidget(self.status_label)

        self.note_label = BodyLabel("", self)
        self.note_label.setWordWrap(True)
        layout.addWidget(self.note_label)

        self.meta_label = CaptionLabel("", self)
        self.meta_label.setWordWrap(True)
        layout.addWidget(self.meta_label)

    def set_state(
        self,
        title: str,
        note: str,
        meta: str = "",
        *,
        can_open_release: bool = False,
        can_replace: bool = False,
    ) -> None:
        self.status_label.setText(title)
        self.note_label.setText(note)
        self.meta_label.setText(meta)
        self.release_button.setVisible(can_open_release)
        self.release_button.setEnabled(can_open_release)
        self.replace_button.setVisible(can_replace)
        self.replace_button.setEnabled(can_replace)

    def retranslate_ui(self) -> None:
        self.header_label.setText(_tr("更新"))
        self.check_button.setText(_tr("检查更新"))
        self.release_button.setText(_tr("打开 Release"))
        self.replace_button.setText(_tr("下载并替换"))


class ClickablePathLabel(CaptionLabel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setText("")
        self.setWordWrap(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(_tr("点击复制路径"))

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        path_text = self.text().strip()
        if path_text and path_text != "-":
            QApplication.clipboard().setText(path_text)
            InfoBar.success(
                title=_tr("已复制路径"),
                content=path_text,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=1500,
                parent=self.window(),
            )
        super().mousePressEvent(event)


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
        self.path_label = ClickablePathLabel(self)

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

    def set_labels(self, title: str, button_text: str) -> None:
        self.title_label.setText(title)
        self.button.setText(button_text)


class ResultCard(ElevatedCardWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(8)

        self.eyebrow = CaptionLabel(_tr("结果摘要"), self)
        self.value_label = TitleLabel("-", self)
        self.note_label = BodyLabel(_tr("查询成功后会在这里显示关键结果"), self)
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

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)

    def set_rows(self, rows: list[tuple[str, ...]]) -> None:
        while self.layout_.count() > 1:
            item = self.layout_.takeAt(1)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for row_data in rows:
            label, value, note, link = self._normalize_row(row_data)
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

            if link:
                value_widget = HyperlinkButton(row)
                value_widget.setText(value)
                value_widget.setUrl(link)
                value_widget.setMinimumWidth(120)
            else:
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

    def _normalize_row(self, row_data: tuple[str, ...]) -> tuple[str, str, str, str]:
        if len(row_data) == 3:
            label, value, note = row_data
            return label, value, note, ""
        if len(row_data) == 4:
            label, value, note, link = row_data
            return label, value, note, link
        raise ValueError(f"Unsupported row data: {row_data!r}")


class StatusBadge(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(0)
        self.kind = "idle"

        self.title_label = CaptionLabel(_tr("等待查询"), self)
        layout.addWidget(self.title_label)
        self.set_status("idle", _tr("等待查询"))

    def set_status(self, kind: str, title: str, detail: str = "") -> None:
        self.kind = kind
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

    def retranslate_ui(self) -> None:
        mapping = {
            "idle": _tr("等待查询"),
            "loading": _tr("查询中"),
            "success": _tr("查询成功"),
            "error": _tr("查询失败"),
        }
        self.set_status(self.kind, mapping.get(self.kind, _tr("等待查询")))


class FloatingMetricCard(ElevatedCardWidget):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 7, 8, 7)
        layout.setSpacing(4)

        self.title_label = CaptionLabel(title, self)
        self.value_label = StrongBodyLabel("-", self)
        self.time_label = CaptionLabel("-", self)

        self.title_label.setFixedWidth(52)
        self.value_label.setMinimumWidth(54)
        self.value_label.setMaximumWidth(84)
        self.value_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self.time_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addSpacing(6)
        layout.addWidget(self.time_label)

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)

    def set_content(self, value: str, refreshed_at: str) -> None:
        self.value_label.setText(value)
        self.time_label.setText(self._format_refresh_time(refreshed_at))

    def _format_refresh_time(self, refreshed_at: str) -> str:
        if refreshed_at in {"", "-"}:
            return "-"
        return refreshed_at


class FloatingWindow(QWidget):
    refresh_requested = Signal()
    full_window_requested = Signal()
    topmost_changed = Signal(bool)
    closed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._topmost_enabled = True
        self._allow_close = False
        self._drag_offset: QPoint | None = None
        self._build_ui()
        self._apply_window_flags(initial=True)

    def _build_ui(self) -> None:
        self.setWindowTitle(APP_DISPLAY_NAME)
        self.resize(292, 106)
        self.setMinimumSize(280, 102)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        shell = ElevatedCardWidget(self)
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(5, 4, 5, 5)
        shell_layout.setSpacing(2)

        header = QWidget(shell)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(2, 2, 2, 2)
        header_layout.setSpacing(3)

        self.refresh_button = PrimaryPushButton(_tr("刷新"), header)
        self.refresh_button.setIcon(FluentIcon.SYNC)
        self.refresh_button.setMinimumWidth(56)
        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        header_layout.addWidget(self.refresh_button)

        self.topmost_button = TransparentToolButton(header)
        self.topmost_button.setFixedSize(30, 30)
        self.topmost_button.clicked.connect(self._toggle_topmost)
        header_layout.addStretch(1)

        header_layout.addWidget(self.topmost_button)

        self.full_window_button = PushButton(_tr("主窗口"), header)
        self.full_window_button.setIcon(FluentIcon.HOME)
        self.full_window_button.setMinimumWidth(56)
        self.full_window_button.clicked.connect(self.full_window_requested.emit)
        header_layout.addWidget(self.full_window_button)

        shell_layout.addWidget(header)

        self.key_card = FloatingMetricCard(_tr("剩余配额"), shell)
        self.credits_card = FloatingMetricCard(_tr("账户余额"), shell)
        shell_layout.addWidget(self.key_card)
        shell_layout.addWidget(self.credits_card)
        root.addWidget(shell)
        self._refresh_topmost_button()

    def retranslate_ui(self) -> None:
        self.refresh_button.setText(_tr("刷新"))
        self.full_window_button.setText(_tr("主窗口"))
        self.key_card.set_title(_tr("剩余配额"))
        self.credits_card.set_title(_tr("账户余额"))
        self._refresh_topmost_button()

    def _toggle_topmost(self) -> None:
        self._topmost_enabled = not self._topmost_enabled
        self._refresh_topmost_button()
        self.topmost_changed.emit(self._topmost_enabled)

    def _refresh_topmost_button(self) -> None:
        icon = FluentIcon.PIN if self._topmost_enabled else FluentIcon.UNPIN
        tip = _tr("取消置顶") if self._topmost_enabled else _tr("置顶")
        self.topmost_button.setIcon(icon)
        self.topmost_button.setToolTip(tip)

    def _apply_window_flags(self, initial: bool = False) -> None:
        if initial:
            flags = Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
            if self._topmost_enabled:
                flags |= Qt.WindowType.WindowStaysOnTopHint
            self.setWindowFlags(flags)
            return

    def set_topmost(self, enabled: bool) -> None:
        self._topmost_enabled = enabled
        self._refresh_topmost_button()
        self._apply_window_flags(initial=True)

    def update_metrics(
        self,
        key_value: str,
        key_time: str,
        credits_value: str,
        credits_time: str,
    ) -> None:
        self.key_card.set_content(key_value, key_time)
        self.credits_card.set_content(credits_value, credits_time)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._allow_close:
            super().closeEvent(event)
            return
        self.closed.emit()
        event.ignore()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def close_for_shutdown(self) -> None:
        self._allow_close = True
        self.close()



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
        self._status_message = _tr("等待查询")
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
        self.scroll_area.enableTransparentBackground()
        outer.addWidget(self.scroll_area)

        content = QWidget(self.scroll_area)
        self.scroll_area.setWidget(content)

        root = QVBoxLayout(content)
        root.setContentsMargins(36, 28, 36, 36)
        root.setSpacing(18)

        self.title_label = TitleLabel(_tr(self.page_title), self)
        root.addWidget(self.title_label)

        input_card = ElevatedCardWidget(self)
        input_layout = QVBoxLayout(input_card)
        input_layout.setContentsMargins(24, 22, 24, 22)
        input_layout.setSpacing(10)
        input_row = QHBoxLayout()
        input_row.setSpacing(12)
        self.input_label_widget = StrongBodyLabel(_tr(self.input_label), input_card)
        self.input_label_widget.setMinimumWidth(210)
        input_row.addWidget(self.input_label_widget)

        self.secret_input = PasswordLineEdit(input_card)
        self.secret_input.setPlaceholderText(_tr(self.input_placeholder))
        input_row.addWidget(self.secret_input, 1)

        self.paste_button = PushButton(_tr("粘贴"), input_card)
        self.paste_button.setIcon(FluentIcon.PASTE)
        self.paste_button.clicked.connect(self._paste_secret)
        input_row.addWidget(self.paste_button)

        self.copy_button = PushButton(_tr("复制"), input_card)
        self.copy_button.setIcon(FluentIcon.COPY)
        self.copy_button.clicked.connect(self._copy_secret)
        input_row.addWidget(self.copy_button)

        self.save_button = PushButton(_tr("保存缓存"), input_card)
        self.save_button.setIcon(FluentIcon.SAVE)
        self.save_button.clicked.connect(self._save_secret)
        input_row.addWidget(self.save_button)

        self.clear_saved_button = PushButton(_tr("删除缓存"), input_card)
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

        self.query_button = PrimaryPushButton(_tr(self.button_text), result_card)
        self.query_button.setIcon(self.button_icon)
        self.query_button.clicked.connect(self._query)
        result_header.addWidget(self.query_button)

        self.status_badge = StatusBadge(result_card)
        result_header.addWidget(self.status_badge)
        result_header.addStretch(1)

        self.time_label = CaptionLabel(_tr("最近成功: -"), result_card)
        result_header.addWidget(self.time_label)

        self.result_mode_switch = SegmentedWidget(result_card)
        self.result_mode_switch.addItem("summary", _tr("结果卡片"), lambda: self._show_result_mode("summary"))
        self.result_mode_switch.addItem("raw", _tr("原始请求"), lambda: self._show_result_mode("raw"))
        result_header.addWidget(self.result_mode_switch)

        result_layout.addLayout(result_header)

        self.summary_container = QWidget(result_card)
        self.summary_layout = QVBoxLayout(self.summary_container)
        self.summary_layout.setContentsMargins(0, 0, 0, 0)
        self.summary_layout.setSpacing(12)
        self.hero_card = ResultCard(self.summary_container)
        self.detail_card = DetailCard(_tr("详细信息"), self.summary_container)
        self.summary_layout.addWidget(self.hero_card)
        self.summary_layout.addWidget(self.detail_card)
        result_layout.addWidget(self.summary_container)

        self.result_output = TextEdit(result_card)
        self.result_output.setReadOnly(True)
        self.result_output.setMinimumHeight(320)
        mono = QFont("JetBrains Mono")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.result_output.setFont(mono)
        self.result_output.setPlainText(
            json.dumps({"message": _tr("在上方输入 key 后开始查询")}, ensure_ascii=False, indent=2)
        )
        result_layout.addWidget(self.result_output)

        root.addWidget(result_card, 1)
        self._show_result_mode("summary")
        self._render_summary_placeholder()

    def _set_busy(self, busy: bool, message: str) -> None:
        self._status_message = message
        self.secret_input.setEnabled(not busy)
        self.query_button.setEnabled(not busy)
        self.paste_button.setEnabled(not busy)
        self.copy_button.setEnabled(not busy)
        self.save_button.setEnabled(not busy)
        self.clear_saved_button.setEnabled(not busy)

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
        if self._worker and self._worker.isRunning():
            self._show_error(_tr("已有请求正在执行，请稍候"))
            return

        self._set_busy(True, _tr("查询中..."))
        self.status_badge.set_status("loading", _tr("查询中"))
        self._summary_payload = {}
        self._http_meta = {}
        self._raw_payload = {}
        self._render_summary_placeholder(_tr("查询中..."))
        self.result_output.setPlainText("{\n  \"loading\": true\n}")

        self._worker = QueryWorker(mode, secret, self)
        self._worker.succeeded.connect(self._handle_success)
        self._worker.failed.connect(self._handle_failure)
        self._worker.finished.connect(self._handle_finished)
        self._worker.start()

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
        self._worker = None

    def _show_error(self, message: str) -> None:
        show_error_bar(self.window(), _tr("请求失败"), message)

    def _show_result_mode(self, mode: str) -> None:
        showing_summary = mode == "summary"
        self.summary_container.setVisible(showing_summary)
        self.result_output.setVisible(not showing_summary)
        self.result_mode_switch.setCurrentItem(mode)

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
        self.input_label_widget.setText(_tr(self.input_label))
        self.secret_input.setPlaceholderText(_tr(self.input_placeholder))
        self.paste_button.setText(_tr("粘贴"))
        self.copy_button.setText(_tr("复制"))
        self.save_button.setText(_tr("保存缓存"))
        self.clear_saved_button.setText(_tr("删除缓存"))
        self.query_button.setText(_tr(self.button_text))
        self.detail_card.set_title(_tr("详细信息"))
        self.result_mode_switch.setItemText("summary", _tr("结果卡片"))
        self.result_mode_switch.setItemText("raw", _tr("原始请求"))
        self.status_badge.retranslate_ui()
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
        if self._worker and self._worker.isRunning():
            return
        self._run_query(self.mode, secret)

    def run_query_if_possible(self) -> None:
        self.auto_query_if_possible()

    def latest_success_time(self) -> str:
        return self._last_success_time

    def _display_amount(self, value: object) -> str:
        return format_currency_value(value)

    def stop_worker(self) -> None:
        stop_thread(self._worker)


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

class CachePage(QWidget):
    def __init__(
        self,
        config_store: ConfigStore,
        on_cache_changed: Callable[[], None],
        on_language_changed: Callable[[str], None],
        on_open_floating_window: Callable[[], None],
        floating_window_supported: bool,
        indicator_available: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("cache-page")
        self.config_store = config_store
        self.on_cache_changed = on_cache_changed
        self.on_language_changed = on_language_changed
        self.on_open_floating_window = on_open_floating_window
        self.floating_window_supported = floating_window_supported
        self.indicator_available = indicator_available
        self._build_ui()
        self.refresh_view()

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
        self.scroll_area.enableTransparentBackground()
        outer.addWidget(self.scroll_area)

        content = QWidget(self.scroll_area)
        self.scroll_area.setWidget(content)

        root = QVBoxLayout(content)
        root.setContentsMargins(36, 28, 36, 36)
        root.setSpacing(18)

        header = QHBoxLayout()
        header.setSpacing(12)
        header.addWidget(TitleLabel(_tr("配置"), self))
        header.addStretch(1)
        header.addWidget(CaptionLabel(_tr("显示后端"), self))
        self.display_backend_combo = ComboBox(self)
        for code, label in DISPLAY_BACKEND_OPTIONS:
            self.display_backend_combo.addItem(_tr(label), userData=code)
        self.display_backend_combo.currentIndexChanged.connect(self._handle_display_backend_changed)
        header.addWidget(self.display_backend_combo)
        header.addWidget(CaptionLabel(_tr("界面语言"), self))
        self.language_combo = ComboBox(self)
        for code, label in LANGUAGE_OPTIONS:
            self.language_combo.addItem(label, userData=code)
        self.language_combo.currentIndexChanged.connect(self._handle_language_changed)
        header.addWidget(self.language_combo)
        root.addLayout(header)
        root.addWidget(
            WarningCard(
                _tr("敏感信息提示"),
                _tr(
                    "保存后的 OpenRouter API Key、OpenRouter Management Key 和 Webhook URL 会以明文写入本地 config.json。 如果设备由多人共用，请谨慎启用保存功能。"
                ),
                self,
            )
        )

        summary_card = ElevatedCardWidget(self)
        summary_layout = QGridLayout(summary_card)
        summary_layout.setContentsMargins(24, 24, 24, 24)
        summary_layout.setHorizontalSpacing(12)
        summary_layout.setVerticalSpacing(12)

        self.dir_exists_card = PathActionCard(
            _tr("缓存目录"),
            _tr("删除整个缓存目录"),
            FluentIcon.DELETE,
            self._delete_config_dir,
            summary_card,
        )
        self.config_exists_card = PathActionCard(
            _tr("配置文件"),
            _tr("删除配置文件"),
            FluentIcon.DELETE,
            self._delete_config_file,
            summary_card,
        )
        self.entry_count_card = MetricCard(_tr("已缓存项目"), "-", "", summary_card)
        self.file_count_card = MetricCard(_tr("目录内文件"), "-", "", summary_card)

        summary_layout.addWidget(self.dir_exists_card, 0, 0)
        summary_layout.addWidget(self.config_exists_card, 0, 1)
        summary_layout.addWidget(self.file_count_card, 1, 0)
        summary_layout.addWidget(self.entry_count_card, 1, 1)
        root.addWidget(summary_card)

        floating_card = ElevatedCardWidget(self)
        floating_layout = QHBoxLayout(floating_card)
        floating_layout.setContentsMargins(24, 22, 24, 22)
        floating_layout.setSpacing(12)
        floating_text = QVBoxLayout()
        floating_text.setContentsMargins(0, 0, 0, 0)
        floating_text.setSpacing(4)
        floating_text.addWidget(StrongBodyLabel(_tr("悬浮小窗"), floating_card))
        floating_hint_text = (
            _tr("切换到仅显示剩余配额和账户余额的顶层小窗。")
            if self.floating_window_supported
            else _tr("当前仅在 X11/xcb 启动时支持悬浮小窗。")
        )
        floating_hint = CaptionLabel(floating_hint_text, floating_card)
        floating_hint.setWordWrap(True)
        floating_text.addWidget(floating_hint)
        floating_layout.addLayout(floating_text, 1)

        self.open_floating_button = PrimaryPushButton(_tr("打开悬浮小窗"), floating_card)
        self.open_floating_button.setIcon(FluentIcon.OPEN_PANE if hasattr(FluentIcon, "OPEN_PANE") else FluentIcon.HOME)
        self.open_floating_button.clicked.connect(self.on_open_floating_window)
        self.open_floating_button.setEnabled(self.floating_window_supported)
        floating_layout.addWidget(self.open_floating_button)
        root.addWidget(floating_card)

        indicator_card = ElevatedCardWidget(self)
        indicator_layout = QHBoxLayout(indicator_card)
        indicator_layout.setContentsMargins(24, 22, 24, 22)
        indicator_layout.setSpacing(12)
        indicator_text = QVBoxLayout()
        indicator_text.setContentsMargins(0, 0, 0, 0)
        indicator_text.setSpacing(4)
        indicator_text.addWidget(StrongBodyLabel(_tr("顶栏指示器"), indicator_card))
        indicator_hint_text = (
            _tr("在 GNOME 顶栏显示滚动的配额和余额数据（Ubuntu 开箱即用，其他发行版需安装 AppIndicator 扩展）。")
            if self.indicator_available
            else _tr("当前环境不支持顶栏指示器（需要 D-Bus StatusNotifierWatcher 服务）。")
        )
        indicator_hint = CaptionLabel(indicator_hint_text, indicator_card)
        indicator_hint.setWordWrap(True)
        indicator_text.addWidget(indicator_hint)
        indicator_layout.addLayout(indicator_text, 1)
        self.indicator_switch_row = self._create_switch_row(
            _tr("启用顶栏指示器"),
            "panel_indicator_enabled",
            indicator_card,
        )
        self.indicator_switch_row.setEnabled(self.indicator_available)
        indicator_layout.addWidget(self.indicator_switch_row)
        root.addWidget(indicator_card)

        auto_query_card = ElevatedCardWidget(self)
        auto_query_layout = QVBoxLayout(auto_query_card)
        auto_query_layout.setContentsMargins(24, 22, 24, 22)
        auto_query_layout.setSpacing(12)
        auto_query_layout.addWidget(StrongBodyLabel(_tr("自动查询"), auto_query_card))

        auto_query_hint = CaptionLabel(_tr("每个对象在同一行设置启动时查询、定时查询和查询间隔。"), auto_query_card)
        auto_query_layout.addWidget(auto_query_hint)

        self.auto_key_row = self._create_auto_query_row(
            _tr("Key 配额"),
            "auto_query_key_info",
            "poll_key_info_enabled",
            "poll_key_info_interval_seconds",
            "300",
            auto_query_card,
        )
        auto_query_layout.addWidget(self.auto_key_row)

        self.auto_credits_row = self._create_auto_query_row(
            _tr("账户余额"),
            "auto_query_credits",
            "poll_credits_enabled",
            "poll_credits_interval_seconds",
            "300",
            auto_query_card,
        )
        auto_query_layout.addWidget(self.auto_credits_row)
        root.addWidget(auto_query_card)

        alerts_card = ElevatedCardWidget(self)
        alerts_layout = QVBoxLayout(alerts_card)
        alerts_layout.setContentsMargins(24, 22, 24, 22)
        alerts_layout.setSpacing(12)
        alerts_layout.addWidget(StrongBodyLabel(_tr("告警与通知"), alerts_card))

        self.notify_in_app_row = self._create_switch_row(
            _tr("启用应用内通知"),
            "notify_in_app",
            alerts_card,
        )
        alerts_layout.addWidget(self.notify_in_app_row)
        self.notify_system_row = self._create_switch_row(
            _tr("启用系统通知"),
            "notify_system",
            alerts_card,
        )
        alerts_layout.addWidget(self.notify_system_row)

        self.key_warning_row = self._create_input_row(
            _tr("Key 配额 Warning 阈值"),
            "key_info_warning_threshold",
            "5.0",
            alerts_card,
        )
        alerts_layout.addWidget(self.key_warning_row)
        self.key_critical_row = self._create_input_row(
            _tr("Key 配额 Critical 阈值"),
            "key_info_critical_threshold",
            "1.0",
            alerts_card,
        )
        alerts_layout.addWidget(self.key_critical_row)
        self.credits_warning_row = self._create_input_row(
            _tr("账户余额 Warning 阈值"),
            "credits_warning_threshold",
            "10.0",
            alerts_card,
        )
        alerts_layout.addWidget(self.credits_warning_row)
        self.credits_critical_row = self._create_input_row(
            _tr("账户余额 Critical 阈值"),
            "credits_critical_threshold",
            "2.0",
            alerts_card,
        )
        alerts_layout.addWidget(self.credits_critical_row)

        self.webhook_key_switch_row = self._create_switch_row(
            _tr("启用 Key 配额 Webhook"),
            "notify_webhook_key_info_enabled",
            alerts_card,
        )
        alerts_layout.addWidget(self.webhook_key_switch_row)
        self.webhook_key_only_critical_row = self._create_switch_row(
            _tr("Key 配额仅 Critical Webhook"),
            "notify_webhook_key_info_only_critical",
            alerts_card,
        )
        alerts_layout.addWidget(self.webhook_key_only_critical_row)
        self.webhook_key_url_row = self._create_input_row(
            _tr("Key 配额 Webhook URL"),
            "notify_webhook_key_info_url",
            "https://example.com/key",
            alerts_card,
        )
        alerts_layout.addWidget(self.webhook_key_url_row)

        self.webhook_credits_switch_row = self._create_switch_row(
            _tr("启用账户余额 Webhook"),
            "notify_webhook_credits_enabled",
            alerts_card,
        )
        alerts_layout.addWidget(self.webhook_credits_switch_row)
        self.webhook_credits_only_critical_row = self._create_switch_row(
            _tr("账户余额仅 Critical Webhook"),
            "notify_webhook_credits_only_critical",
            alerts_card,
        )
        alerts_layout.addWidget(self.webhook_credits_only_critical_row)
        self.webhook_credits_url_row = self._create_input_row(
            _tr("账户余额 Webhook URL"),
            "notify_webhook_credits_url",
            "https://example.com/credits",
            alerts_card,
        )
        alerts_layout.addWidget(self.webhook_credits_url_row)
        root.addWidget(alerts_card)

        update_card = ElevatedCardWidget(self)
        update_layout = QVBoxLayout(update_card)
        update_layout.setContentsMargins(24, 22, 24, 22)
        update_layout.setSpacing(12)
        update_layout.addWidget(StrongBodyLabel(_tr("软件更新"), update_card))

        update_hint = CaptionLabel(
            _tr("控制软件启动时是否自动检查 GitHub Release 更新。"),
            update_card,
        )
        update_hint.setWordWrap(True)
        update_layout.addWidget(update_hint)

        self.auto_update_row = self._create_switch_row(
            _tr("启动时自动检查更新"),
            "auto_check_updates",
            update_card,
        )
        update_layout.addWidget(self.auto_update_row)
        root.addWidget(update_card)

        content_card = ElevatedCardWidget(self)
        content_layout = QVBoxLayout(content_card)
        content_layout.setContentsMargins(24, 24, 24, 24)
        content_layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(12)

        self.status_label = BodyLabel("", content_card)
        header.addWidget(self.status_label)
        header.addStretch(1)

        self.refresh_button = PrimaryPushButton(_tr("刷新"), content_card)
        self.refresh_button.setIcon(FluentIcon.SYNC)
        self.refresh_button.clicked.connect(self.refresh_view)
        header.addWidget(self.refresh_button)

        self.content_mode_switch = SegmentedWidget(content_card)
        self.content_mode_switch.addItem("data", _tr("解析数据"), lambda: self._show_mode("data"))
        self.content_mode_switch.addItem("file", _tr("原始文件"), lambda: self._show_mode("file"))
        header.addWidget(self.content_mode_switch)

        content_layout.addLayout(header)

        self.parsed_container = QWidget(content_card)
        self.parsed_layout = QVBoxLayout(self.parsed_container)
        self.parsed_layout.setContentsMargins(0, 0, 0, 0)
        self.parsed_layout.setSpacing(10)
        self.parsed_title = StrongBodyLabel(_tr("已解析的数据"), self.parsed_container)
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

    def retranslate_ui(self) -> None:
        scroll_value = self.scroll_area.verticalScrollBar().value()
        while self.layout().count():
            item = self.layout().takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                while child_layout.count():
                    child_item = child_layout.takeAt(0)
                    child_widget = child_item.widget()
                    if child_widget is not None:
                        child_widget.deleteLater()
        self._build_ui()
        self.refresh_view()
        QTimer.singleShot(0, lambda: self.scroll_area.verticalScrollBar().setValue(scroll_value))

    def refresh_view(self) -> None:
        snapshot = self.config_store.inspect()
        loaded_config = snapshot.get("loaded_config")
        payload = loaded_config if isinstance(loaded_config, dict) else {}
        language_code = resolve_language_code(payload.get("ui_language"))
        display_backend = self._resolve_display_backend(payload.get("display_backend"))
        files = snapshot.get("files", [])
        file_count = sum(1 for item in files if item.get("type") == "file")
        entry_count = len(payload)

        self.dir_exists_card.set_content(
            _tr("已存在") if snapshot["dir_exists"] else _tr("不存在"),
            _tr("缓存目录路径"),
            str(snapshot["config_dir"]),
            bool(snapshot["dir_exists"]),
        )
        self.config_exists_card.set_content(
            _tr("已存在") if snapshot["config_exists"] else _tr("不存在"),
            _tr("config.json 文件路径"),
            str(snapshot["config_path"]),
            bool(snapshot["config_exists"]),
        )
        self.entry_count_card.set_value(str(entry_count), _tr("当前解析出的缓存键数量"))
        self.file_count_card.set_value(str(file_count), _tr("缓存目录内的文件数量"))

        self.status_label.setText(
            _tr("已解析本地缓存") if snapshot["config_exists"] else _tr("未找到配置文件")
        )
        self._sync_display_backend_combo(display_backend)
        self._sync_language_combo(language_code)
        self._sync_auto_query_row(
            self.auto_key_row,
            bool(payload.get("auto_query_key_info", False)),
            bool(payload.get("poll_key_info_enabled", False)),
            payload.get("poll_key_info_interval_seconds", 300),
        )
        self._sync_auto_query_row(
            self.auto_credits_row,
            bool(payload.get("auto_query_credits", False)),
            bool(payload.get("poll_credits_enabled", False)),
            payload.get("poll_credits_interval_seconds", 300),
        )
        self._sync_switch_state(
            self.auto_update_row,
            bool(payload.get("auto_check_updates", True)),
        )
        self._sync_switch_state(
            self.indicator_switch_row,
            bool(payload.get("panel_indicator_enabled", False)),
        )
        self._sync_switch_state(self.notify_in_app_row, bool(payload.get("notify_in_app", True)))
        self._sync_switch_state(self.notify_system_row, bool(payload.get("notify_system", True)))
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

        self._sync_input_row(self.key_warning_row, payload.get("key_info_warning_threshold", 5.0))
        self._sync_input_row(self.key_critical_row, payload.get("key_info_critical_threshold", 1.0))
        self._sync_input_row(self.credits_warning_row, payload.get("credits_warning_threshold", 10.0))
        self._sync_input_row(self.credits_critical_row, payload.get("credits_critical_threshold", 2.0))
        self._sync_input_row(self.webhook_key_url_row, payload.get("notify_webhook_key_info_url", ""))
        self._sync_input_row(self.webhook_credits_url_row, payload.get("notify_webhook_credits_url", ""))

        self._render_parsed_data(payload)
        self._file_text = self.config_store.read_raw_config() or _tr("未找到 config.json 文件")
        self.content_output.setPlainText(self._file_text)
        self._show_mode(self._mode)

    def _resolve_display_backend(self, value: object) -> str:
        if isinstance(value, str) and value in {code for code, _ in DISPLAY_BACKEND_OPTIONS}:
            return value
        return "auto"

    def _sync_display_backend_combo(self, backend: str) -> None:
        index = self.display_backend_combo.findData(backend)
        if index < 0:
            index = 0
        self.display_backend_combo.blockSignals(True)
        self.display_backend_combo.setCurrentIndex(index)
        self.display_backend_combo.blockSignals(False)

    def _handle_display_backend_changed(self, index: int) -> None:
        _ = index
        backend = self.display_backend_combo.currentData()
        if not isinstance(backend, str):
            return
        current_backend = self._resolve_display_backend((self.config_store.load() or {}).get("display_backend"))
        if backend == current_backend:
            return
        if backend == "auto":
            self.config_store.delete_value("display_backend")
        else:
            self.config_store.save_value("display_backend", backend)
        InfoBar.success(
            title=_tr("已保存"),
            content=_tr("显示后端已更新，重启后生效"),
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3000,
            parent=self.window(),
        )
        self.on_cache_changed()

    def _sync_language_combo(self, language_code: str) -> None:
        index = self.language_combo.findData(language_code)
        if index < 0:
            index = 0
        self.language_combo.blockSignals(True)
        self.language_combo.setCurrentIndex(index)
        self.language_combo.blockSignals(False)

    def _handle_language_changed(self, index: int) -> None:
        _ = index
        language_code = self.language_combo.currentData()
        if not isinstance(language_code, str):
            return
        current_language = resolve_language_code((self.config_store.load() or {}).get("ui_language"))
        if language_code == current_language:
            return
        self.config_store.save_value("ui_language", language_code)
        self.on_language_changed(language_code)

    def _show_mode(self, mode: str) -> None:
        self._mode = mode
        showing_data = mode == "data"
        self.parsed_container.setVisible(showing_data)
        self.content_output.setVisible(not showing_data)
        self.content_mode_switch.setCurrentItem(mode)

    def _display_config_key(self, key: str) -> str:
        mapping = {
            "api_key": "OpenRouter API Key",
            "management_key": "OpenRouter Management Key",
            "display_backend": "显示后端",
            "ui_language": "界面语言",
            "auto_check_updates": "启动时自动检查更新",
            "auto_query_key_info": "启动时自动查询 Key 配额",
            "auto_query_credits": "启动时自动查询账户余额",
            "poll_key_info_enabled": "启用 Key 配额定时查询",
            "poll_key_info_interval_seconds": "Key 配额间隔（秒）",
            "poll_credits_enabled": "启用账户余额定时查询",
            "poll_credits_interval_seconds": "账户余额间隔（秒）",
            "panel_indicator_enabled": "启用顶栏指示器",
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
        return _tr(mapping.get(key, key))

    def _render_parsed_data(self, loaded_config: object) -> None:
        if not isinstance(loaded_config, dict) or not loaded_config:
            rows = [(_tr("状态"), _tr("暂无数据"), "")]
        else:
            rows = [
                (self._display_config_key(key), self._display_config_value(key, value), "")
                for key, value in loaded_config.items()
            ]
        self._render_property_rows(self.parsed_rows_layout, rows)

    def _display_config_value(self, key: str, value: object) -> str:
        if key == "ui_language" and isinstance(value, str):
            label_map = {code: label for code, label in LANGUAGE_OPTIONS}
            return label_map.get(value, value)
        if key == "display_backend" and isinstance(value, str):
            label_map = {code: _tr(label) for code, label in DISPLAY_BACKEND_OPTIONS}
            return label_map.get(value, value)
        return str(value)

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

    def _create_auto_query_row(
        self,
        title: str,
        auto_query_key: str,
        poll_key: str,
        interval_key: str,
        placeholder: str,
        parent: QWidget,
    ) -> QWidget:
        row = QWidget(parent)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        title_label = StrongBodyLabel(title, row)
        title_label.setMinimumWidth(96)
        layout.addWidget(title_label)

        auto_label = CaptionLabel(_tr("启动时查询"), row)
        layout.addWidget(auto_label)

        auto_switch = SwitchButton(row)
        auto_switch.checkedChanged.connect(
            lambda checked, key=auto_query_key, button=auto_switch: self._toggle_auto_query(key, button, checked)
        )
        layout.addWidget(auto_switch)

        poll_label = CaptionLabel(_tr("定时查询"), row)
        layout.addWidget(poll_label)

        poll_switch = SwitchButton(row)
        poll_switch.checkedChanged.connect(
            lambda checked, key=poll_key, button=poll_switch: self._toggle_auto_query(key, button, checked)
        )
        layout.addWidget(poll_switch)

        interval_label = CaptionLabel(_tr("查询间隔（秒）"), row)
        layout.addWidget(interval_label)

        interval_input = LineEdit(row)
        interval_input.setPlaceholderText(placeholder)
        interval_input.setFixedWidth(120)
        interval_input.editingFinished.connect(
            lambda key=interval_key, line_edit=interval_input: self._save_input_value(
                key, line_edit.text().strip(), placeholder
            )
        )
        layout.addWidget(interval_input)
        layout.addStretch(1)

        row._auto_switch = auto_switch  # type: ignore[attr-defined]
        row._poll_switch = poll_switch  # type: ignore[attr-defined]
        row._line_edit = interval_input  # type: ignore[attr-defined]
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

        save_button = PushButton(_tr("保存"), row)
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

    def _sync_auto_query_row(
        self,
        row: QWidget,
        auto_checked: bool,
        poll_checked: bool,
        interval_value: object,
    ) -> None:
        auto_switch = row._auto_switch  # type: ignore[attr-defined]
        poll_switch = row._poll_switch  # type: ignore[attr-defined]
        line_edit = row._line_edit  # type: ignore[attr-defined]

        for button, checked in ((auto_switch, auto_checked), (poll_switch, poll_checked)):
            button.blockSignals(True)
            button.setChecked(checked)
            button.blockSignals(False)
            self._sync_switch_button(button, checked)

        line_edit.blockSignals(True)
        line_edit.setText("" if interval_value is None else str(interval_value))
        line_edit.blockSignals(False)

    def _sync_switch_button(self, button: SwitchButton, checked: bool) -> None:
        button.setOnText(_tr("开启"))
        button.setOffText(_tr("关闭"))

    def _save_input_value(self, config_key: str, raw_value: str, placeholder: str) -> None:
        if not raw_value:
            self.config_store.delete_value(config_key)
        else:
            value: object = raw_value
            if config_key.endswith("_interval_seconds"):
                try:
                    value = max(1, int(raw_value))
                except ValueError:
                    self._show_error(_tr("间隔必须是整数秒"))
                    return
            elif config_key.endswith("_threshold"):
                try:
                    value = float(raw_value)
                except ValueError:
                    self._show_error(_tr("阈值必须是数字"))
                    return
            self.config_store.save_value(config_key, value)

        self.on_cache_changed()
        InfoBar.success(
            title=_tr("已保存"),
            content=_tr("配置已更新"),
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=1500,
            parent=self.window(),
        )

    def _sync_input_row(self, row: QWidget, value: object) -> None:
        line_edit = row._line_edit  # type: ignore[attr-defined]
        line_edit.blockSignals(True)
        line_edit.setText("" if value is None else str(value))
        line_edit.blockSignals(False)

    def _show_error(self, message: str) -> None:
        show_error_bar(self.window(), _tr("配置无效"), message)

    def _delete_config_file(self) -> None:
        if not self._confirm(_tr("删除配置文件"), _tr("确认删除 config.json 吗？")):
            return
        self.config_store.delete_config_file()
        self.on_cache_changed()
        InfoBar.success(
            title=_tr("已删除"),
            content=_tr("配置文件已删除"),
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2000,
            parent=self.window(),
        )

    def _delete_config_dir(self) -> None:
        if not self._confirm(_tr("删除缓存目录"), _tr("确认删除整个 ~/.config/open-router-key-viewer 目录吗？")):
            return
        self.config_store.delete_config_dir()
        self.on_cache_changed()
        InfoBar.success(
            title=_tr("已删除"),
            content=_tr("缓存目录已删除"),
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2000,
            parent=self.window(),
        )

    def _confirm(self, title: str, message: str) -> bool:
        box = MessageBox(title, message, self.window())
        box.yesButton.setText(_tr("确认"))
        box.cancelButton.setText(_tr("取消"))
        return bool(box.exec())


class AboutPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("about-page")
        self._release_url = APP_REPOSITORY_URL + "/releases"
        self._latest_asset: ReleaseAsset | None = None
        self._update_worker: UpdateCheckWorker | None = None
        self._install_worker: UpdateInstallWorker | None = None
        self._binary_update_supported = bool(getattr(sys, "frozen", False))
        self._binary_updater = BinaryUpdater(Path(sys.executable)) if self._binary_update_supported else None
        self._build_info = get_build_info()
        self._startup_silent_check = False
        self._refresh_update_card_state: Callable[[], None] = lambda: None
        if self._binary_updater is not None:
            self._binary_updater.cleanup_stale_updates()
        owner, repo = self._parse_repo(APP_REPOSITORY_URL)
        self._release_checker = GitHubReleaseChecker(
            owner,
            repo,
            asset_name=BINARY_ASSET_NAME,
            current_version=__version__,
        )
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll_area = SingleDirectionScrollArea(self, Qt.Vertical)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.enableTransparentBackground()
        outer.addWidget(scroll_area)

        content = QWidget(scroll_area)
        scroll_area.setWidget(content)

        root = QVBoxLayout(content)
        root.setContentsMargins(36, 28, 36, 36)
        root.setSpacing(18)

        self.title_label = TitleLabel(_tr("关于"), self)
        root.addWidget(self.title_label)

        hero_card = ElevatedCardWidget(self)
        hero_layout = QVBoxLayout(hero_card)
        hero_layout.setContentsMargins(24, 22, 24, 22)
        hero_layout.setSpacing(8)
        hero_layout.addWidget(StrongBodyLabel(APP_DISPLAY_NAME, hero_card))
        hero_layout.addWidget(TitleLabel(f"v{__version__}", hero_card))

        self.description_label = BodyLabel(
            _tr("用于查询 OpenRouter API Key 配额和 OpenRouter Management Key 账户余额。"),
            hero_card,
        )
        self.description_label.setWordWrap(True)
        hero_layout.addWidget(self.description_label)
        root.addWidget(hero_card)

        self.update_card = UpdateCard(self)
        self.update_card.check_button.clicked.connect(self._check_updates)
        self.update_card.release_button.clicked.connect(self._open_release_page)
        self.update_card.replace_button.clicked.connect(self._replace_current_binary)
        self._show_intro_state()
        root.addWidget(self.update_card)

        self.details_card = DetailCard(_tr("版本信息"), self)
        self.details_card.set_rows(
            [
                (_tr("应用名称"), APP_DISPLAY_NAME, ""),
                (
                    _tr("版本"),
                    f"v{__version__}",
                    f"{self._short_commit(self._build_info.commit_sha)} · "
                    f"{'dirty' if self._build_info.dirty else 'clean'}",
                ),
                (_tr("运行方式"), _tr("二进制发布") if self._binary_update_supported else _tr("源码运行"), ""),
                (_tr("作者"), APP_AUTHOR, "", APP_AUTHOR_URL),
                ("Python", sys.version.split()[0], ""),
                ("Qt", qVersion(), ""),
                (_tr("许可证"), APP_LICENSE_NAME, ""),
            ]
        )
        root.addWidget(self.details_card)

        self.notes_card = DetailCard(_tr("项目"), self)
        self.notes_card.set_rows(
            [
                (_tr("仓库地址"), "GitHub Repository", "", APP_REPOSITORY_URL),
                (_tr("数据来源"), "OpenRouter API Reference", "", APP_DATA_SOURCE_URL),
            ]
        )
        root.addWidget(self.notes_card)

    def _show_intro_state(self) -> None:
        if self._binary_update_supported:
            self.update_card.set_state(
                _tr("可检查二进制更新"),
                _tr("当前为打包后的二进制运行。点击“检查更新”后，将对比 GitHub Release 中的最新版本。"),
                _tr("支持打开 Release 页面，也支持下载并在应用退出后替换当前二进制文件。"),
                can_open_release=True,
            )
        else:
            self.update_card.set_state(
                _tr("可检查更新"),
                _tr("当前是源码运行模式。你仍然可以查看最新 Release 和版本信息。"),
                _tr("源码运行不支持下载后直接替换当前二进制文件。"),
                can_open_release=True,
            )
        self._refresh_update_card_state = self._show_intro_state

    def retranslate_ui(self) -> None:
        self.title_label.setText(_tr("关于"))
        self.description_label.setText(_tr("用于查询 OpenRouter API Key 配额和 OpenRouter Management Key 账户余额。"))
        self.update_card.retranslate_ui()
        self.details_card.set_title(_tr("版本信息"))
        self.details_card.set_rows(
            [
                (_tr("应用名称"), APP_DISPLAY_NAME, ""),
                (
                    _tr("版本"),
                    f"v{__version__}",
                    f"{self._short_commit(self._build_info.commit_sha)} · "
                    f"{'dirty' if self._build_info.dirty else 'clean'}",
                ),
                (_tr("运行方式"), _tr("二进制发布") if self._binary_update_supported else _tr("源码运行"), ""),
                (_tr("作者"), APP_AUTHOR, "", APP_AUTHOR_URL),
                ("Python", sys.version.split()[0], ""),
                ("Qt", qVersion(), ""),
                (_tr("许可证"), APP_LICENSE_NAME, ""),
            ]
        )
        self.notes_card.set_title(_tr("项目"))
        self.notes_card.set_rows(
            [
                (_tr("仓库地址"), "GitHub Repository", "", APP_REPOSITORY_URL),
                (_tr("数据来源"), "OpenRouter API Reference", "", APP_DATA_SOURCE_URL),
            ]
        )
        self._refresh_update_card_state()

    def _start_update_check_state(self) -> None:
        self.update_card.set_state(
            _tr("正在检查更新"),
            _tr("正在查询 GitHub Release 中的最新已发布版本。"),
            _tr("仅检查正式 Release，不包含 draft 或 prerelease。"),
        )
        self._refresh_update_card_state = self._start_update_check_state

    def _show_update_available_state(
        self,
        *,
        current_version: str,
        release_version: str,
        asset_note: str,
        published_at: str,
        replace_note: str,
        can_replace: bool,
    ) -> None:
        self.update_card.set_state(
            _tr("发现新版本 v{version}").format(version=release_version),
            _tr("当前版本 v{current_version}，最新版本 v{release_version}。").format(
                current_version=current_version,
                release_version=release_version,
            ),
            _tr("{asset_note}  发布时间：{published_at}{replace_note}").format(
                asset_note=asset_note,
                published_at=published_at,
                replace_note=replace_note,
            ),
            can_open_release=True,
            can_replace=can_replace,
        )
        self._refresh_update_card_state = lambda: self._show_update_available_state(
            current_version=current_version,
            release_version=release_version,
            asset_note=asset_note,
            published_at=published_at,
            replace_note=replace_note,
            can_replace=can_replace,
        )

    def _show_dev_build_state(
        self,
        *,
        current_version: str,
        release_version: str,
        tag_name: str,
        published_at: str,
        commit_note: str,
    ) -> None:
        self.update_card.set_state(
            _tr("当前是非 Release 的开发版本"),
            _tr("当前构建与最新 Release 不完全一致。版本：v{current_version}，最新 Release：v{release_version}。").format(
                current_version=current_version,
                release_version=release_version,
            ),
            _tr("最新公开标签：{tag_name}  发布时间：{published_at}{commit_note}").format(
                tag_name=tag_name,
                published_at=published_at,
                commit_note=commit_note,
            ),
            can_open_release=True,
            can_replace=False,
        )
        self._refresh_update_card_state = lambda: self._show_dev_build_state(
            current_version=current_version,
            release_version=release_version,
            tag_name=tag_name,
            published_at=published_at,
            commit_note=commit_note,
        )

    def _show_latest_state(self, *, current_version: str, tag_name: str, published_at: str) -> None:
        self.update_card.set_state(
            _tr("当前已是最新版本"),
            _tr("当前版本 v{current_version} 已与最新 Release 保持一致。").format(
                current_version=current_version
            ),
            _tr("最新标签：{tag_name}  发布时间：{published_at}").format(
                tag_name=tag_name,
                published_at=published_at,
            ),
            can_open_release=True,
            can_replace=False,
        )
        self._refresh_update_card_state = lambda: self._show_latest_state(
            current_version=current_version,
            tag_name=tag_name,
            published_at=published_at,
        )

    def _show_update_failure_state(self, message: str) -> None:
        self.update_card.set_state(
            _tr("检查更新失败"),
            message,
            _tr("请稍后重试，或手动打开 GitHub Release 页面查看。"),
            can_open_release=True,
            can_replace=False,
        )
        self._refresh_update_card_state = lambda: self._show_update_failure_state(message)

    def _show_downloading_state(self, *, name: str, meta: str, note: str | None = None) -> None:
        note_text = note or _tr("正在下载 {name}。").format(name=name)
        self.update_card.set_state(
            _tr("正在下载更新"),
            note_text,
            meta,
            can_open_release=False,
            can_replace=False,
        )
        self._refresh_update_card_state = lambda: self._show_downloading_state(
            name=name,
            meta=meta,
            note=note_text,
        )

    def _show_downloaded_state(self, *, filename: str) -> None:
        self.update_card.set_state(
            _tr("更新已下载完成"),
            _tr("正在退出当前程序并应用新版本。"),
            _tr("目标文件：{filename}  程序将自动重新启动。").format(filename=filename),
            can_open_release=False,
            can_replace=False,
        )
        self._refresh_update_card_state = lambda: self._show_downloaded_state(filename=filename)

    def _show_download_failed_state(self, message: str) -> None:
        self.update_card.set_state(
            _tr("下载更新失败"),
            message,
            _tr("你仍然可以打开 Release 页面手动下载。"),
            can_open_release=True,
            can_replace=self._binary_update_supported and self._latest_asset is not None,
        )
        self._refresh_update_card_state = lambda: self._show_download_failed_state(message)

    def _check_updates(self) -> None:
        self._startup_silent_check = False
        self._start_update_check()

    def check_updates_silently(self) -> None:
        self._startup_silent_check = True
        self._start_update_check()

    def _start_update_check(self) -> None:
        if self._update_worker and self._update_worker.isRunning():
            return

        self.update_card.check_button.setEnabled(False)
        self.update_card.release_button.setEnabled(False)
        self.update_card.replace_button.setEnabled(False)
        if not self._startup_silent_check:
            self.update_card.set_state(
                _tr("正在检查更新"),
                _tr("正在查询 GitHub Release 中的最新已发布版本。"),
                _tr("仅检查正式 Release，不包含 draft 或 prerelease。"),
            )
            self._refresh_update_card_state = self._start_update_check_state
        self._update_worker = UpdateCheckWorker(self._release_checker, self)
        self._update_worker.succeeded.connect(self._handle_update_success)
        self._update_worker.failed.connect(self._handle_update_failure)
        self._update_worker.finished.connect(self._handle_update_finished)
        self._update_worker.start()

    def _handle_update_success(self, result: object) -> None:
        if not isinstance(result, UpdateCheckResult):
            self._handle_update_failure(_tr("检查更新失败：返回结果不符合预期"))
            return

        release = result.latest_release
        self._release_url = release.html_url
        self._latest_asset = release.asset
        asset_note = (
            _tr("下载文件：{name}").format(name=release.asset.name)
            if release.asset is not None
            else _tr("该 Release 未找到匹配的二进制资产，将打开发布页面。")
        )
        can_replace = bool(result.update_available and self._binary_update_supported and release.asset is not None)
        replace_note = ""
        if can_replace and self._binary_updater is not None:
            supported, reason = self._binary_updater.can_replace_current_binary()
            can_replace = supported
            if reason:
                replace_note = f"  {reason}"
        if result.update_available:
            self._show_update_available_state(
                current_version=result.current_version,
                release_version=release.version,
                asset_note=asset_note,
                published_at=self._format_release_time(release.published_at),
                replace_note=replace_note,
                can_replace=can_replace,
            )
            if self._startup_silent_check:
                InfoBar.info(
                    title=_tr("发现新版本"),
                    content=_tr("检测到 v{release.version} 可用，可在关于页查看并更新。").format(
                        release=release
                    ),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=5000,
                    parent=self.window(),
                )
            return

        is_dev_build = (
            result.version_comparison < 0
            or self._build_info.dirty
            or (
                bool(release.commit_sha)
                and self._build_info.commit_sha != "unknown"
                and self._build_info.commit_sha != release.commit_sha
            )
        )
        if is_dev_build:
            commit_note = ""
            if release.commit_sha:
                commit_note = (
                    _tr("  当前 Commit：{current_commit}  Release Commit：{release_commit}").format(
                        current_commit=self._short_commit(self._build_info.commit_sha),
                        release_commit=self._short_commit(release.commit_sha),
                    )
                )
            self._latest_asset = None
            self._show_dev_build_state(
                current_version=result.current_version,
                release_version=release.version,
                tag_name=release.tag_name,
                published_at=self._format_release_time(release.published_at),
                commit_note=commit_note,
            )
            if self._startup_silent_check:
                InfoBar.info(
                    title=_tr("当前是开发版本"),
                    content=_tr("当前构建与最新 Release 不完全一致，可在关于页查看详情。"),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=5000,
                    parent=self.window(),
                )
            return

        self._latest_asset = None
        self._show_latest_state(
            current_version=result.current_version,
            tag_name=release.tag_name,
            published_at=self._format_release_time(release.published_at),
        )

    def _handle_update_failure(self, message: str) -> None:
        self._latest_asset = None
        if self._startup_silent_check:
            InfoBar.warning(
                title=_tr("自动检查更新失败"),
                content=message,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=5000,
                parent=self.window(),
            )
        else:
            self._show_update_failure_state(message)
            show_error_bar(self.window(), _tr("检查更新失败"), message)

    def _handle_update_finished(self) -> None:
        self.update_card.check_button.setEnabled(True)
        self.update_card.release_button.setEnabled(True)
        self._update_worker = None
        self._startup_silent_check = False

    def _open_release_page(self) -> None:
        if not self._release_url:
            return
        QDesktopServices.openUrl(QUrl(self._release_url))

    def _replace_current_binary(self) -> None:
        if not self._binary_update_supported or self._binary_updater is None:
            self._handle_update_failure(_tr("当前运行方式不支持直接替换二进制文件"))
            return
        if self._latest_asset is None:
            self._handle_update_failure(_tr("当前未找到可替换的二进制更新文件"))
            return

        supported, reason = self._binary_updater.can_replace_current_binary()
        if not supported:
            self._handle_update_failure(reason or _tr("当前环境不支持替换二进制文件"))
            return

        box = MessageBox(
            _tr("下载并替换当前二进制"),
            _tr("将下载最新二进制文件，并在你关闭当前程序后替换当前可执行文件。\n下载完成后会自动退出当前程序，替换完成后自动重新启动。是否继续？"),
            self.window(),
        )
        box.yesButton.setText(_tr("继续"))
        box.cancelButton.setText(_tr("取消"))
        if not box.exec():
            return

        try:
            self.update_card.check_button.setEnabled(False)
            self.update_card.release_button.setEnabled(False)
            self.update_card.replace_button.setEnabled(False)
            self._show_downloading_state(
                name=self._latest_asset.name,
                meta=_tr("下载完成后将自动退出当前程序，替换二进制并重新启动。"),
            )
            self._install_worker = UpdateInstallWorker(
                self._binary_updater,
                self._latest_asset,
                os.getpid(),
                self,
            )
            self._install_worker.progress_changed.connect(self._handle_install_progress)
            self._install_worker.succeeded.connect(self._handle_install_success)
            self._install_worker.failed.connect(self._handle_install_failure)
            self._install_worker.finished.connect(self._handle_install_finished)
            self._install_worker.start()
        except UpdateInstallError as exc:
            self._handle_update_failure(str(exc))
            return

    def _handle_install_progress(self, received: int, total: int) -> None:
        if total > 0:
            percent = int(received * 100 / total)
            meta = _tr("已下载 {received} / {total} ({percent}%)").format(
                received=self._format_bytes(received),
                total=self._format_bytes(total),
                percent=percent,
            )
        else:
            meta = _tr("已下载 {received}").format(received=self._format_bytes(received))
        self._show_downloading_state(
            name="",
            note=_tr("下载完成后将自动退出当前程序，替换二进制并重新启动。"),
            meta=meta,
        )

    def _handle_install_success(self) -> None:
        self._show_downloaded_state(
            filename=os.path.basename(sys.executable),
        )
        QTimer.singleShot(300, QApplication.instance().quit)

    def _handle_install_failure(self, message: str) -> None:
        self._show_download_failed_state(message)
        show_error_bar(self.window(), _tr("下载更新失败"), message)

    def _handle_install_finished(self) -> None:
        self._install_worker = None
        if QApplication.instance() is None:
            return
        if self._install_worker is None:
            self.update_card.check_button.setEnabled(True)
            self.update_card.release_button.setEnabled(True)

    def _format_bytes(self, value: int) -> str:
        units = ["B", "KB", "MB", "GB"]
        size = float(value)
        unit = units[0]
        for unit in units:
            if size < 1024 or unit == units[-1]:
                break
            size /= 1024
        return f"{size:.1f} {unit}"

    def _short_commit(self, commit_sha: str) -> str:
        stripped = commit_sha.strip()
        if not stripped or stripped == "unknown":
            return "unknown"
        return stripped[:8]

    def _format_release_time(self, value: str) -> str:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().strftime(
                DISPLAY_DATETIME_FORMAT
            )
        except ValueError:
            return value or "-"

    def _parse_repo(self, url: str) -> tuple[str, str]:
        parsed = urlparse(url)
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        if len(parts) >= 2:
            return parts[0], parts[1]
        return "SunAnICB", "open-router-key-viewer"

    def stop_workers(self) -> None:
        stop_thread(self._update_worker)
        stop_thread(self._install_worker)


class MainWindow(FluentWindow):
    def __init__(self) -> None:
        super().__init__()
        self.config_store = ConfigStore()
        self._floating_window_supported = self._is_x11_platform()
        self._indicator_available = self._check_indicator_available()
        self._alert_state = {"key-info": "normal", "credits": "normal"}
        self._tray_icon: QSystemTrayIcon | None = None
        self._sni_tray: SNITray | None = None  # type: ignore[assignment]
        self._panel_label_timer: QTimer | None = None
        self._panel_label_phase = 0
        self._floating_key_value = "-"
        self._floating_key_time = "-"
        self._floating_credits_value = "-"
        self._floating_credits_time = "-"
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
        self.cache_page = CachePage(
            self.config_store,
            self.refresh_cache_views,
            self.apply_language,
            self.show_floating_window,
            self._floating_window_supported,
            self._indicator_available,
            self,
        )
        self.about_page = AboutPage(self)
        self.floating_window: FloatingWindow | None = None
        if self._floating_window_supported:
            self.floating_window = self._create_floating_window(topmost=True)
        self.key_nav_item = self.addSubInterface(
            self.key_info_page, FluentIcon.CERTIFICATE, _tr("Key 配额")
        )
        self.credits_nav_item = self.addSubInterface(
            self.credits_page, FluentIcon.PIE_SINGLE, _tr("账户余额")
        )
        self.cache_nav_item = self.addSubInterface(self.cache_page, FluentIcon.SETTING, _tr("配置"))
        self.about_nav_item = self.addSubInterface(self.about_page, FluentIcon.INFO, _tr("关于"))
        self.navigationInterface.setReturnButtonVisible(False)
        self.setWindowTitle(APP_DISPLAY_NAME)
        self._apply_initial_geometry()
        self._setup_indicator()
        if self.floating_window is not None:
            self._sync_floating_window()
        QTimer.singleShot(0, self._run_startup_queries)

    def _is_x11_platform(self) -> bool:
        return "xcb" in (QGuiApplication.platformName() or "").lower()

    @staticmethod
    def _check_indicator_available() -> bool:
        if SNITray is None:
            return False
        try:
            from PySide6.QtDBus import QDBusConnection, QDBusInterface
            bus = QDBusConnection.sessionBus()
            if not bus.isConnected():
                return False
            watcher = QDBusInterface(
                "org.kde.StatusNotifierWatcher",
                "/StatusNotifierWatcher",
                "org.kde.StatusNotifierWatcher",
                bus,
            )
            return watcher.isValid()
        except Exception:
            return False

    def _setup_indicator(self) -> None:
        payload = self.config_store.load() or {}
        if (
            self._indicator_available
            and bool(payload.get("panel_indicator_enabled"))
        ):
            sni = SNITray(
                activate=self.show_full_window,
                refresh=self.refresh_floating_metrics,
                show_window=self.show_full_window,
                quit=lambda: QApplication.instance().quit(),
            )
            if sni.register():
                self._sni_tray = sni
                self._start_panel_label_rotation()
                self._set_window_icon()
                return
        self._setup_tray_icon()

    def _set_window_icon(self) -> None:
        icon = self._load_app_icon()
        if icon.isNull():
            icon = QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.setWindowIcon(icon)
        QApplication.instance().setWindowIcon(icon)

    def _start_panel_label_rotation(self) -> None:
        self._panel_label_timer = QTimer(self)
        self._panel_label_timer.timeout.connect(self._rotate_panel_label)
        self._panel_label_timer.start(4000)
        self._sync_panel_label()

    def _rotate_panel_label(self) -> None:
        self._panel_label_phase = 1 - self._panel_label_phase
        self._sync_panel_label()

    def _sync_panel_label(self) -> None:
        if self._sni_tray is None or not self._sni_tray.is_active:
            return
        if self._panel_label_phase == 0:
            text = f"{_tr('配额')} {self._floating_key_value}"
        else:
            text = f"{_tr('余额')} {self._floating_credits_value}"
        self._sni_tray.set_label(text, f"{_tr('余额')} $99.9999")

    def apply_language(self, language_code: str) -> None:
        app = QApplication.instance()
        if app is None:
            return
        install_language(app, language_code)
        self.retranslate_ui()
        InfoBar.success(
            title=_tr("已保存"),
            content=_tr("界面语言已更新"),
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2500,
            parent=self,
        )

    def retranslate_ui(self) -> None:
        self.key_nav_item.setText(_tr("Key 配额"))
        self.credits_nav_item.setText(_tr("账户余额"))
        self.cache_nav_item.setText(_tr("配置"))
        self.about_nav_item.setText(_tr("关于"))
        self.key_info_page.retranslate_ui()
        self.credits_page.retranslate_ui()
        self.cache_page.retranslate_ui()
        self.about_page.retranslate_ui()
        if self.floating_window is not None:
            self.floating_window.retranslate_ui()
        self._sync_floating_window()
        self._sync_panel_label()

    def _apply_indicator_settings(self) -> None:
        payload = self.config_store.load() or {}
        want_enabled = (
            self._indicator_available
            and bool(payload.get("panel_indicator_enabled"))
        )

        if self._sni_tray is None or not self._sni_tray.is_active:
            if want_enabled:
                sni = SNITray(
                    activate=self.show_full_window,
                    refresh=self.refresh_floating_metrics,
                    show_window=self.show_full_window,
                    quit=lambda: QApplication.instance().quit(),
                )
                if sni.register():
                    self._sni_tray = sni
                    self._start_panel_label_rotation()
                    if self._tray_icon is not None:
                        self._tray_icon.hide()
                        self._tray_icon = None
            return

        if want_enabled:
            self._sni_tray.show()
            if self._panel_label_timer is None:
                self._start_panel_label_rotation()
        else:
            self._sni_tray.hide()
            if self._panel_label_timer is not None:
                self._panel_label_timer.stop()
                self._panel_label_timer.deleteLater()
                self._panel_label_timer = None

    def refresh_cache_views(self) -> None:
        self.key_info_page.load_cached_secret()
        self.credits_page.load_cached_secret()
        self.cache_page.refresh_view()
        self._apply_polling_settings()
        self._apply_indicator_settings()

    def _apply_initial_geometry(self) -> None:
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(960, 640)
            return

        available = screen.availableGeometry()
        width = max(800, int(available.width() * 0.8))
        height = max(560, int(available.height() * 0.8))
        width = min(width, available.width())
        height = min(height, available.height())
        self.resize(width, height)

        x = available.x() + (available.width() - width) // 2
        y = available.y() + (available.height() - height) // 2
        self.move(x, y)

    def _run_startup_queries(self) -> None:
        payload = self.config_store.load() or {}
        if payload.get("auto_check_updates", True):
            self.about_page.check_updates_silently()
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

    def refresh_floating_metrics(self) -> None:
        self.key_info_page.run_query_if_possible()
        self.credits_page.run_query_if_possible()

    def _create_floating_window(self, topmost: bool) -> FloatingWindow:
        window = FloatingWindow()
        window.set_topmost(topmost)
        window.refresh_requested.connect(self.refresh_floating_metrics)
        window.full_window_requested.connect(self.show_full_window)
        window.topmost_changed.connect(self._schedule_floating_window_rebuild)
        window.closed.connect(self.show_full_window)
        return window

    def _schedule_floating_window_rebuild(self, topmost: bool) -> None:
        QTimer.singleShot(0, lambda value=topmost: self._rebuild_floating_window(value))

    def _rebuild_floating_window(self, topmost: bool) -> None:
        if self.floating_window is None:
            return

        old_window = self.floating_window
        was_visible = old_window.isVisible()
        geometry = old_window.geometry()

        new_window = self._create_floating_window(topmost=topmost)
        self.floating_window = new_window
        self._sync_floating_window()
        new_window.setGeometry(geometry)

        old_window.blockSignals(True)
        old_window.close_for_shutdown()
        old_window.deleteLater()

        if was_visible:
            new_window.show()
            new_window.raise_()
            new_window.activateWindow()

    def show_floating_window(self) -> None:
        if self.floating_window is None:
            InfoBar.warning(
                title=_tr("当前不可用"),
                content=(
                    _tr("数据已显示在顶栏指示器中")
                    if self._sni_tray is not None and self._sni_tray.is_active
                    else _tr("悬浮小窗仅在 X11/xcb 启动时支持")
                ),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=2500,
                parent=self,
            )
            return
        self._sync_floating_window()
        center = self.frameGeometry().center()
        self.hide()
        target_x = center.x() - self.floating_window.width() // 2
        target_y = center.y() - self.floating_window.height() // 2
        self.floating_window.move(target_x, target_y)
        self.floating_window.show()
        self.floating_window.raise_()
        self.floating_window.activateWindow()

    def show_full_window(self) -> None:
        if self.floating_window is not None:
            self.floating_window.hide()
        self.show()
        self.raise_()
        self.activateWindow()

    def handle_query_success(self, mode: str, payload: dict[str, object]) -> None:
        summary = payload.get("summary", {})
        if not isinstance(summary, dict):
            return
        self._update_floating_metrics(mode, summary)
        self._evaluate_thresholds(mode, summary)

    def _update_floating_metrics(self, mode: str, summary: dict[str, object]) -> None:
        if mode == "key-info":
            value = summary.get("limit_remaining")
            self._floating_key_value = format_currency_value(value)
            self._floating_key_time = self.key_info_page.latest_success_time()
        else:
            value = summary.get("remaining_credits")
            self._floating_credits_value = format_currency_value(value)
            self._floating_credits_time = self.credits_page.latest_success_time()
        self._sync_floating_window()

    def _sync_floating_window(self) -> None:
        if self.floating_window is not None:
            self.floating_window.update_metrics(
                self._floating_key_value,
                self._floating_key_time,
                self._floating_credits_value,
                self._floating_credits_time,
            )
        self._sync_panel_label()

    def _evaluate_thresholds(self, mode: str, summary: dict[str, object]) -> None:
        payload = self.config_store.load() or {}
        if mode == "key-info":
            value = summary.get("limit_remaining")
            warning = payload.get("key_info_warning_threshold")
            critical = payload.get("key_info_critical_threshold")
            target = _tr("Key 配额")
            label = summary.get("label")
            subject = f"{target} · {label}" if isinstance(label, str) and label.strip() else target
        else:
            value = summary.get("remaining_credits")
            warning = payload.get("credits_warning_threshold")
            critical = payload.get("credits_critical_threshold")
            target = _tr("账户余额")
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
        content = _tr("{target} {level} 告警\n{subject} 当前值 {value:.4f}").format(
            target=target,
            level="Critical" if level == "critical" else "Warning",
            subject=subject,
            value=value,
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
        title = APP_DISPLAY_NAME
        content = _tr("{target} {level} 告警\n{subject} 当前值 {value:.4f}").format(
            target=target,
            level="Critical" if level == "critical" else "Warning",
            subject=subject,
            value=value,
        )

        if self._sni_tray is not None and self._sni_tray.is_active:
            urgency = "critical" if level == "critical" else "normal"
            self._sni_tray.notify(title, content, urgency)
            return

        if self._tray_icon is None or not self._tray_icon.isVisible():
            return
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
        base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
        candidates = [
            base_dir / "assets" / "open-router-key-viewer.png",
            base_dir / "assets" / "open-router-key-viewer.svg",
            Path(sys.argv[0]).resolve().parent / "assets" / "open-router-key-viewer.png",
            Path(sys.argv[0]).resolve().parent / "assets" / "open-router-key-viewer.svg",
            Path.cwd() / "assets" / "open-router-key-viewer.png",
            Path.cwd() / "assets" / "open-router-key-viewer.svg",
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
            "timestamp": datetime.now().strftime(DISPLAY_DATETIME_FORMAT),
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
        if self._panel_label_timer is not None:
            self._panel_label_timer.stop()
        self.key_info_page.stop_worker()
        self.credits_page.stop_worker()
        self.about_page.stop_workers()
        if self.floating_window is not None:
            self.floating_window.blockSignals(True)
            self.floating_window.close_for_shutdown()
        if self._sni_tray is not None:
            self._sni_tray.unregister()
        if self._tray_icon is not None:
            self._tray_icon.hide()
        super().closeEvent(event)


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    config_store = ConfigStore()
    payload = config_store.load() or {}
    install_language(app, resolve_language_code(payload.get("ui_language")))
    app.setApplicationName(APP_DISPLAY_NAME)
    app.setApplicationVersion(__version__)
    setThemeColor("#0F6CBD")

    window = MainWindow()
    window.show()
    return app.exec()
