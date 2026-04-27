from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from open_router_key_viewer.services.config_store import ConfigStoreError
from open_router_key_viewer.services.settings_snapshot import SettingsSnapshotService
from open_router_key_viewer.state import AppConfig, ConfigKey
from open_router_key_viewer.state.settings_view_model import SettingsSnapshotViewModel

SettingsEffect = Literal["runtime", "language", "theme", "global"]


@dataclass(frozen=True, slots=True)
class SettingsActionResult:
    ok: bool
    effect: SettingsEffect | None = None
    value: object = None
    message: str = ""
    success_title: str = "已保存"
    success_message: str = "配置已更新"


class SettingsCoordinator:
    """Own local settings writes, validation, and refresh effects."""

    def __init__(self, snapshot_service: SettingsSnapshotService) -> None:
        self.snapshot_service = snapshot_service

    def current_config(self) -> AppConfig:
        return self.snapshot_service.current_config()

    def build_snapshot(self) -> SettingsSnapshotViewModel:
        return self.snapshot_service.build()

    def set_display_backend(self, backend: str) -> SettingsActionResult:
        current_backend = self.current_config().display_backend
        if backend == current_backend:
            return SettingsActionResult(ok=True)
        try:
            if backend == "auto":
                self.snapshot_service.delete_value(ConfigKey.DISPLAY_BACKEND)
            else:
                self.snapshot_service.save_value(ConfigKey.DISPLAY_BACKEND, backend)
        except ConfigStoreError as exc:
            return self._error(exc)
        return SettingsActionResult(
            ok=True,
            effect="runtime",
            success_message="显示后端已更新，重启后生效",
        )

    def set_language(self, language_code: str) -> SettingsActionResult:
        if language_code == self.current_config().ui_language:
            return SettingsActionResult(ok=True)
        try:
            self.snapshot_service.save_value(ConfigKey.UI_LANGUAGE, language_code)
        except ConfigStoreError as exc:
            return self._error(exc)
        return SettingsActionResult(ok=True, effect="language", value=language_code)

    def set_theme_mode(self, theme_mode: str) -> SettingsActionResult:
        if theme_mode == self.current_config().theme_mode:
            return SettingsActionResult(ok=True)
        try:
            if theme_mode == "auto":
                self.snapshot_service.delete_value(ConfigKey.THEME_MODE)
            else:
                self.snapshot_service.save_value(ConfigKey.THEME_MODE, theme_mode)
        except ConfigStoreError as exc:
            return self._error(exc)
        return SettingsActionResult(ok=True, effect="theme", value=theme_mode)

    def set_switch(self, config_key: ConfigKey, checked: bool) -> SettingsActionResult:
        try:
            self.snapshot_service.save_value(config_key, checked)
        except ConfigStoreError as exc:
            return self._error(exc)
        return SettingsActionResult(ok=True, effect="runtime")

    def set_input(self, config_key: ConfigKey, raw_value: str) -> SettingsActionResult:
        try:
            if not raw_value:
                self.snapshot_service.delete_value(config_key)
            else:
                self.snapshot_service.save_value(config_key, self._parse_input_value(config_key, raw_value))
        except ValueError as exc:
            return SettingsActionResult(ok=False, message=str(exc))
        except ConfigStoreError as exc:
            return self._error(exc)
        return SettingsActionResult(ok=True, effect="runtime")

    def delete_config_file(self) -> SettingsActionResult:
        try:
            self.snapshot_service.delete_config_file()
        except ConfigStoreError as exc:
            return self._error(exc)
        return SettingsActionResult(ok=True, effect="global", success_title="已删除", success_message="配置文件已删除")

    def delete_config_dir(self) -> SettingsActionResult:
        try:
            self.snapshot_service.delete_config_dir()
        except ConfigStoreError as exc:
            return self._error(exc)
        return SettingsActionResult(ok=True, effect="global", success_title="已删除", success_message="缓存目录已删除")

    @staticmethod
    def _parse_input_value(config_key: ConfigKey, raw_value: str) -> Any:
        if config_key in {ConfigKey.POLL_KEY_INFO_INTERVAL_SECONDS, ConfigKey.POLL_CREDITS_INTERVAL_SECONDS}:
            try:
                return max(1, int(raw_value))
            except ValueError as exc:
                raise ValueError("间隔必须是整数秒") from exc
        if config_key in {
            ConfigKey.KEY_INFO_WARNING_THRESHOLD,
            ConfigKey.KEY_INFO_CRITICAL_THRESHOLD,
            ConfigKey.CREDITS_WARNING_THRESHOLD,
            ConfigKey.CREDITS_CRITICAL_THRESHOLD,
        }:
            try:
                return float(raw_value)
            except ValueError as exc:
                raise ValueError("阈值必须是数字") from exc
        return raw_value

    @staticmethod
    def _error(exc: Exception) -> SettingsActionResult:
        return SettingsActionResult(ok=False, message=str(exc))
