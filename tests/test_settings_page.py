from __future__ import annotations

from typing import Any

from open_router_key_viewer.state import AppConfig
from open_router_key_viewer.core.settings_coordinator import SettingsCoordinator
from open_router_key_viewer.services.settings_snapshot import SettingsSnapshotService
from open_router_key_viewer.ui.pages.settings_page import CachePage


class _FakeConfigStore:
    def __init__(self) -> None:
        self.payload: dict[str, Any] = {}

    def load(self) -> dict[str, Any] | None:
        return dict(self.payload)

    def load_config(self) -> AppConfig:
        return AppConfig.from_raw(self.payload)

    def save_value(self, key: str, value: Any) -> dict[str, Any]:
        self.payload[key] = value
        return dict(self.payload)

    def save_config_value(self, key: str, value: Any) -> AppConfig:
        self.save_value(str(key), value)
        return self.load_config()

    def save_flag(self, key: str, value: bool) -> dict[str, Any]:
        return self.save_value(key, value)

    def delete_value(self, key: str) -> None:
        self.payload.pop(key, None)

    def delete_config_file(self) -> None:
        self.payload.clear()

    def delete_config_dir(self) -> None:
        self.payload.clear()

    def inspect(self) -> dict[str, Any]:
        return {
            "config_dir": "/tmp/open-router-key-viewer",
            "config_path": "/tmp/open-router-key-viewer/config.json",
            "dir_exists": True,
            "config_exists": bool(self.payload),
            "loaded_config": dict(self.payload),
            "files": [{"path": "config.json", "type": "file", "size": 32}],
        }

    def read_raw_config(self) -> str | None:
        if not self.payload:
            return None
        return "{}"


def test_cache_page_display_backend_change_uses_runtime_refresh(qapp) -> None:
    _ = qapp
    runtime_refreshes: list[str] = []
    global_refreshes: list[str] = []
    page = CachePage(
        SettingsCoordinator(SettingsSnapshotService(_FakeConfigStore())),
        lambda: runtime_refreshes.append("runtime"),
        lambda: global_refreshes.append("global"),
        lambda _code: None,
        lambda _code: None,
        lambda: None,
        False,
        False,
    )

    index = page.display_backend_combo.findData("x11")
    assert index >= 0

    page.display_backend_combo.setCurrentIndex(index)

    assert runtime_refreshes == ["runtime"]
    assert global_refreshes == []


def test_cache_page_syncs_runtime_capabilities_after_build(qapp) -> None:
    _ = qapp
    page = CachePage(
        SettingsCoordinator(SettingsSnapshotService(_FakeConfigStore())),
        lambda: None,
        lambda: None,
        lambda _code: None,
        lambda _code: None,
        lambda: None,
        False,
        False,
    )

    assert page.open_floating_button.isEnabled() is False
    assert page.indicator_switch_row.isEnabled() is False

    page.sync_runtime_capabilities(floating_window_supported=True, indicator_available=True)

    assert page.open_floating_button.isEnabled() is True
    assert page.indicator_switch_row.isEnabled() is True


def test_language_and_theme_changes_are_deferred(qapp) -> None:
    app = qapp
    language_changes: list[str] = []
    theme_changes: list[str] = []
    store = _FakeConfigStore()
    page = CachePage(
        SettingsCoordinator(SettingsSnapshotService(store)),
        lambda: None,
        lambda: None,
        language_changes.append,
        theme_changes.append,
        lambda: None,
        False,
        False,
    )

    language_index = page.language_combo.findData("en")
    assert language_index >= 0
    page.language_combo.setCurrentIndex(language_index)
    assert language_changes == []
    app.processEvents()
    assert language_changes == ["en"]

    theme_index = page.theme_mode_combo.findData("dark")
    assert theme_index >= 0
    page.theme_mode_combo.setCurrentIndex(theme_index)
    assert theme_changes == []
    app.processEvents()
    assert theme_changes == ["dark"]
