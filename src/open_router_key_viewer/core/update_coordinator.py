from __future__ import annotations

import os
from collections.abc import Callable

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget

from open_router_key_viewer.services.update_checker import (
    BinaryUpdater,
    ReleaseAsset,
    UpdateCheckResult,
    UpdateInstallError,
)
from open_router_key_viewer.core.update_workers import (
    UpdateCheckWorker,
    UpdateInstallWorker,
)
from open_router_key_viewer.core.threading import disconnect_signal, stop_thread


class UpdateCoordinator:
    """Own update check and binary install worker lifecycles."""

    def __init__(
        self,
        host: QWidget,
        *,
        checker,
        binary_updater: BinaryUpdater | None,
        on_check_succeeded: Callable[[object], None],
        on_check_failed: Callable[[str], None],
        on_check_finished: Callable[[], None],
        on_install_progress: Callable[[int, int], None],
        on_install_succeeded: Callable[[], None],
        on_install_failed: Callable[[str], None],
        on_install_finished: Callable[[], None],
        on_install_ready_to_relaunch: Callable[[], None] | None = None,
        install_relaunch_delay_ms: int = 300,
        check_worker_cls=None,
        install_worker_cls=None,
        stop_thread_func=stop_thread,
    ) -> None:
        self.host = host
        self.checker = checker
        self.binary_updater = binary_updater
        self.on_check_succeeded = on_check_succeeded
        self.on_check_failed = on_check_failed
        self.on_check_finished = on_check_finished
        self.on_install_progress = on_install_progress
        self.on_install_succeeded = on_install_succeeded
        self.on_install_failed = on_install_failed
        self.on_install_finished = on_install_finished
        self.on_install_ready_to_relaunch = on_install_ready_to_relaunch
        self.install_relaunch_delay_ms = install_relaunch_delay_ms
        self.check_worker_cls = check_worker_cls or UpdateCheckWorker
        self.install_worker_cls = install_worker_cls or UpdateInstallWorker
        self.stop_thread_func = stop_thread_func
        self._check_worker: UpdateCheckWorker | None = None
        self._install_worker: UpdateInstallWorker | None = None

    def is_checking(self) -> bool:
        return self._check_worker is not None and self._check_worker.isRunning()

    def check_updates(self) -> bool:
        if self.is_checking():
            return False
        self._check_worker = self.check_worker_cls(self.checker, self.host)
        self._check_worker.succeeded.connect(self._handle_check_succeeded)
        self._check_worker.failed.connect(self._handle_check_failed)
        self._check_worker.finished.connect(self._handle_check_finished)
        self._check_worker.start()
        return True

    def install_update(self, asset: ReleaseAsset) -> None:
        if self.binary_updater is None:
            raise UpdateInstallError("当前运行方式不支持直接替换二进制文件")
        self._install_worker = self.install_worker_cls(
            self.binary_updater,
            asset,
            os.getpid(),
            self.host,
        )
        self._install_worker.progress_changed.connect(self.on_install_progress)
        self._install_worker.succeeded.connect(self._handle_install_succeeded)
        self._install_worker.failed.connect(self.on_install_failed)
        self._install_worker.finished.connect(self._handle_install_finished)
        self._install_worker.start()

    def stop(self) -> None:
        check_worker = self._check_worker
        install_worker = self._install_worker
        if check_worker is not None:
            disconnect_signal(check_worker.succeeded)
            disconnect_signal(check_worker.failed)
            disconnect_signal(check_worker.finished)
        if install_worker is not None:
            disconnect_signal(install_worker.progress_changed)
            disconnect_signal(install_worker.succeeded)
            disconnect_signal(install_worker.failed)
            disconnect_signal(install_worker.finished)
        self._check_worker = None
        self._install_worker = None
        self.stop_thread_func(check_worker)
        self.stop_thread_func(install_worker)

    def _handle_check_succeeded(self, result: object) -> None:
        if not isinstance(result, UpdateCheckResult):
            self.on_check_failed("检查更新失败：返回结果不符合预期")
            return
        self.on_check_succeeded(result)

    def _handle_check_failed(self, message: str) -> None:
        self.on_check_failed(message)

    def _handle_check_finished(self) -> None:
        self._check_worker = None
        self.on_check_finished()

    def _handle_install_succeeded(self) -> None:
        self.on_install_succeeded()
        if self.on_install_ready_to_relaunch is not None:
            QTimer.singleShot(self.install_relaunch_delay_ms, self.on_install_ready_to_relaunch)

    def _handle_install_finished(self) -> None:
        self._install_worker = None
        self.on_install_finished()
