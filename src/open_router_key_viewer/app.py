from __future__ import annotations

import io
import sys
from collections.abc import Callable, Mapping
from contextlib import redirect_stdout

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QGuiApplication
from PySide6.QtWidgets import QApplication, QWidget

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
from open_router_key_viewer.core.progress_runner import ProgressRunner
from open_router_key_viewer.i18n import tr
from open_router_key_viewer.state import (
    LANGUAGE_SWITCH_STEPS,
    MAIN_WINDOW_STEPS,
    STARTUP_STEPS,
    THEME_SWITCH_STEPS,
    ProgressStep,
    step_by_id,
)
from open_router_key_viewer.state.app_metadata import APP_DISPLAY_NAME
from open_router_key_viewer.ui.controllers.shell_controller import WindowShellController
from open_router_key_viewer.ui.pages.about_page import AboutPage
from open_router_key_viewer.ui.pages.query_pages import CreditsPage, KeyInfoPage
from open_router_key_viewer.ui.pages.settings_page import CachePage
from open_router_key_viewer.ui.runtime import apply_theme_mode, install_language
from open_router_key_viewer.ui.widgets import ProgressWindow

_tr = tr


def _create_progress_window(parent: QWidget | None = None) -> ProgressWindow:
    progress_window = ProgressWindow(parent)
    progress_window.center_on_screen()
    progress_window.show()
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    return progress_window


