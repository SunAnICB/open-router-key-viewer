from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer

from open_router_key_viewer.services.runtime_settings import RuntimeSettingsService


class AppKernel(QObject):
    """Coordinate startup, polling, runtime refresh, and shutdown policy."""

    def __init__(
        self,
        runtime_settings: RuntimeSettingsService,
        *,
        run_key_query: Callable[[], None],
        run_credits_query: Callable[[], None],
        load_cached_secrets: Callable[[], None],
        refresh_settings_view: Callable[[], None],
        apply_indicator_settings: Callable[[], None],
        check_updates_silently: Callable[[], None],
        hide_to_background: Callable[[], bool],
        stop_workers: Callable[[], None],
        close_shell: Callable[[], None],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.runtime_settings = runtime_settings
        self.run_key_query = run_key_query
        self.run_credits_query = run_credits_query
        self.load_cached_secrets = load_cached_secrets
        self.refresh_settings_view = refresh_settings_view
        self.apply_indicator_settings = apply_indicator_settings
        self.check_updates_silently = check_updates_silently
        self.hide_to_background = hide_to_background
        self.stop_workers = stop_workers
        self.close_shell = close_shell
        self.key_timer = QTimer(self)
        self.key_timer.timeout.connect(self.run_key_query)
        self.credits_timer = QTimer(self)
        self.credits_timer.timeout.connect(self.run_credits_query)

    def run_startup_tasks(self) -> None:
        config = self.runtime_settings.current_config()
        if config.auto_check_updates:
            self.check_updates_silently()
        if config.auto_query_key_info and config.api_key:
            self.run_key_query()
        if config.auto_query_credits and config.management_key:
            self.run_credits_query()
        self.apply_polling_settings()

    def schedule_startup_tasks(self) -> None:
        QTimer.singleShot(0, self.run_startup_tasks)

    def refresh_cache_views(self) -> None:
        self.load_cached_secrets()
        self.refresh_settings_view()
        self.refresh_runtime_settings()

    def refresh_runtime_settings(self) -> None:
        self.apply_polling_settings()
        self.apply_indicator_settings()

    def apply_polling_settings(self) -> None:
        config = self.runtime_settings.current_config()
        self._apply_timer(
            self.key_timer,
            config.poll_key_info_enabled and bool(config.api_key),
            config.poll_key_info_interval_seconds,
        )
        self._apply_timer(
            self.credits_timer,
            config.poll_credits_enabled and bool(config.management_key),
            config.poll_credits_interval_seconds,
        )

    def should_hide_to_background(self, shutting_down: bool) -> bool:
        if shutting_down:
            return False
        config = self.runtime_settings.current_config()
        return bool(
            config.single_instance_enabled
            and config.background_resident_on_close
            and self.hide_to_background()
        )

    def shutdown(self) -> None:
        self.key_timer.stop()
        self.credits_timer.stop()
        self.stop_workers()
        self.close_shell()

    @staticmethod
    def _apply_timer(timer: QTimer, enabled: bool, interval_seconds: int) -> None:
        if enabled:
            timer.start(max(1, interval_seconds) * 1000)
        else:
            timer.stop()
