from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout

from PySide6.QtCore import Qt
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
from open_router_key_viewer.core.app_kernel import AppKernel
from open_router_key_viewer.core.bootstrap import (
    AppContext,
    create_app_context,
    create_single_instance_manager,
    load_startup_config,
)
from open_router_key_viewer.i18n import tr
from open_router_key_viewer.state.app_metadata import APP_DISPLAY_NAME
from open_router_key_viewer.ui.controllers.shell_controller import WindowShellController
from open_router_key_viewer.ui.pages.about_page import AboutPage
from open_router_key_viewer.ui.pages.query_pages import CreditsPage, KeyInfoPage
from open_router_key_viewer.ui.pages.settings_page import CachePage
from open_router_key_viewer.ui.runtime import apply_theme_mode, install_language

_tr = tr


class MainWindow(FluentWindow):
    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context
        self.runtime_settings = context.runtime_settings
        self._shutting_down = False
        self.key_query_state = context.key_query_state
        self.credits_query_state = context.credits_query_state
        self.key_info_page = KeyInfoPage(
            context.key_secret_coordinator,
            self.key_query_state,
            self.refresh_cache_views,
            self.handle_query_success,
            self,
        )
        self.credits_page = CreditsPage(
            context.credits_secret_coordinator,
            self.credits_query_state,
            self.refresh_cache_views,
            self.handle_query_success,
            self,
        )
        self.cache_page = CachePage(
            context.settings_coordinator,
            self.refresh_runtime_settings,
            self.refresh_cache_views,
            self.apply_language,
            self.apply_theme_mode,
            self._show_floating_window,
            False,
            False,
            self,
        )
        self.about_page = AboutPage(context.about_coordinator, self)
        self.shell_controller = WindowShellController(
            self,
            shell_coordinator=context.shell_coordinator,
            refresh_floating_metrics=self.refresh_floating_metrics,
            quit_application=self.quit_application,
        )
        self.kernel = AppKernel(
            self.runtime_settings,
            run_key_query=self.key_info_page.auto_query_if_possible,
            run_credits_query=self.credits_page.auto_query_if_possible,
            load_cached_secrets=self._load_cached_secrets,
            refresh_settings_view=self.cache_page.refresh_view,
            apply_indicator_settings=self.shell_controller.apply_indicator_settings,
            check_updates_silently=self.about_page.check_updates_silently,
            hide_to_background=self.shell_controller.hide_to_background,
            stop_workers=self._stop_workers,
            close_shell=self.shell_controller.close,
            parent=self,
        )
        self.cache_page.sync_runtime_capabilities(
            floating_window_supported=self.shell_controller.floating_window_supported,
            indicator_available=self.shell_controller.indicator_available,
        )
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
        self.kernel.schedule_startup_tasks()

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
        self.kernel.refresh_cache_views()

    def _load_cached_secrets(self) -> None:
        self.key_info_page.load_cached_secret()
        self.credits_page.load_cached_secret()

    def refresh_runtime_settings(self) -> None:
        self.kernel.refresh_runtime_settings()

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

    def handle_query_success(self, mode: str, summary: dict[str, object]) -> None:
        self.shell_controller.handle_query_success(mode, summary)

    def _stop_workers(self) -> None:
        self.key_info_page.stop_worker()
        self.credits_page.stop_worker()
        self.about_page.stop_workers()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.kernel.should_hide_to_background(self._shutting_down):
            event.ignore()
            return
        self.kernel.shutdown()
        super().closeEvent(event)


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    config = load_startup_config()
    single_instance_manager = None
    if config.single_instance_enabled:
        single_instance_manager = create_single_instance_manager(parent=app)
        if not single_instance_manager.start_or_activate_existing():
            return 0
    install_language(app, config.ui_language)
    apply_theme_mode(config.theme_mode)
    app.setApplicationName(APP_DISPLAY_NAME)
    app.setApplicationVersion(__version__)
    setThemeColor("#0F6CBD")

    window = MainWindow(create_app_context())
    if single_instance_manager is not None:
        single_instance_manager.activation_requested.connect(window.present_window)
    window.show()
    try:
        return app.exec()
    finally:
        if single_instance_manager is not None:
            single_instance_manager.close()
