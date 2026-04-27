from __future__ import annotations

from typing import Any

from open_router_key_viewer.services.settings_snapshot import SettingsSnapshotService
from open_router_key_viewer.state import AppConfig


class _FakeConfigStore:
    def inspect(self) -> dict[str, Any]:
        return {
            "config_dir": "/tmp/open-router-key-viewer",
            "config_path": "/tmp/open-router-key-viewer/config.json",
            "dir_exists": True,
            "config_exists": True,
            "loaded_config": {"api_key": "secret", "auto_check_updates": True},
            "files": [
                {"path": "config.json", "type": "file", "size": 32},
                {"path": "nested", "type": "directory"},
            ],
        }

    def read_raw_config(self) -> str:
        return '{"api_key":"secret"}'

    def load_config(self) -> AppConfig:
        return AppConfig(api_key="secret", auto_check_updates=True)


def test_settings_snapshot_builds_render_ready_values() -> None:
    snapshot = SettingsSnapshotService(_FakeConfigStore()).build()  # type: ignore[arg-type]

    assert snapshot.directory.exists is True
    assert snapshot.config_file.path.endswith("config.json")
    assert snapshot.file_count.value == "1"
    assert snapshot.entry_count.value == "2"
    assert ("OpenRouter API Key", "secret", "") in snapshot.parsed_rows
    assert snapshot.raw_file_text == '{"api_key":"secret"}'
