from __future__ import annotations

from dataclasses import dataclass

from open_router_key_viewer.services.config_store import ConfigStoreError
from open_router_key_viewer.services.secret_cache import SecretCacheService
from open_router_key_viewer.state import ConfigKey


@dataclass(frozen=True, slots=True)
class SecretCacheResult:
    ok: bool
    message: str = ""


class SecretCoordinator:
    """Own cached secret reads and writes."""

    def __init__(self, secret_cache: SecretCacheService) -> None:
        self.secret_cache = secret_cache

    def load_secret(self, key: ConfigKey) -> str:
        return self.secret_cache.load_secret(key)

    def save_secret(self, key: ConfigKey, secret: str) -> SecretCacheResult:
        try:
            self.secret_cache.save_secret(key, secret)
        except ConfigStoreError as exc:
            return SecretCacheResult(False, str(exc))
        return SecretCacheResult(True)

    def delete_secret(self, key: ConfigKey) -> SecretCacheResult:
        try:
            self.secret_cache.delete_secret(key)
        except ConfigStoreError as exc:
            return SecretCacheResult(False, str(exc))
        return SecretCacheResult(True)
