from __future__ import annotations

from open_router_key_viewer.services.config_store import ConfigStore
from open_router_key_viewer.state import AppConfig


class RuntimeSettingsService:
    """Expose runtime settings without coupling controllers to config storage."""

    def __init__(self, config_store: ConfigStore) -> None:
        self.config_store = config_store

    def current_config(self) -> AppConfig:
        return self.config_store.load_config()

    def panel_indicator_enabled(self) -> bool:
        return self.current_config().panel_indicator_enabled
