from __future__ import annotations

import io
from contextlib import redirect_stdout

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QSizePolicy,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

with redirect_stdout(io.StringIO()):
    from qfluentwidgets import (
        CaptionLabel,
        ElevatedCardWidget,
        FluentIcon,
        PasswordLineEdit,
        PrimaryPushButton,
        PushButton,
        SegmentedWidget,
        StrongBodyLabel,
        TextEdit,
        isDarkTheme,
    )

from open_router_key_viewer.i18n import tr
from open_router_key_viewer.ui.widgets import ResultCard, StatusBadge

_tr = tr


class SecretInputCard(ElevatedCardWidget):
    def __init__(self, input_label: str, placeholder: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(12)
        self.input_label_widget = StrongBodyLabel(input_label, self)
        self.input_label_widget.setMinimumWidth(210)
        row.addWidget(self.input_label_widget)

        self.secret_input = PasswordLineEdit(self)
        self.secret_input.setPlaceholderText(placeholder)
        row.addWidget(self.secret_input, 1)

        self.paste_button = PushButton(_tr("粘贴"), self)
        self.paste_button.setIcon(FluentIcon.PASTE)
        row.addWidget(self.paste_button)

        self.copy_button = PushButton(_tr("复制"), self)
        self.copy_button.setIcon(FluentIcon.COPY)
        row.addWidget(self.copy_button)

        self.save_button = PushButton(_tr("保存缓存"), self)
        self.save_button.setIcon(FluentIcon.SAVE)
        row.addWidget(self.save_button)

        self.clear_saved_button = PushButton(_tr("删除缓存"), self)
        self.clear_saved_button.setIcon(FluentIcon.DELETE)
        row.addWidget(self.clear_saved_button)
        layout.addLayout(row)

    def retranslate_ui(self, input_label: str, placeholder: str) -> None:
        self.input_label_widget.setText(input_label)
        self.secret_input.setPlaceholderText(placeholder)
        self.paste_button.setText(_tr("粘贴"))
        self.copy_button.setText(_tr("复制"))
        self.save_button.setText(_tr("保存缓存"))
        self.clear_saved_button.setText(_tr("删除缓存"))

    def set_busy(self, busy: bool) -> None:
        self.secret_input.setEnabled(not busy)
        self.paste_button.setEnabled(not busy)
        self.copy_button.setEnabled(not busy)
        self.save_button.setEnabled(not busy)
        self.clear_saved_button.setEnabled(not busy)


class QueryDetailPanel(ElevatedCardWidget):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._style_dark: bool | None = None
        self._rows: tuple[tuple[str, str, str], ...] = ()
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(10)

        self.title_label = StrongBodyLabel(title, self)
        layout.addWidget(self.title_label)

        self.view = QTreeView(self)
        self.view.setRootIsDecorated(False)
        self.view.setItemsExpandable(False)
        self.view.setAllColumnsShowFocus(False)
        self.view.setUniformRowHeights(True)
        self.view.setIndentation(0)
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.view.setHeaderHidden(True)
        self.view.setAlternatingRowColors(True)
        self.view.setWordWrap(True)
        self.view.setTextElideMode(Qt.TextElideMode.ElideNone)

        self.model = QStandardItemModel(0, 3, self)
        self.view.setModel(self.model)

        header = self.view.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        self._apply_view_style(force=True)
        layout.addWidget(self.view)

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)

    def set_rows(self, rows: list[tuple[str, str, str]]) -> None:
        next_rows = tuple(rows)
        style_changed = self._apply_view_style()
        if next_rows == self._rows and not style_changed:
            return

        self._rows = next_rows
        self.model.removeRows(0, self.model.rowCount())
        label_color = QColor("#C7D0DC") if isDarkTheme() else QColor("#667085")
        value_color = QColor("#F5F7FA") if isDarkTheme() else QColor("#111827")
        note_color = QColor("#B8C0CC") if isDarkTheme() else QColor("#6B7280")

        for label, value, note in next_rows:
            label_item = QStandardItem(label)
            value_item = QStandardItem(value)
            note_item = QStandardItem(note)
            for item in (label_item, value_item, note_item):
                item.setEditable(False)
                item.setSelectable(False)
            label_item.setForeground(label_color)
            value_item.setForeground(value_color)
            note_item.setForeground(note_color)
            self.model.appendRow([label_item, value_item, note_item])

        self.view.expandAll()
        self._fit_view_height()

    def _fit_view_height(self) -> None:
        self.setMaximumHeight(16777215)
        row_count = self.model.rowCount()
        if row_count <= 0:
            self.view.setFixedHeight(48)
            self.setMaximumHeight(self.sizeHint().height())
            return
        row_height = self.view.sizeHintForRow(0)
        if row_height <= 0:
            row_height = 44
        self.view.setFixedHeight(row_count * row_height + 14)
        self.setMaximumHeight(self.sizeHint().height())

    def _apply_view_style(self, *, force: bool = False) -> bool:
        dark = isDarkTheme()
        if not force and dark == self._style_dark:
            return False
        self._style_dark = dark
        if dark:
            border = "rgba(255, 255, 255, 0.08)"
            row_bg = "rgba(255, 255, 255, 0.03)"
            alt_bg = "rgba(255, 255, 255, 0.06)"
            hover_bg = "rgba(255, 255, 255, 0.08)"
        else:
            border = "rgba(15, 23, 42, 0.08)"
            row_bg = "rgba(255, 255, 255, 0.78)"
            alt_bg = "rgba(15, 108, 189, 0.05)"
            hover_bg = "rgba(15, 108, 189, 0.08)"

        self.view.setStyleSheet(
            f"""
            QTreeView {{
                background: transparent;
                alternate-background-color: {alt_bg};
                border: 1px solid {border};
                border-radius: 12px;
                padding: 4px 0;
            }}
            QTreeView::item {{
                background: {row_bg};
                border: none;
                border-bottom: 1px solid {border};
                padding: 10px 12px;
            }}
            QTreeView::item:hover {{
                background: {hover_bg};
            }}
            """
        )
        return True


