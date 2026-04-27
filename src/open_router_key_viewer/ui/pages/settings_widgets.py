from __future__ import annotations

import io
from collections.abc import Callable
from contextlib import redirect_stdout

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QTreeView, QVBoxLayout, QWidget

with redirect_stdout(io.StringIO()):
    from qfluentwidgets import (
        CaptionLabel,
        LineEdit,
        StrongBodyLabel,
        SwitchButton,
        isDarkTheme,
    )

from open_router_key_viewer.i18n import tr

_tr = tr


class SwitchSettingRow(QWidget):
    def __init__(self, text: str, on_toggle: Callable[[bool], None], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._on_toggle = on_toggle
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.label = StrongBodyLabel(text, self)
        layout.addWidget(self.label)
        layout.addStretch(1)

        self.switch = SwitchButton(self)
        self.switch.checkedChanged.connect(self._handle_toggle)
        layout.addWidget(self.switch)
        self.sync_state(False)

    def _handle_toggle(self, checked: bool) -> None:
        self._on_toggle(checked)

    def sync_state(self, checked: bool) -> None:
        self.switch.blockSignals(True)
        self.switch.setChecked(checked)
        self.switch.blockSignals(False)
        self.switch.setOnText(_tr("开启"))
        self.switch.setOffText(_tr("关闭"))

    def retranslate_ui(self, text: str) -> None:
        self.label.setText(text)
        self.switch.setOnText(_tr("开启"))
        self.switch.setOffText(_tr("关闭"))


class InputSettingRow(QWidget):
    def __init__(
        self,
        text: str,
        placeholder: str,
        on_save: Callable[[str], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._placeholder = placeholder
        self._on_save = on_save
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.label = StrongBodyLabel(text, self)
        self.label.setMinimumWidth(220)
        layout.addWidget(self.label)

        self.line_edit = LineEdit(self)
        self.line_edit.setPlaceholderText(placeholder)
        self.line_edit.editingFinished.connect(self._save)
        layout.addWidget(self.line_edit, 1)

    def _save(self) -> None:
        self._on_save(self.line_edit.text().strip())

    def sync_value(self, value: object) -> None:
        self.line_edit.blockSignals(True)
        self.line_edit.setText("" if value is None else str(value))
        self.line_edit.blockSignals(False)

    def retranslate_ui(self, text: str, placeholder: str) -> None:
        self._placeholder = placeholder
        self.label.setText(text)
        self.line_edit.setPlaceholderText(placeholder)


class AutoQuerySettingRow(QWidget):
    def __init__(
        self,
        title: str,
        placeholder: str,
        on_toggle_startup: Callable[[bool], None],
        on_toggle_polling: Callable[[bool], None],
        on_save_interval: Callable[[str], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._placeholder = placeholder
        self._on_save_interval = on_save_interval
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.title_label = StrongBodyLabel(title, self)
        self.title_label.setMinimumWidth(96)
        layout.addWidget(self.title_label)

        self.auto_label = CaptionLabel(_tr("启动时查询"), self)
        layout.addWidget(self.auto_label)

        self.auto_switch = SwitchButton(self)
        self.auto_switch.checkedChanged.connect(on_toggle_startup)
        layout.addWidget(self.auto_switch)

        self.poll_label = CaptionLabel(_tr("定时查询"), self)
        layout.addWidget(self.poll_label)

        self.poll_switch = SwitchButton(self)
        self.poll_switch.checkedChanged.connect(on_toggle_polling)
        layout.addWidget(self.poll_switch)

        self.interval_label = CaptionLabel(_tr("查询间隔（秒）"), self)
        layout.addWidget(self.interval_label)

        self.interval_input = LineEdit(self)
        self.interval_input.setPlaceholderText(placeholder)
        self.interval_input.setFixedWidth(120)
        self.interval_input.editingFinished.connect(self._save_interval)
        layout.addWidget(self.interval_input)
        layout.addStretch(1)
        self.sync_state(False, False, placeholder)

    def _save_interval(self) -> None:
        self._on_save_interval(self.interval_input.text().strip())

    def sync_state(self, auto_checked: bool, poll_checked: bool, interval_value: object) -> None:
        for button, checked in ((self.auto_switch, auto_checked), (self.poll_switch, poll_checked)):
            button.blockSignals(True)
            button.setChecked(checked)
            button.blockSignals(False)
            button.setOnText(_tr("开启"))
            button.setOffText(_tr("关闭"))

        self.interval_input.blockSignals(True)
        self.interval_input.setText("" if interval_value is None else str(interval_value))
        self.interval_input.blockSignals(False)

    def retranslate_ui(self, title: str, placeholder: str) -> None:
        self._placeholder = placeholder
        self.title_label.setText(title)
        self.auto_label.setText(_tr("启动时查询"))
        self.poll_label.setText(_tr("定时查询"))
        self.interval_label.setText(_tr("查询间隔（秒）"))
        self.interval_input.setPlaceholderText(placeholder)
        self.auto_switch.setOnText(_tr("开启"))
        self.auto_switch.setOffText(_tr("关闭"))
        self.poll_switch.setOnText(_tr("开启"))
        self.poll_switch.setOffText(_tr("关闭"))


class PropertyRowsPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

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
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        self._apply_view_style()
        layout.addWidget(self.view)

    def set_rows(self, rows: list[tuple[str, str, str]]) -> None:
        self._apply_view_style()
        self.model.removeRows(0, self.model.rowCount())
        label_color = QColor("#C7D0DC") if isDarkTheme() else QColor("#667085")
        value_color = QColor("#F5F7FA") if isDarkTheme() else QColor("#111827")
        note_color = QColor("#B8C0CC") if isDarkTheme() else QColor("#6B7280")
        has_note = any(bool(note) for _, _, note in rows)

        for label, value, note in rows:
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

        self.view.setColumnHidden(2, not has_note)
        self.view.expandAll()
        self._fit_view_height()

    def _fit_view_height(self) -> None:
        row_count = self.model.rowCount()
        if row_count <= 0:
            self.view.setFixedHeight(48)
            return
        row_height = self.view.sizeHintForRow(0)
        if row_height <= 0:
            row_height = 44
        self.view.setFixedHeight(row_count * row_height + 14)

    def _apply_view_style(self) -> None:
        if isDarkTheme():
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