class MainWindow(FluentWindow):
    def __init__(self, context: AppContext, progress_runner: ProgressRunner | None = None) -> None:
        super().__init__()
        self._pending_context = context
        self._progress_runner = progress_runner
        self._run_window_step("init_state", self._init_state)
        self._run_window_step("key_page", self._init_key_page)
        self._run_window_step("credits_page", self._init_credits_page)
        self._run_window_step("settings_page", self._init_settings_page)
        self._run_window_step("about_page", self._init_about_page)
        self._run_window_step("shell_controller", self._init_shell_controller)
        self._run_window_step("kernel", self._init_kernel)
        self._run_window_step("capabilities", self._sync_runtime_capabilities)
        self._run_window_step("navigation", self._init_navigation)
        self._run_window_step("window_ready", self._finish_window_setup)
        self._progress_runner = None

    def _run_window_step(self, step_id: str, action: Callable[[], object]) -> None:
        step = step_by_id(MAIN_WINDOW_STEPS, step_id)
        if self._progress_runner is None:
            action()
            return
        self._progress_runner.run(step, action)

    def _init_state(self) -> None:
        self.context = self._pending_context
        self.runtime_settings = self.context.runtime_settings
        self._shutting_down = False
        self.key_query_state = self.context.key_query_state
        self.credits_query_state = self.context.credits_query_state

    def _init_key_page(self) -> None:
        context = self.context
        self.key_info_page = KeyInfoPage(
            context.key_secret_coordinator,
            self.key_query_state,
            self.refresh_cache_views,
            self.handle_query_success,
            self,
        )

    def _init_credits_page(self) -> None:
        context = self.context
        self.credits_page = CreditsPage(
            context.credits_secret_coordinator,
            self.credits_query_state,
            self.refresh_cache_views,
            self.handle_query_success,
            self,
        )

    def _init_settings_page(self) -> None:
        context = self.context
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

    def _init_about_page(self) -> None:
        context = self.context
        self.about_page = AboutPage(context.about_coordinator, self)

    def _init_shell_controller(self) -> None:
        context = self.context
        self.shell_controller = WindowShellController(
            self,
            shell_coordinator=context.shell_coordinator,
            refresh_floating_metrics=self.refresh_floating_metrics,
            quit_application=self.quit_application,
        )

    def _init_kernel(self) -> None:
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

    def _sync_runtime_capabilities(self) -> None:
        self.cache_page.sync_runtime_capabilities(
            floating_window_supported=self.shell_controller.floating_window_supported,
            indicator_available=self.shell_controller.indicator_available,
        )
        self.cache_page.retranslate_ui()

    def _init_navigation(self) -> None:
        self.key_nav_item = self.addSubInterface(self.key_info_page, FluentIcon.CERTIFICATE, _tr("Key 配额"))
        self.credits_nav_item = self.addSubInterface(self.credits_page, FluentIcon.PIE_SINGLE, _tr("账户余额"))
        self.cache_nav_item = self.addSubInterface(self.cache_page, FluentIcon.SETTING, _tr("配置"))
        self.about_nav_item = self.addSubInterface(self.about_page, FluentIcon.INFO, _tr("关于"))
        self.navigationInterface.setReturnButtonVisible(False)
        self.setWindowTitle(APP_DISPLAY_NAME)

    def _finish_window_setup(self) -> None:
        self._apply_initial_geometry()
        self._progress_overlay = ProgressWindow(self)
        self._progress_overlay.hide()
        self.shell_controller.setup_indicator()
        self.shell_controller.retranslate_ui()
        self.kernel.schedule_startup_tasks()

    def apply_language(self, language_code: str) -> None:
        app = QApplication.instance()
        if app is None:
            return
        self._run_ui_progress_plan(
            LANGUAGE_SWITCH_STEPS,
            {
                "install_language": lambda: install_language(app, language_code),
                "navigation": self._retranslate_navigation,
                "key_page": self.key_info_page.retranslate_ui,
                "credits_page": self.credits_page.retranslate_ui,
                "settings_page": self.cache_page.retranslate_ui,
                "about_page": self.about_page.retranslate_ui,
                "shell": self.shell_controller.retranslate_ui,
                "done": lambda: None,
            },
        )
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
        self._run_ui_progress_plan(
            THEME_SWITCH_STEPS,
            {
                "apply_theme": lambda: apply_theme_mode(theme_mode),
                "key_page": self.key_info_page.retranslate_ui,
                "credits_page": self.credits_page.retranslate_ui,
                "settings_page": self.cache_page.retranslate_ui,
                "about_page": self.about_page.retranslate_ui,
                "shell": self.shell_controller.retranslate_ui,
                "done": lambda: None,
            },
        )
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
        self._retranslate_navigation()
        self.key_info_page.retranslate_ui()
        self.credits_page.retranslate_ui()
        self.cache_page.retranslate_ui()
        self.about_page.retranslate_ui()
        self.shell_controller.retranslate_ui()

    def _retranslate_navigation(self) -> None:
        self.key_nav_item.setText(_tr("Key 配额"))
        self.credits_nav_item.setText(_tr("账户余额"))
        self.cache_nav_item.setText(_tr("配置"))
        self.about_nav_item.setText(_tr("关于"))

    def _run_ui_progress_plan(
        self,
        steps: tuple[ProgressStep, ...],
        actions: Mapping[str, Callable[[], object]],
    ) -> None:
        app = QApplication.instance()
        if app is None:
            return
        self._progress_overlay.center_on_screen()
        self._progress_overlay.show()
        self._progress_overlay.raise_()
        app.processEvents()
        runner = ProgressRunner(self._progress_overlay.set_progress, process_events=app.processEvents)
        try:
            for step in steps:
                runner.run(step, actions.get(step.id, lambda: None))
        finally:
            self._progress_overlay.hide()

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
    app.setApplicationName(APP_DISPLAY_NAME)
    app.setApplicationVersion(__version__)
    setThemeColor("#0F6CBD")

    previous_quit_policy = app.quitOnLastWindowClosed()
    app.setQuitOnLastWindowClosed(False)
    progress_window = _create_progress_window()
    runner = ProgressRunner(progress_window.set_progress, process_events=app.processEvents)

    config = runner.run(step_by_id(STARTUP_STEPS, "load_config"), load_startup_config)
    single_instance_manager = None

    def check_single_instance():
        if not config.single_instance_enabled:
            return None
        manager = create_single_instance_manager(parent=app)
        if not manager.start_or_activate_existing():
            return False
        return manager

    instance_result = runner.run(step_by_id(STARTUP_STEPS, "check_single_instance"), check_single_instance)
    if instance_result is False:
        progress_window.close()
        return 0
    single_instance_manager = instance_result

    def apply_startup_ui_settings() -> None:
        install_language(app, config.ui_language)
        apply_theme_mode(config.theme_mode)

    runner.run(step_by_id(STARTUP_STEPS, "apply_ui_settings"), apply_startup_ui_settings)
    context = runner.run(step_by_id(STARTUP_STEPS, "create_context"), create_app_context)
    runner.update(step_by_id(STARTUP_STEPS, "create_window"))
    window = MainWindow(context, runner)
    if single_instance_manager is not None:
        runner.run(
            step_by_id(STARTUP_STEPS, "connect_single_instance"),
            lambda: single_instance_manager.activation_requested.connect(window.present_window),
        )
    runner.update(step_by_id(STARTUP_STEPS, "ready"))
    progress_window.close()
    app.setQuitOnLastWindowClosed(previous_quit_policy)
    window.show()
    try:
        return app.exec()
    finally:
        if single_instance_manager is not None:
            single_instance_manager.close()
