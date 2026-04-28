from __future__ import annotations

import io
from collections.abc import Callable
from contextlib import redirect_stdout

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QCloseEvent, QFont, QMouseEvent
from PySide6.QtWidgets import QApplication, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

with redirect_stdout(io.StringIO()):
    from qfluentwidgets import (
        BodyLabel,
        CaptionLabel,
        ElevatedCardWidget,
        FluentIcon,
        HyperlinkButton,
        isDarkTheme,
        PrimaryPushButton,
        ProgressBar,
        PushButton,
        StrongBodyLabel,
        TitleLabel,
        TransparentToolButton,
        InfoBar,
        InfoBarPosition,
    )

from open_router_key_viewer.i18n import tr
from open_router_key_viewer.state.app_metadata import APP_DISPLAY_NAME
from open_router_key_viewer.state.floating_metrics import RenderedMetric
from open_router_key_viewer.state.progress import ProgressState

_tr = tr


class ProgressWindow(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if parent is None:
            self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        else:
            self.setWindowFlags(Qt.WindowType.Widget)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(420, 172)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        card = ElevatedCardWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)

        self.title_label = StrongBodyLabel(APP_DISPLAY_NAME, card)
        layout.addWidget(self.title_label)

        self.message_label = BodyLabel(_tr("正在初始化应用..."), card)
        layout.addWidget(self.message_label)

        self.progress_bar = ProgressBar(card)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.detail_label = CaptionLabel("", card)
        self.detail_label.setWordWrap(True)
        layout.addWidget(self.detail_label)

        root.addWidget(card)

    def set_progress(self, state: ProgressState) -> None:
        self.progress_bar.setValue(max(0, min(100, state.percent)))
        self.message_label.setText(_tr(state.message))
        self.detail_label.setText(_tr(state.detail))

    def center_on_screen(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.move(
                (parent.width() - self.width()) // 2,
                (parent.height() - self.height()) // 2,
            )
            self.raise_()
            return

        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        geometry = screen.availableGeometry()
        self.move(
            geometry.x() + (geometry.width() - self.width()) // 2,
            geometry.y() + (geometry.height() - self.height()) // 2,
        )


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


class InstallCard(ElevatedCardWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(12)
        self.header_label = StrongBodyLabel(_tr("安装"), self)
        header.addWidget(self.header_label)
        header.addStretch(1)

        self.install_button = PrimaryPushButton(_tr("安装到目录"), self)
        header.addWidget(self.install_button)

        self.open_button = PushButton(_tr("打开目录"), self)
        self.open_button.setVisible(False)
        self.open_button.setEnabled(False)
        header.addWidget(self.open_button)

        self.remove_button = PushButton(_tr("移除安装"), self)
        self.remove_button.setVisible(False)
        self.remove_button.setEnabled(False)
        header.addWidget(self.remove_button)
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
        can_open_directory: bool = False,
        can_remove: bool = False,
        install_button_text: str | None = None,
        install_enabled: bool = True,
    ) -> None:
        self.status_label.setText(title)
        self.note_label.setText(note)
        self.meta_label.setText(meta)
        self.open_button.setVisible(can_open_directory)
        self.open_button.setEnabled(can_open_directory)
        self.remove_button.setVisible(can_remove)
        self.remove_button.setEnabled(can_remove)
        self.install_button.setEnabled(install_enabled)
        if install_button_text is not None:
            self.install_button.setText(install_button_text)

    def retranslate_ui(self) -> None:
        self.header_label.setText(_tr("安装"))
        self.install_button.setText(_tr("安装到固定位置"))
        self.open_button.setText(_tr("打开目录"))
        self.remove_button.setText(_tr("移除安装"))


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
                note_color = "rgba(255, 255, 255, 0.72)" if isDarkTheme() else "rgba(0, 0, 0, 0.62)"
                note_label.setStyleSheet(f"color: {note_color};")
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
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 12, 6)
        layout.setSpacing(8)
        self.kind = "idle"
        self._detail = ""

        self.icon_label = BodyLabel("", self)
        icon_font = QFont(self.icon_label.font())
        icon_font.setPointSize(icon_font.pointSize() + 1)
        self.icon_label.setFont(icon_font)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setFixedSize(18, 18)
        layout.addWidget(self.icon_label)

        self.title_label = BodyLabel(_tr("等待查询"), self)
        layout.addWidget(self.title_label)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.set_status("idle", _tr("等待查询"))

    def set_status(self, kind: str, title: str, detail: str = "") -> None:
        self.kind = kind
        self._detail = detail
        self.title_label.setText(title)
        styles = (
            {
                "idle": {
                    "icon": "\u2022",
                    "bg": "rgba(255, 255, 255, 0.10)",
                    "border": "rgba(255, 255, 255, 0.16)",
                    "text": "#F5F7FA",
                    "icon_bg": "rgba(255, 255, 255, 0.14)",
                },
                "loading": {
                    "icon": "\u25F4",
                    "bg": "rgba(255, 185, 0, 0.16)",
                    "border": "rgba(255, 185, 0, 0.32)",
                    "text": "#FFE3A8",
                    "icon_bg": "rgba(255, 185, 0, 0.26)",
                },
                "success": {
                    "icon": "\u2713",
                    "bg": "rgba(15, 123, 71, 0.20)",
                    "border": "rgba(15, 123, 71, 0.34)",
                    "text": "#AEE9C5",
                    "icon_bg": "rgba(15, 123, 71, 0.30)",
                },
                "error": {
                    "icon": "\u2715",
                    "bg": "rgba(196, 43, 28, 0.20)",
                    "border": "rgba(196, 43, 28, 0.34)",
                    "text": "#FFC0BA",
                    "icon_bg": "rgba(196, 43, 28, 0.30)",
                },
            }
            if isDarkTheme()
            else {
                "idle": {
                    "icon": "\u2022",
                    "bg": "#EEF4FA",
                    "border": "#D5E2F0",
                    "text": "#23415E",
                    "icon_bg": "#DCE8F4",
                },
                "loading": {
                    "icon": "\u25F4",
                    "bg": "#FFF5E0",
                    "border": "#F1D39C",
                    "text": "#6A4D00",
                    "icon_bg": "#F8E2B9",
                },
                "success": {
                    "icon": "\u2713",
                    "bg": "#E8F6EE",
                    "border": "#AED5BC",
                    "text": "#115533",
                    "icon_bg": "#CFE9DA",
                },
                "error": {
                    "icon": "\u2715",
                    "bg": "#FCECEC",
                    "border": "#E0B1B1",
                    "text": "#7A1F1F",
                    "icon_bg": "#F2D3D3",
                },
            }
        )
        style = styles.get(kind, styles["idle"])
        self.icon_label.setText(style["icon"])
        self.setStyleSheet(
            "QWidget {"
            f"background-color: {style['bg']};"
            f"border: 1px solid {style['border']};"
            "border-radius: 13px;"
            "}"
            f"QLabel {{ color: {style['text']}; background: transparent; }}"
        )
        self.icon_label.setStyleSheet(
            "QLabel {"
            f"background-color: {style['icon_bg']};"
            f"color: {style['text']};"
            "border: none;"
            "border-radius: 9px;"
            "font-weight: 700;"
            "}"
        )
        self.title_label.setStyleSheet(
            "QLabel {"
            f"color: {style['text']};"
            "font-weight: 600;"
            "border: none;"
            "background: transparent;"
            "}"
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
        self._metric_cards: dict[str, FloatingMetricCard] = {}
        self._last_metrics: list[RenderedMetric] = []
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

        self.metrics_container = QWidget(shell)
        self.metrics_layout = QVBoxLayout(self.metrics_container)
        self.metrics_layout.setContentsMargins(0, 0, 0, 0)
        self.metrics_layout.setSpacing(2)
        shell_layout.addWidget(self.metrics_container)
        root.addWidget(shell)
        self._refresh_topmost_button()

    def retranslate_ui(self) -> None:
        self.refresh_button.setText(_tr("刷新"))
        self.full_window_button.setText(_tr("主窗口"))
        self.update_metrics(self._last_metrics)
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

    def update_metrics(self, metrics: list[RenderedMetric]) -> None:
        self._last_metrics = list(metrics)
        active_ids = {metric.id for metric in metrics}
        for metric_id, card in list(self._metric_cards.items()):
            if metric_id not in active_ids:
                self.metrics_layout.removeWidget(card)
                card.deleteLater()
                del self._metric_cards[metric_id]

        for index, metric in enumerate(metrics):
            card = self._metric_cards.get(metric.id)
            if card is None:
                card = FloatingMetricCard(_tr(metric.label), self.metrics_container)
                self._metric_cards[metric.id] = card
            card.set_title(_tr(metric.label))
            card.set_content(metric.value, metric.refreshed_at)
            if self.metrics_layout.indexOf(card) != index:
                self.metrics_layout.insertWidget(index, card)

        height = 52 + max(1, len(metrics)) * 34
        self.setMinimumSize(280, height)
        self.resize(max(self.width(), 280), height)

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
