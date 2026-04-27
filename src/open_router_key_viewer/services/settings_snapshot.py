from __future__ import annotations

from open_router_key_viewer.services.config_store import ConfigStore
from typing import Any

from open_router_key_viewer.state.app_config import AppConfig, ConfigKey, config_display_rows
from open_router_key_viewer.state.settings_view_model import (
    MetricViewModel,
    PathCardViewModel,
    SettingsSnapshotViewModel,
)


class SettingsSnapshotService:
    """Build a render-ready snapshot of the local config cache."""

    def __init__(self, config_store: ConfigStore) -> None:
        self.config_store = config_store

    def build(self) -> SettingsSnapshotViewModel:
        snapshot = self.config_store.inspect()
        config = self.config_store.load_config()
        raw_config = snapshot.get("loaded_config")
        payload = raw_config if isinstance(raw_config, dict) else {}
        files = snapshot.get("files", [])
        file_count = sum(1 for item in files if item.get("type") == "file")
        entry_count = len(payload)
        config_exists = bool(snapshot["config_exists"])
        dir_exists = bool(snapshot["dir_exists"])

        parsed_rows = config_display_rows(payload) if payload else [("状态", "暂无数据", "")]
        return SettingsSnapshotViewModel(
            config=config,
            directory=PathCardViewModel(
                title="缓存目录",
                status="已存在" if dir_exists else "不存在",
                note="缓存目录路径",
                path=str(snapshot["config_dir"]),
                exists=dir_exists,
            ),
            config_file=PathCardViewModel(
                title="配置文件",
                status="已存在" if config_exists else "不存在",
                note="config.json 文件路径",
                path=str(snapshot["config_path"]),
                exists=config_exists,
            ),
            file_count=MetricViewModel("目录内文件", str(file_count), "缓存目录内的文件数量"),
            entry_count=MetricViewModel("已缓存项目", str(entry_count), "当前解析出的缓存键数量"),
            status="已解析本地缓存" if config_exists else "未找到配置文件",
            parsed_rows=parsed_rows,
            raw_file_text=self.config_store.read_raw_config() or "未找到 config.json 文件",
        )

    def current_config(self) -> AppConfig:
        return self.config_store.load_config()

    def save_value(self, key: ConfigKey | str, value: Any) -> AppConfig:
        return self.config_store.save_config_value(key, value)

    def delete_value(self, key: ConfigKey | str) -> None:
        self.config_store.delete_value(key)

    def delete_config_file(self) -> None:
        self.config_store.delete_config_file()

    def delete_config_dir(self) -> None:
        self.config_store.delete_config_dir()
