from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QCloseEvent, QGuiApplication
from PySide6.QtWidgets import QApplication

with redirect_stdout(io.StringIO()):
    from qfluentwidgets import (
        FluentIcon,
        FluentWindow,
        InfoBar,
        InfoBarPosition,
        setThemeColor,
    )

from open_router_key_viewer import __version__
from open_router_key_viewer.i18n import resolve_language_code, tr
from open_router_key_viewer.services.config_store import ConfigStore
from open_router_key_viewer.services.single_instance import SingleInstanceManager
from open_router_key_viewer.ui.controllers.shell_controller import WindowShellController
from open_router_key_viewer.ui.pages.about_page import AboutPage
from open_router_key_viewer.ui.pages.query_pages import CreditsPage, KeyInfoPage
from open_router_key_viewer.ui.pages.settings_page import CachePage
from open_router_key_viewer.ui.runtime import APP_DISPLAY_NAME, apply_theme_mode, install_language

_tr = tr


def _safe_interval_seconds(value: object, default: int = 300) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


class MainWindow(FluentWindow):
    def __init__(self) -> None:
        super().__init__()
        self.config_store = ConfigStore()
        self._shutting_down = False
        self.key_timer = QTimer(self)
        self.key_timer.timeout.connect(self.key_info_page_auto_query)
        self.credits_timer = QTimer(self)
        self.credits_timer.timeout.connect(self.credits_page_auto_query)
        self.key_info_page = KeyInfoPage(
            self.config_store,
            self.refresh_cache_views,
            self.handle_query_success,
            self,
        )
        self.credits_page = CreditsPage(
            self.config_store,
            self.refresh_cache_views,
            self.handle_query_success,
            self,
        )
        self.cache_page = CachePage(
            self.config_store,
            self.refresh_cache_views,
            self.apply_language,
            self.apply_theme_mode,
            self._show_floating_window,
            False,
            False,
            self,
        )
        self.about_page = AboutPage(self)
        self.shell_controller = WindowShellController(
            self,
            config_store=self.config_store,
            key_info_page=self.key_info_page,
            credits_page=self.credits_page,
            refresh_floating_metrics=self.refresh_floating_metrics,
            quit_application=self.quit_application,
        )
        self.cache_page.floating_window_supported = self.shell_controller.floating_window_supported
        self.cache_page.indicator_available = self.shell_controller.indicator_available
        self.cache_page.retranslate_ui()
        self.key_nav_item = self.addSubInterface(self.key_info_page, FluentIcon.CERTIFICATE, _tr("Key 配额"))
        self.credits_nav_item = self.addSubInterface(self.credits_page, FluentIcon.PIE_SINGLE, _tr("账户余额"))
        self.cache_nav_item = self.addSubInterface(self.cache_page, FluentIcon.SETTING, _tr("配置"))
        self.about_nav_item = self.addSubInterface(self.about_page, FluentIcon.INFO, _tr("关于"))
        self.navigationInterface.setReturnButtonVisible(False)
        self.setWindowTitle(APP_DISPLAY_NAME)
        self._apply_initial_geometry()
        self.shell_controller.setup_indicator()
        self.shell_controller.retranslate_ui()
        QTimer.singleShot(0, self._run_startup_queries)

    def apply_language(self, language_code: str) -> None:
        app = QApplication.instance()
        if app is None:
            return
        install_language(app, language_code)
        self.retranslate_ui()
        InfoBar.success(
            title=_tr("已保存"),
            content=_tr("界面语言已更新"),
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2500,
            parent=self,
        )

    def apply_theme_mode(self, theme_mode: str) -> None:
        apply_theme_mode(theme_mode)
        self.retranslate_ui()
        InfoBar.success(
            title=_tr("已保存"),
            content=_tr("主题模式已更新"),
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2500,
            parent=self,
        )

    def retranslate_ui(self) -> None:
        self.key_nav_item.setText(_tr("Key 配额"))
        self.credits_nav_item.setText(_tr("账户余额"))
        self.cache_nav_item.setText(_tr("配置"))
        self.about_nav_item.setText(_tr("关于"))
        self.key_info_page.retranslate_ui()
        self.credits_page.retranslate_ui()
        self.cache_page.retranslate_ui()
        self.about_page.retranslate_ui()
        self.shell_controller.retranslate_ui()

    def refresh_cache_views(self) -> None:
        self.key_info_page.load_cached_secret()
        self.credits_page.load_cached_secret()
        self.cache_page.refresh_view()
        self._apply_polling_settings()
        self.shell_controller.apply_indicator_settings()

    def _apply_initial_geometry(self) -> None:
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(960, 640)
            return

        available = screen.availableGeometry()
        width = max(800, int(available.width() * 0.8))
        height = max(560, int(available.height() * 0.8))
        width = min(width, available.width())
        height = min(height, available.height())
        self.resize(width, height)

        x = available.x() + (available.width() - width) // 2
        y = available.y() + (available.height() - height) // 2
        self.move(x, y)

    def _run_startup_queries(self) -> None:
        payload = self.config_store.load() or {}
        if payload.get("auto_check_updates", True):
            self.about_page.check_updates_silently()
        if payload.get("auto_query_key_info") and payload.get("api_key"):
            self.key_info_page.auto_query_if_possible()
        if payload.get("auto_query_credits") and payload.get("management_key"):
            self.credits_page.auto_query_if_possible()
        self._apply_polling_settings()

    def _apply_polling_settings(self) -> None:
        payload = self.config_store.load() or {}
        self._apply_timer(
            self.key_timer,
            bool(payload.get("poll_key_info_enabled")) and bool(payload.get("api_key")),
            _safe_interval_seconds(payload.get("poll_key_info_interval_seconds", 300)),
        )
        self._apply_timer(
            self.credits_timer,
            bool(payload.get("poll_credits_enabled")) and bool(payload.get("management_key")),
            _safe_interval_seconds(payload.get("poll_credits_interval_seconds", 300)),
        )

    def _apply_timer(self, timer: QTimer, enabled: bool, interval_seconds: int) -> None:
        if enabled:
            timer.start(max(1, interval_seconds) * 1000)
        else:
            timer.stop()

    def key_info_page_auto_query(self) -> None:
        self.key_info_page.auto_query_if_possible()

    def credits_page_auto_query(self) -> None:
        self.credits_page.auto_query_if_possible()

    def refresh_floating_metrics(self) -> None:
        self.key_info_page.run_query_if_possible()
        self.credits_page.run_query_if_possible()

    def _show_floating_window(self) -> None:
        self.shell_controller.show_floating_window()

    def present_window(self) -> None:
        self.shell_controller.show_full_window()
        restored_state = (self.windowState() & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive
        self.setWindowState(restored_state)

    def quit_application(self) -> None:
        self._shutting_down = True
        QApplication.instance().quit()

    def _single_instance_enabled(self) -> bool:
        payload = self.config_store.load() or {}
        return bool(payload.get("single_instance_enabled", False))

    def _background_resident_on_close_enabled(self) -> bool:
        payload = self.config_store.load() or {}
        return bool(payload.get("background_resident_on_close", False))

    def handle_query_success(self, mode: str, payload: dict[str, object]) -> None:
        self.shell_controller.handle_query_success(mode, payload)

    def closeEvent(self, event: QCloseEvent) -> None:
        if (
            not self._shutting_down
            and self._single_instance_enabled()
            and self._background_resident_on_close_enabled()
        ):
            if self.shell_controller.hide_to_background():
                event.ignore()
                return
        self.key_timer.stop()
        self.credits_timer.stop()
        self.key_info_page.stop_worker()
        self.credits_page.stop_worker()
        self.about_page.stop_workers()
        self.shell_controller.close()
        super().closeEvent(event)


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    config_store = ConfigStore()
    payload = config_store.load() or {}
    single_instance_manager: SingleInstanceManager | None = None
    if payload.get("single_instance_enabled"):
        single_instance_manager = SingleInstanceManager(parent=app)
        if not single_instance_manager.start_or_activate_existing():
            return 0
    install_language(app, resolve_language_code(payload.get("ui_language")))
    apply_theme_mode(str(payload.get("theme_mode", "auto")))
    app.setApplicationName(APP_DISPLAY_NAME)
    app.setApplicationVersion(__version__)
    setThemeColor("#0F6CBD")

    window = MainWindow()
    if single_instance_manager is not None:
        single_instance_manager.activation_requested.connect(window.present_window)
    window.show()
    try:
        return app.exec()
    finally:
        if single_instance_manager is not None:
            single_instance_manager.close()
