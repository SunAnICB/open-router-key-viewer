from __future__ import annotations

import io
from contextlib import redirect_stdout

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import QApplication, QWidget

with redirect_stdout(io.StringIO()):
    from qfluentwidgets import InfoBar, InfoBarPosition

from open_router_key_viewer.i18n import DictTranslator, tr
from open_router_key_viewer.services.openrouter import OpenRouterAPIError, OpenRouterClient
from open_router_key_viewer.services.update_checker import (
    BinaryUpdater,
    GitHubReleaseChecker,
    ReleaseAsset,
    UpdateCheckError,
    UpdateInstallError,
)

APP_DISPLAY_NAME = "OpenRouter Key Viewer"
APP_AUTHOR = "SunAnICB"
APP_AUTHOR_URL = "https://github.com/SunAnICB"
APP_REPOSITORY_URL = "https://github.com/SunAnICB/open-router-key-viewer"
APP_LICENSE_NAME = "MIT"
APP_DATA_SOURCE_URL = "https://openrouter.ai/docs/api-reference/overview"
DISPLAY_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
BINARY_ASSET_NAME = "open-router-key-viewer"
DISPLAY_BACKEND_OPTIONS: list[tuple[str, str]] = [
    ("auto", "自动"),
    ("wayland", "Wayland"),
    ("x11", "X11"),
]


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
    if thread.wait(timeout_ms):
        return
    thread.terminate()
    thread.wait(1000)


class QueryWorker(QThread):
    succeeded = Signal(dict)
    failed = Signal(str)

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
            self.failed.emit(str(exc))
            return

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
            self.failed.emit(str(exc))
            return
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
            self.failed.emit(str(exc))
            return
        self.succeeded.emit()

    def _emit_progress(self, received: int, total: int | None) -> None:
        self.progress_changed.emit(received, total or 0)

