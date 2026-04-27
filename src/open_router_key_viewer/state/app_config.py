from __future__ import annotations

from dataclasses import dataclass, fields
from enum import StrEnum
from typing import Any, get_args, get_origin, get_type_hints

from open_router_key_viewer.i18n import resolve_language_code


class ConfigKey(StrEnum):
    API_KEY = "api_key"
    MANAGEMENT_KEY = "management_key"
    DISPLAY_BACKEND = "display_backend"
    UI_LANGUAGE = "ui_language"
    THEME_MODE = "theme_mode"
    SINGLE_INSTANCE_ENABLED = "single_instance_enabled"
    BACKGROUND_RESIDENT_ON_CLOSE = "background_resident_on_close"
    AUTO_CHECK_UPDATES = "auto_check_updates"
    AUTO_QUERY_KEY_INFO = "auto_query_key_info"
    AUTO_QUERY_CREDITS = "auto_query_credits"
    POLL_KEY_INFO_ENABLED = "poll_key_info_enabled"
    POLL_KEY_INFO_INTERVAL_SECONDS = "poll_key_info_interval_seconds"
    POLL_CREDITS_ENABLED = "poll_credits_enabled"
    POLL_CREDITS_INTERVAL_SECONDS = "poll_credits_interval_seconds"
    PANEL_INDICATOR_ENABLED = "panel_indicator_enabled"
    NOTIFY_IN_APP = "notify_in_app"
    NOTIFY_SYSTEM = "notify_system"
    KEY_INFO_WARNING_THRESHOLD = "key_info_warning_threshold"
    KEY_INFO_CRITICAL_THRESHOLD = "key_info_critical_threshold"
    CREDITS_WARNING_THRESHOLD = "credits_warning_threshold"
    CREDITS_CRITICAL_THRESHOLD = "credits_critical_threshold"
    NOTIFY_WEBHOOK_KEY_INFO_ENABLED = "notify_webhook_key_info_enabled"
    NOTIFY_WEBHOOK_KEY_INFO_ONLY_CRITICAL = "notify_webhook_key_info_only_critical"
    NOTIFY_WEBHOOK_KEY_INFO_URL = "notify_webhook_key_info_url"
    NOTIFY_WEBHOOK_CREDITS_ENABLED = "notify_webhook_credits_enabled"
    NOTIFY_WEBHOOK_CREDITS_ONLY_CRITICAL = "notify_webhook_credits_only_critical"
    NOTIFY_WEBHOOK_CREDITS_URL = "notify_webhook_credits_url"


DISPLAY_BACKEND_VALUES = {"auto", "wayland", "x11"}
THEME_MODE_VALUES = {"auto", "light", "dark"}

CONFIG_LABELS: dict[str, str] = {
    ConfigKey.API_KEY: "OpenRouter API Key",
    ConfigKey.MANAGEMENT_KEY: "OpenRouter Management Key",
    ConfigKey.DISPLAY_BACKEND: "显示后端",
    ConfigKey.UI_LANGUAGE: "界面语言",
    ConfigKey.THEME_MODE: "主题模式",
    ConfigKey.SINGLE_INSTANCE_ENABLED: "启用单实例模式",
    ConfigKey.BACKGROUND_RESIDENT_ON_CLOSE: "关闭窗口时驻留后台",
    ConfigKey.AUTO_CHECK_UPDATES: "启动时自动检查更新",
    ConfigKey.AUTO_QUERY_KEY_INFO: "启动时自动查询 Key 配额",
    ConfigKey.AUTO_QUERY_CREDITS: "启动时自动查询账户余额",
    ConfigKey.POLL_KEY_INFO_ENABLED: "启用 Key 配额定时查询",
    ConfigKey.POLL_KEY_INFO_INTERVAL_SECONDS: "Key 配额间隔（秒）",
    ConfigKey.POLL_CREDITS_ENABLED: "启用账户余额定时查询",
    ConfigKey.POLL_CREDITS_INTERVAL_SECONDS: "账户余额间隔（秒）",
    ConfigKey.PANEL_INDICATOR_ENABLED: "启用顶栏指示器",
    ConfigKey.NOTIFY_IN_APP: "启用应用内通知",
    ConfigKey.NOTIFY_SYSTEM: "启用系统通知",
    ConfigKey.KEY_INFO_WARNING_THRESHOLD: "Key 配额 Warning 阈值",
    ConfigKey.KEY_INFO_CRITICAL_THRESHOLD: "Key 配额 Critical 阈值",
    ConfigKey.CREDITS_WARNING_THRESHOLD: "账户余额 Warning 阈值",
    ConfigKey.CREDITS_CRITICAL_THRESHOLD: "账户余额 Critical 阈值",
    ConfigKey.NOTIFY_WEBHOOK_KEY_INFO_ENABLED: "启用 Key 配额 Webhook",
    ConfigKey.NOTIFY_WEBHOOK_KEY_INFO_ONLY_CRITICAL: "Key 配额仅 Critical Webhook",
    ConfigKey.NOTIFY_WEBHOOK_KEY_INFO_URL: "Key 配额 Webhook URL",
    ConfigKey.NOTIFY_WEBHOOK_CREDITS_ENABLED: "启用账户余额 Webhook",
    ConfigKey.NOTIFY_WEBHOOK_CREDITS_ONLY_CRITICAL: "账户余额仅 Critical Webhook",
    ConfigKey.NOTIFY_WEBHOOK_CREDITS_URL: "账户余额 Webhook URL",
}

