from __future__ import annotations

import io
import sys
from collections.abc import Callable
from contextlib import redirect_stdout
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QWidget

with redirect_stdout(io.StringIO()):
    from qfluentwidgets import InfoBar, InfoBarPosition, MessageBox

from open_router_key_viewer.core.update_coordinator import UpdateCoordinator
from open_router_key_viewer.core.update_runtime import build_update_runtime_context
from open_router_key_viewer.core.update_state import UpdateStateMachine, UpdateStatus
from open_router_key_viewer.core.threading import stop_thread
from open_router_key_viewer.i18n import tr
from open_router_key_viewer.state import (
    TextSpec,
    UpdateCardViewModel,
)
from open_router_key_viewer.ui.runtime import show_error_bar
from open_router_key_viewer.ui.widgets import UpdateCard

_tr = tr


class AboutUpdateController:
    """Coordinate release checks and binary self-update from the about page."""

    def __init__(
        self,
        host: QWidget,
        update_card: UpdateCard,
        *,
        quit_application: Callable[[], None] | None = None,
    ) -> None:
        self.host = host
        self.update_card = update_card
        self._quit_application = quit_application or self._default_quit_application
        runtime_context = build_update_runtime_context()
        self._binary_update_supported = runtime_context.binary_update_supported
        self._build_info = runtime_context.build_info
        self._update_state = UpdateStateMachine(
            build_info=self._build_info,
            binary_update_supported=self._binary_update_supported,
            binary_updater=runtime_context.binary_updater,
        )
        self._update_state.release_url = runtime_context.release_url
        self._startup_silent_check = False
        self._refresh_update_card_state: Callable[[], None] = lambda: None
        self._update_coordinator = UpdateCoordinator(
            self.host,
            checker=runtime_context.release_checker,
            binary_updater=runtime_context.binary_updater,
            on_check_succeeded=self._handle_update_success,
            on_check_failed=self._handle_update_failure,
            on_check_finished=self._handle_update_finished,
            on_install_progress=self._handle_install_progress,
            on_install_succeeded=self._handle_install_success,
            on_install_failed=self._handle_install_failure,
            on_install_finished=self._handle_install_finished,
            on_install_ready_to_relaunch=self._quit_application,
            stop_thread_func=stop_thread,
        )

        self.update_card.check_button.clicked.connect(self.check_updates)
        self.update_card.release_button.clicked.connect(self.open_release_page)
        self.update_card.replace_button.clicked.connect(self.replace_current_binary)
        self.show_intro_state()

    @property
    def build_info(self):
        return self._build_info

    @property
    def binary_update_supported(self) -> bool:
        return self._binary_update_supported

    @property
    def _update_worker(self):
        return self._update_coordinator._check_worker

    @property
    def _install_worker(self):
        return self._update_coordinator._install_worker

    @_install_worker.setter
    def _install_worker(self, worker) -> None:
        self._update_coordinator._install_worker = worker

    def retranslate_ui(self) -> None:
        self.update_card.retranslate_ui()
        self._refresh_update_card_state()

    def show_intro_state(self) -> None:
        self._apply_update_status(self._update_state.intro())
        self._refresh_update_card_state = self.show_intro_state

    def check_updates(self) -> None:
        self._startup_silent_check = False
        self._start_update_check()

    def check_updates_silently(self) -> None:
        self._startup_silent_check = True
        self._start_update_check()

    def open_release_page(self) -> None:
        if not self._update_state.release_url:
            return
        QDesktopServices.openUrl(QUrl(self._update_state.release_url))

    def replace_current_binary(self) -> None:
        replacement = self._update_state.prepare_replacement()
        if not replacement.ok or replacement.asset is None:
            self._handle_update_failure(_tr(replacement.error))
            return

        box = MessageBox(
            _tr("下载并替换当前二进制"),
            _tr("将下载最新二进制文件，并在你关闭当前程序后替换当前可执行文件。\n下载完成后会自动退出当前程序，替换完成后自动重新启动。是否继续？"),
            self.host.window(),
        )
        box.yesButton.setText(_tr("继续"))
        box.cancelButton.setText(_tr("取消"))
        if not box.exec():
            return

        try:
            self.update_card.check_button.setEnabled(False)
            self.update_card.release_button.setEnabled(False)
            self.update_card.replace_button.setEnabled(False)
            self._show_status(
                self._update_state.downloading(
                    name=replacement.asset.name,
                    meta="下载完成后将自动退出当前程序，替换二进制并重新启动。",
                )
            )
            self._update_coordinator.install_update(replacement.asset)
        except RuntimeError as exc:
            self._handle_update_failure(str(exc))

    def stop(self) -> None:
        self._update_coordinator.stop()

    def _start_update_check(self) -> None:
        if self._update_coordinator.is_checking():
            return

        self.update_card.check_button.setEnabled(False)
        self.update_card.release_button.setEnabled(False)
        self.update_card.replace_button.setEnabled(False)
        if not self._startup_silent_check:
            self._show_status(self._update_state.checking())
            self._refresh_update_card_state = self._start_update_check_state
        self._update_coordinator.check_updates()

    def _start_update_check_state(self) -> None:
        self._show_status(self._update_state.checking())
        self._refresh_update_card_state = self._start_update_check_state

    def _handle_update_success(self, result: object) -> None:
        self._show_status(self._update_state.handle_check_success(result, silent=self._startup_silent_check))

    def _handle_update_failure(self, message: str) -> None:
        status = self._update_state.handle_check_failure(message, silent=self._startup_silent_check)
        if self._startup_silent_check:
            self._show_status(status)
        else:
            self._show_status(status)
            show_error_bar(self.host.window(), _tr("检查更新失败"), message)

    def _handle_update_finished(self) -> None:
        self.update_card.check_button.setEnabled(True)
        self.update_card.release_button.setEnabled(True)
        self._startup_silent_check = False

    def _handle_install_progress(self, received: int, total: int) -> None:
        self._show_status(self._update_state.download_progress(received=received, total=total))

    def _handle_install_success(self) -> None:
        self._show_status(self._update_state.downloaded(filename=Path(sys.executable).name))

    def _handle_install_failure(self, message: str) -> None:
        self._show_status(self._update_state.download_failed(message))
        show_error_bar(self.host.window(), _tr("下载更新失败"), message)

    def _handle_install_finished(self) -> None:
        if QApplication.instance() is None:
            return
        self.update_card.check_button.setEnabled(True)
        self.update_card.release_button.setEnabled(True)

    def _show_status(self, status: UpdateStatus) -> None:
        self._apply_update_status(status)
        self._refresh_update_card_state = lambda: self._apply_update_card_state(status.view_model)

    def _apply_update_status(self, status: UpdateStatus) -> None:
        self._apply_update_card_state(status.view_model)
        if not status.notification_title:
            return
        info_bar = InfoBar.warning if status.warning else InfoBar.info
        info_bar(
            title=_tr(status.notification_title),
            content=_tr(status.notification_message),
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=5000,
            parent=self.host.window(),
        )

    def _apply_update_card_state(self, view_model: UpdateCardViewModel) -> None:
        self.update_card.set_state(
            self._render_text(view_model.title),
            self._render_text(view_model.note),
            self._render_text(view_model.meta),
            can_open_release=view_model.can_open_release,
            can_replace=view_model.can_replace,
        )

    def _render_text(self, spec: TextSpec) -> str:
        if not spec.args:
            return _tr(spec.source)
        rendered_args = {
            key: self._render_text(value) if isinstance(value, TextSpec) else value
            for key, value in spec.args.items()
        }
        return _tr(spec.source).format(**rendered_args)

    @staticmethod
    def _default_quit_application() -> None:
        app = QApplication.instance()
        if app is not None:
            app.quit()
