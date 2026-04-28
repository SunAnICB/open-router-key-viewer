from __future__ import annotations

from open_router_key_viewer.ui.pages.settings_widgets import (
    AutoQuerySettingRow,
    InputSettingRow,
    PropertyRowsPanel,
    SwitchSettingRow,
    TargetMetricDisplayConfigPanel,
)
from open_router_key_viewer.ui.widgets import StatusBadge
from open_router_key_viewer.state import AppConfig


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


def test_metric_display_panel_order_is_independent_from_enabled_targets(qapp) -> None:
    _ = qapp
    changes: list[tuple[list[str], list[str]]] = []
    panel = TargetMetricDisplayConfigPanel(
        "panel",
        lambda selected, order, _labels, _interval: changes.append((selected, order)),
        lambda: None,
    )

    panel.sync_config(
        AppConfig.from_raw(
            {
                "floating_metrics": ["key_remaining"],
                "panel_metrics": ["credits_remaining", "key_usage_daily"],
                "floating_metric_order": ["key_remaining", "credits_remaining", "key_usage_daily"],
                "panel_metric_order": ["credits_remaining", "key_remaining", "key_usage_daily"],
            }
        )
    )

    assert panel.rows_layout.itemAt(0).widget().definition.id == "credits_remaining"
    assert panel.rows_layout.itemAt(1).widget().definition.id == "key_remaining"

    panel._move("key_usage_daily", -1)

    assert changes[-1][0] == ["credits_remaining", "key_usage_daily"]
    assert changes[-1][1][:3] == ["credits_remaining", "key_usage_daily", "key_remaining"]


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