class QueryResultCard(ElevatedCardWidget):
    def __init__(
        self,
        button_text: str,
        button_icon: FluentIcon,
        on_show_summary,
        on_show_raw,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(24, 22, 24, 22)
        self.layout_.setSpacing(16)

        header_widget = QWidget(self)
        header_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        header = QHBoxLayout(header_widget)
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(12)

        self.query_button = PrimaryPushButton(button_text, self)
        self.query_button.setIcon(button_icon)
        self.query_button.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        header.addWidget(self.query_button)

        self.status_badge = StatusBadge(self)
        header.addWidget(self.status_badge)
        header.addStretch(1)

        self.time_label = CaptionLabel(_tr("最近成功: -"), self)
        self.time_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        header.addWidget(self.time_label)

        self.result_mode_switch = SegmentedWidget(self)
        self.result_mode_switch.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.result_mode_switch.addItem("summary", _tr("结果卡片"), on_show_summary)
        self.result_mode_switch.addItem("raw", _tr("原始请求"), on_show_raw)
        header.addWidget(self.result_mode_switch)
        self.layout_.addWidget(header_widget)

        self.summary_container = QWidget(self)
        self.summary_container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        summary_layout = QVBoxLayout(self.summary_container)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(12)
        self.hero_card = ResultCard(self.summary_container)
        self.hero_card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.detail_card = QueryDetailPanel(_tr("详细信息"), self.summary_container)
        summary_layout.addWidget(self.hero_card)
        summary_layout.addWidget(self.detail_card)
        self.layout_.addWidget(self.summary_container)

        self.result_output = TextEdit(self)
        self.result_output.setReadOnly(True)
        self.result_output.setFixedHeight(420)
        mono = QFont("JetBrains Mono")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.result_output.setFont(mono)
        self.layout_.addWidget(self.result_output)

    def retranslate_ui(self, button_text: str) -> None:
        self.query_button.setText(button_text)
        self.detail_card.set_title(_tr("详细信息"))
        self.result_mode_switch.setItemText("summary", _tr("结果卡片"))
        self.result_mode_switch.setItemText("raw", _tr("原始请求"))
        self.status_badge.retranslate_ui()

    def set_busy(self, busy: bool) -> None:
        self.query_button.setEnabled(not busy)

    def show_mode(self, mode: str) -> None:
        showing_summary = mode == "summary"
        self.summary_container.setVisible(showing_summary)
        self.result_output.setVisible(not showing_summary)
        self.result_mode_switch.setCurrentItem(mode)
