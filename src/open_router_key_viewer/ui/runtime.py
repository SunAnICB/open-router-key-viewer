from __future__ import annotations

import io
from contextlib import redirect_stdout

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import QApplication, QWidget

with redirect_stdout(io.StringIO()):
    from qfluentwidgets import InfoBar, InfoBarPosition, Theme, setTheme

from open_router_key_viewer.i18n import DictTranslator, tr
from open_router_key_viewer.services.openrouter import OpenRouterAPIError, OpenRouterClient
from open_router_key_viewer.services.update_checker import (
    BinaryUpdater,
    GitHubReleaseChecker,
    ReleaseAsset,
    UpdateCheckError,
    UpdateInstallError,
)
from open_router_key_viewer.state.app_metadata import THEME_MODE_OPTIONS
_DETACHED_THREADS: list[QThread] = []


def format_currency_value(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"${value:.4f}"
    return "-"


def install_language(app: QApplication, language_code: str) -> None:
    translator = getattr(app, "_dict_translator", None)
    if translator is not None:
        app.removeTranslator(translator)

    new_translator = DictTranslator(language_code)
    app.installTranslator(new_translator)
    app._dict_translator = new_translator  # type: ignore[attr-defined]


def resolve_theme_mode(config_value: object) -> str:
    if isinstance(config_value, str) and config_value in {code for code, _ in THEME_MODE_OPTIONS}:
        return config_value
    return "auto"


def apply_theme_mode(theme_mode: str) -> None:
    resolved = resolve_theme_mode(theme_mode)
    mapping = {
        "auto": Theme.AUTO,
        "light": Theme.LIGHT,
        "dark": Theme.DARK,
    }
    setTheme(mapping.get(resolved, Theme.AUTO))


def show_error_bar(parent: QWidget, title: str, message: str) -> None:
    InfoBar.error(
        title=title,
        content=message,
        orient=Qt.Orientation.Horizontal,
        isClosable=True,
        position=InfoBarPosition.TOP_RIGHT,
        duration=3000,
        parent=parent,
    )


def stop_thread(thread: QThread | None, timeout_ms: int = 3000) -> None:
    if thread is None or not thread.isRunning():
        return
    thread.requestInterruption()
    thread.quit()
    if thread.wait(timeout_ms):
        return
    thread.setParent(None)
    _DETACHED_THREADS.append(thread)

    def _release_thread() -> None:
        try:
            _DETACHED_THREADS.remove(thread)
        except ValueError:
            pass
        thread.deleteLater()

    thread.finished.connect(_release_thread)


def disconnect_signal(signal) -> None:
    try:
        signal.disconnect()
    except (RuntimeError, TypeError):
        return


class QueryWorker(QThread):
    succeeded = Signal(dict)
    failed = Signal(object)

    def __init__(self, mode: str, secret: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.mode = mode
        self.secret = secret
        self.client = OpenRouterClient()

    def run(self) -> None:
        try:
            if self.mode == "key-info":
                result = self.client.get_current_key_info(self.secret)
            elif self.mode == "credits":
                result = self.client.get_credits(self.secret)
            else:
                raise OpenRouterAPIError(f"Unsupported query mode: {self.mode}")
        except OpenRouterAPIError as exc:
            if not self.isInterruptionRequested():
                self.failed.emit(
                    {
                        "message": str(exc),
                        "http_meta": exc.http_meta or {},
                        "raw_response": exc.raw_response,
                    }
                )
            return

        if not self.isInterruptionRequested():
            self.succeeded.emit(result.to_dict())


class UpdateCheckWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, checker: GitHubReleaseChecker, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.checker = checker

    def run(self) -> None:
        try:
            result = self.checker.check_latest_release()
        except UpdateCheckError as exc:
            if not self.isInterruptionRequested():
                self.failed.emit(str(exc))
            return
        if not self.isInterruptionRequested():
            self.succeeded.emit(result)


class UpdateInstallWorker(QThread):
    progress_changed = Signal(int, int)
    succeeded = Signal()
    failed = Signal(str)

    def __init__(
        self,
        updater: BinaryUpdater,
        asset: ReleaseAsset,
        current_pid: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.updater = updater
        self.asset = asset
        self.current_pid = current_pid

    def run(self) -> None:
        try:
            self.updater.install_from_asset(
                self.asset,
                current_pid=self.current_pid,
                progress_callback=self._emit_progress,
            )
        except UpdateInstallError as exc:
            if not self.isInterruptionRequested():
                self.failed.emit(str(exc))
            return
        if not self.isInterruptionRequested():
            self.succeeded.emit()

    def _emit_progress(self, received: int, total: int | None) -> None:
        if not self.isInterruptionRequested():
            self.progress_changed.emit(received, total or 0)
