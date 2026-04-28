from __future__ import annotations

import io
from collections.abc import Callable
from contextlib import redirect_stdout

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QTreeView, QVBoxLayout, QWidget

with redirect_stdout(io.StringIO()):
    from qfluentwidgets import (
        CaptionLabel,
        FluentIcon,
        LineEdit,
        PushButton,
        StrongBodyLabel,
        SwitchButton,
        TransparentToolButton,
        isDarkTheme,
    )

from open_router_key_viewer.i18n import tr
from open_router_key_viewer.state.app_config import AppConfig
from open_router_key_viewer.state.floating_metrics import (
    METRIC_DEFINITIONS,
    METRIC_DEFINITION_BY_ID,
    MetricDefinition,
    MetricTarget,
)

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


class TargetMetricDisplayConfigPanel(QWidget):
    def __init__(
        self,
        target: MetricTarget,
        on_change: Callable[[list[str], list[str], dict[str, str], int | None], None],
        on_reset: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._target = target
        self._on_change = on_change
        self._on_reset = on_reset
        self._syncing = False
        self._saving_enabled = True
        self._order = [definition.id for definition in METRIC_DEFINITIONS]
        self._rows: dict[str, _TargetMetricDisplayRow] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(12)
        self.interval_label = CaptionLabel(_tr("顶栏切换间隔（秒）"), self)
        controls.addWidget(self.interval_label)
        self.interval_input = LineEdit(self)
        self.interval_input.setFixedWidth(120)
        self.interval_input.setPlaceholderText("4")
        self.interval_input.editingFinished.connect(self._emit_change)
        controls.addWidget(self.interval_input)
        controls.addStretch(1)
        self.reset_button = PushButton(_tr("恢复默认"), self)
        self.reset_button.setAutoDefault(False)
        self.reset_button.setDefault(False)
        self.reset_button.clicked.connect(self._on_reset)
        controls.addWidget(self.reset_button)
        layout.addLayout(controls)
        self.interval_label.setVisible(target == "panel")
        self.interval_input.setVisible(target == "panel")

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        self.metric_header = CaptionLabel(_tr("指标"), self)
        self.label_header = CaptionLabel(_tr("显示名称"), self)
        self.show_header = CaptionLabel(_tr("显示"), self)
        header.addWidget(self.metric_header, 2)
        header.addWidget(self.label_header, 3)
        header.addWidget(self.show_header)
        header.addSpacing(72)
        layout.addLayout(header)

        self.rows_layout = QVBoxLayout()
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(8)
        layout.addLayout(self.rows_layout)
        for definition in METRIC_DEFINITIONS:
            row = _TargetMetricDisplayRow(definition, target, self._emit_change, self)
            row.move_up_requested.connect(lambda metric_id=definition.id: self._move(metric_id, -1))
            row.move_down_requested.connect(lambda metric_id=definition.id: self._move(metric_id, 1))
            self._rows[definition.id] = row
            self.rows_layout.addWidget(row)

    def sync_config(self, config: AppConfig) -> None:
        self._syncing = True
        selected = config.floating_metrics if self._target == "floating" else config.panel_metrics
        order = config.floating_metric_order if self._target == "floating" else config.panel_metric_order
        self._order = self._ordered_metric_ids(order)
        self.interval_input.setText(str(config.panel_rotation_interval_seconds))
        for metric_id in self._order:
            definition = METRIC_DEFINITION_BY_ID[metric_id]
            labels = config.metric_labels.get(metric_id, {})
            row = self._rows[metric_id]
            default_label = (
                definition.default_floating_label if self._target == "floating" else definition.default_panel_label
            )
            row.sync_state(
                enabled=metric_id in selected,
                label=labels.get(self._target, default_label),
            )
        self._reorder_rows()
        self._syncing = False

    def refresh_from_config(self, config: AppConfig) -> None:
        self._saving_enabled = False
        self.sync_config(config)
        self._saving_enabled = True

    def suspend_saving(self) -> None:
        self._saving_enabled = False

    def resume_saving(self) -> None:
        self._saving_enabled = True

    def retranslate_ui(self) -> None:
        self.interval_label.setText(_tr("顶栏切换间隔（秒）"))
        self.reset_button.setText(_tr("恢复默认"))
        self.metric_header.setText(_tr("指标"))
        self.label_header.setText(_tr("显示名称"))
        self.show_header.setText(_tr("显示"))
        for row in self._rows.values():
            row.retranslate_ui()

    def deactivate(self) -> None:
        self._syncing = True
        self._saving_enabled = False

    def _ordered_metric_ids(self, metric_order: list[str]) -> list[str]:
        ordered: list[str] = []
        for metric_id in [*metric_order, *(definition.id for definition in METRIC_DEFINITIONS)]:
            if metric_id in METRIC_DEFINITION_BY_ID and metric_id not in ordered:
                ordered.append(metric_id)
        return ordered

    def _move(self, metric_id: str, offset: int) -> None:
        index = self._order.index(metric_id)
        target = index + offset
        if target < 0 or target >= len(self._order):
            return
        self._order[index], self._order[target] = self._order[target], self._order[index]
        self._reorder_rows()
        self._emit_change()

    def _reorder_rows(self) -> None:
        for index, metric_id in enumerate(self._order):
            self.rows_layout.insertWidget(index, self._rows[metric_id])
            self._rows[metric_id].set_move_enabled(index > 0, index < len(self._order) - 1)

    def _emit_change(self) -> None:
        if self._syncing or not self._saving_enabled:
            return
        selected: list[str] = []
        labels: dict[str, str] = {}
        for metric_id in self._order:
            row = self._rows[metric_id]
            if row.enabled():
                selected.append(metric_id)
            labels[metric_id] = row.label()
        interval: int | None = None
        if self._target == "panel":
            try:
                interval = int(self.interval_input.text().strip() or "4")
            except ValueError:
                interval = 4
        self._on_change(selected, list(self._order), labels, interval)


class _TargetMetricDisplayRow(QWidget):
    move_up_requested = Signal()
    move_down_requested = Signal()

    def __init__(
        self,
        definition: MetricDefinition,
        target: MetricTarget,
        on_change: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.definition = definition
        self._target = target
        self._on_change = on_change

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.title_label = StrongBodyLabel("", self)
        layout.addWidget(self.title_label, 2)

        self.label_input = LineEdit(self)
        self.label_input.editingFinished.connect(self._on_change)
        layout.addWidget(self.label_input, 3)

        self.switch = SwitchButton(self)
        self.switch.checkedChanged.connect(lambda _checked: self._on_change())
        layout.addWidget(self.switch)

        self.up_button = TransparentToolButton(self)
        self.up_button.setIcon(FluentIcon.UP)
        self.up_button.clicked.connect(self.move_up_requested.emit)
        layout.addWidget(self.up_button)

        self.down_button = TransparentToolButton(self)
        self.down_button.setIcon(FluentIcon.DOWN)
        self.down_button.clicked.connect(self.move_down_requested.emit)
        layout.addWidget(self.down_button)
        self.retranslate_ui()

    def sync_state(self, *, enabled: bool, label: str) -> None:
        self.label_input.blockSignals(True)
        self.label_input.setText(label)
        self.label_input.blockSignals(False)
        self.switch.blockSignals(True)
        self.switch.setChecked(enabled)
        self.switch.blockSignals(False)
        self.switch.setOnText(_tr("开启"))
        self.switch.setOffText(_tr("关闭"))

    def retranslate_ui(self) -> None:
        title = (
            self.definition.default_floating_label
            if self._target == "floating"
            else self.definition.default_panel_label
        )
        self.title_label.setText(_tr(title))
        self.switch.setOnText(_tr("开启"))
        self.switch.setOffText(_tr("关闭"))
        self.up_button.setToolTip(_tr("上移"))
        self.down_button.setToolTip(_tr("下移"))

    def set_move_enabled(self, up_enabled: bool, down_enabled: bool) -> None:
        self.up_button.setEnabled(up_enabled)
        self.down_button.setEnabled(down_enabled)

    def enabled(self) -> bool:
        return self.switch.isChecked()

    def label(self) -> str:
        return self.label_input.text().strip()


class PropertyRowsPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._style_dark: bool | None = None
        self._rows: tuple[tuple[str, str, str], ...] = ()
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

        self._apply_view_style(force=True)
        layout.addWidget(self.view)

    def set_rows(self, rows: list[tuple[str, str, str]]) -> None:
        style_changed = self._apply_view_style()
        next_rows = tuple(rows)
        if next_rows == self._rows and not style_changed:
            return

        self._rows = next_rows
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
