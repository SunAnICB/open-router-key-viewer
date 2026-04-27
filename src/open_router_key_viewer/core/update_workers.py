from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QWidget

from open_router_key_viewer.services.update_checker import (
    BinaryUpdater,
    GitHubReleaseChecker,
    ReleaseAsset,
    UpdateCheckError,
    UpdateInstallError,
)


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
                progress_callback=self._handle_progress,
            )
        except UpdateInstallError as exc:
            if not self.isInterruptionRequested():
                self.failed.emit(str(exc))
            return
        if not self.isInterruptionRequested():
            self.succeeded.emit()

    def _handle_progress(self, received: int, total: int | None) -> None:
        if not self.isInterruptionRequested():
            self.progress_changed.emit(received, total or 0)
