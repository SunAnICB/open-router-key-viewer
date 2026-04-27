from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject

from open_router_key_viewer.core.about_coordinator import AboutCoordinator
from open_router_key_viewer.core.secret_coordinator import SecretCoordinator
from open_router_key_viewer.core.settings_coordinator import SettingsCoordinator
from open_router_key_viewer.core.shell_coordinator import ShellCoordinator
from open_router_key_viewer.services.config_store import ConfigStore
from open_router_key_viewer.services.runtime_settings import RuntimeSettingsService
from open_router_key_viewer.services.secret_cache import SecretCacheService
from open_router_key_viewer.services.settings_snapshot import SettingsSnapshotService
from open_router_key_viewer.services.single_instance import SingleInstanceManager
from open_router_key_viewer.state import AppConfig, QueryState


@dataclass(slots=True)
class AppContext:
    config_store: ConfigStore
    runtime_settings: RuntimeSettingsService
    key_query_state: QueryState
    credits_query_state: QueryState
    key_secret_coordinator: SecretCoordinator
    credits_secret_coordinator: SecretCoordinator
    settings_coordinator: SettingsCoordinator
    about_coordinator: AboutCoordinator
    shell_coordinator: ShellCoordinator


def create_app_context() -> AppContext:
    config_store = ConfigStore()
    runtime_settings = RuntimeSettingsService(config_store)
    secret_cache = SecretCacheService(config_store)
    key_query_state = QueryState("key-info")
    credits_query_state = QueryState("credits")
    return AppContext(
        config_store=config_store,
        runtime_settings=runtime_settings,
        key_query_state=key_query_state,
        credits_query_state=credits_query_state,
        key_secret_coordinator=SecretCoordinator(secret_cache),
        credits_secret_coordinator=SecretCoordinator(secret_cache),
        settings_coordinator=SettingsCoordinator(SettingsSnapshotService(config_store)),
        about_coordinator=AboutCoordinator(),
        shell_coordinator=ShellCoordinator(
            config_store,
            key_query_state=key_query_state,
            credits_query_state=credits_query_state,
        ),
    )


def load_startup_config() -> AppConfig:
    return RuntimeSettingsService(ConfigStore()).current_config()


def create_single_instance_manager(parent: QObject) -> SingleInstanceManager:
    return SingleInstanceManager(parent=parent)
