from __future__ import annotations

from open_router_key_viewer.services.config_store import ConfigStore
from open_router_key_viewer.state import ConfigKey


class SecretCacheService:
    """Read and update cached OpenRouter secrets."""

    def __init__(self, config_store: ConfigStore) -> None:
        self.config_store = config_store

    def load_secret(self, key: ConfigKey | str) -> str:
        value = getattr(self.config_store.load_config(), str(key), "")
        return value if isinstance(value, str) else ""

    def save_secret(self, key: ConfigKey | str, secret: str) -> None:
        self.config_store.save_config_value(key, secret)

    def delete_secret(self, key: ConfigKey | str) -> None:
        self.config_store.delete_value(key)