CONFIG_VALUE_LABELS: dict[str, dict[str, str]] = {
    ConfigKey.DISPLAY_BACKEND: {
        "auto": "自动",
        "wayland": "Wayland",
        "x11": "X11",
    },
    ConfigKey.THEME_MODE: {
        "auto": "跟随系统",
        "light": "浅色",
        "dark": "深色",
    },
    ConfigKey.UI_LANGUAGE: {
        "zh_CN": "简体中文",
        "zh_TW": "繁體中文",
        "en": "English",
    },
}


@dataclass(slots=True)
class AppConfig:
    api_key: str = ""
    management_key: str = ""
    display_backend: str = "auto"
    ui_language: str = "zh_CN"
    theme_mode: str = "auto"
    single_instance_enabled: bool = False
    background_resident_on_close: bool = False
    auto_check_updates: bool = True
    auto_query_key_info: bool = False
    auto_query_credits: bool = False
    poll_key_info_enabled: bool = False
    poll_key_info_interval_seconds: int = 300
    poll_credits_enabled: bool = False
    poll_credits_interval_seconds: int = 300
    panel_indicator_enabled: bool = False
    notify_in_app: bool = True
    notify_system: bool = True
    key_info_warning_threshold: float = 5.0
    key_info_critical_threshold: float = 1.0
    credits_warning_threshold: float = 10.0
    credits_critical_threshold: float = 2.0
    notify_webhook_key_info_enabled: bool = False
    notify_webhook_key_info_only_critical: bool = True
    notify_webhook_key_info_url: str = ""
    notify_webhook_credits_enabled: bool = False
    notify_webhook_credits_only_critical: bool = True
    notify_webhook_credits_url: str = ""

    @classmethod
    def from_raw(cls, raw: dict[str, Any] | None) -> AppConfig:
        payload = raw or {}
        kwargs: dict[str, Any] = {}
        type_hints = get_type_hints(cls)
        for field in fields(cls):
            raw_value = payload.get(field.name, field.default)
            if field.name == "ui_language":
                raw_value = payload.get(field.name)
            kwargs[field.name] = _coerce_value(raw_value, field.default, type_hints[field.name])
        config = cls(**kwargs)
        if config.display_backend not in DISPLAY_BACKEND_VALUES:
            config.display_backend = "auto"
        config.ui_language = resolve_language_code(payload.get("ui_language"))
        if config.theme_mode not in THEME_MODE_VALUES:
            config.theme_mode = "auto"
        return config

    def to_raw_dict(self) -> dict[str, Any]:
        return {field.name: getattr(self, field.name) for field in fields(self)}


def config_display_rows(raw: dict[str, Any]) -> list[tuple[str, str, str]]:
    return [
        (
            CONFIG_LABELS.get(key, key),
            _display_config_value(key, value),
            "",
        )
        for key, value in raw.items()
    ]


def _coerce_value(value: Any, default: Any, annotation: Any) -> Any:
    target_type = _resolve_type(annotation)
    if target_type is bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "on"}:
                return True
            if lowered in {"false", "0", "no", "off"}:
                return False
        return default
    if target_type is int:
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return default
    if target_type is float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
    if target_type is str:
        return value if isinstance(value, str) else default
    return value


def _resolve_type(annotation: Any) -> Any:
    origin = get_origin(annotation)
    if origin is None:
        return annotation
    args = [arg for arg in get_args(annotation) if arg is not type(None)]
    return args[0] if args else annotation


def _display_config_value(key: str, value: Any) -> str:
    label_map = CONFIG_VALUE_LABELS.get(key)
    if label_map is not None and isinstance(value, str):
        return label_map.get(value, value)
    return str(value)
