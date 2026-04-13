from __future__ import annotations

import io
from collections.abc import Callable
from contextlib import redirect_stdout

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

with redirect_stdout(io.StringIO()):
    from qfluentwidgets import CaptionLabel, LineEdit, PushButton, StrongBodyLabel, SwitchButton

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
        layout.addWidget(self.line_edit, 1)

        self.save_button = PushButton(_tr("保存"), self)
        self.save_button.clicked.connect(self._save)
        layout.addWidget(self.save_button)

    def _save(self) -> None:
        self._on_save(self.line_edit.text().strip())

    def sync_value(self, value: object) -> None:
        self.line_edit.blockSignals(True)
        self.line_edit.setText("" if value is None else str(value))
        self.line_edit.blockSignals(False)


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


class PropertyRowsPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.rows_layout = QVBoxLayout(self)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(10)

    def set_rows(self, rows: list[tuple[str, str, str]]) -> None:
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for label, value, note in rows:
            row = QWidget(self)
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

            self.rows_layout.addWidget(row)
        self.rows_layout.addStretch(1)
