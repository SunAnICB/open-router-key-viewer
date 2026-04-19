from __future__ import annotations

from PySide6.QtWidgets import QLabel

from open_router_key_viewer.ui.pages.settings_widgets import (
    AutoQuerySettingRow,
    InputSettingRow,
    PropertyRowsPanel,
    SwitchSettingRow,
)
from open_router_key_viewer.ui.widgets import StatusBadge


def test_switch_setting_row_sync_and_callback(qapp) -> None:
    _ = qapp
    toggles: list[bool] = []
    row = SwitchSettingRow("Enabled", toggles.append)

    row.sync_state(True)
    assert row.switch.isChecked() is True
    assert row.switch.onText == "开启"
    assert row.switch.offText == "关闭"

    row._handle_toggle(False)
    assert toggles == [False]


def test_input_setting_row_save_trims_value(qapp) -> None:
    _ = qapp
    saved: list[str] = []
    row = InputSettingRow("Threshold", "5.0", saved.append)

    row.line_edit.setText("  12.5  ")
    row._save()

    assert saved == ["12.5"]


def test_auto_query_setting_row_sync_and_save(qapp) -> None:
    _ = qapp
    startup: list[bool] = []
    polling: list[bool] = []
    intervals: list[str] = []
    row = AutoQuerySettingRow(
        "Quota",
        "300",
        startup.append,
        polling.append,
        intervals.append,
    )

    row.sync_state(True, False, 120)
    assert row.auto_switch.isChecked() is True
    assert row.poll_switch.isChecked() is False
    assert row.interval_input.text() == "120"

    row.auto_switch.checkedChanged.emit(False)
    row.poll_switch.checkedChanged.emit(True)
    row.interval_input.setText(" 600 ")
    row._save_interval()

    assert startup == [False]
    assert polling == [True]
    assert intervals == ["600"]


def test_property_rows_panel_replaces_existing_rows(qapp) -> None:
    _ = qapp
    panel = PropertyRowsPanel()

    panel.set_rows([("Key", "Value", "Note")])
    first_labels = [widget.text() for widget in panel.findChildren(QLabel) if widget.text()]
    assert "Key" in first_labels
    assert "Value" in first_labels
    assert "Note" in first_labels

    panel.set_rows([("Another", "Entry", "")])
    updated_labels = [widget.text() for widget in panel.findChildren(QLabel) if widget.text()]
    assert "Another" in updated_labels
    assert "Entry" in updated_labels


def test_status_badge_updates_visual_state(qapp) -> None:
    _ = qapp
    badge = StatusBadge()

    badge.set_status("success", "查询成功")
    assert badge.title_label.text() == "查询成功"
    assert badge.icon_label.text() == "\u2713"
    assert "border-radius: 13px" in badge.styleSheet()

    badge.set_status("error", "查询失败")
    assert badge.title_label.text() == "查询失败"
    assert badge.icon_label.text() == "\u2715"
