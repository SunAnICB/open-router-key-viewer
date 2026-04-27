from __future__ import annotations

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
    row.line_edit.editingFinished.emit()

    assert saved == ["12.5"]
    assert not hasattr(row, "save_button")


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
    assert panel.model.rowCount() == 1
    assert panel.model.item(0, 0).text() == "Key"
    assert panel.model.item(0, 1).text() == "Value"
    assert panel.model.item(0, 2).text() == "Note"
    assert panel.view.isColumnHidden(2) is False

    panel.set_rows([("Another", "Entry", "")])
    assert panel.model.rowCount() == 1
    assert panel.model.item(0, 0).text() == "Another"
    assert panel.model.item(0, 1).text() == "Entry"
    assert panel.model.item(0, 2).text() == ""
    assert panel.view.isColumnHidden(2) is True


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
