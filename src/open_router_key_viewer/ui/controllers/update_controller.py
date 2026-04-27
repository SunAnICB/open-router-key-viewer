from __future__ import annotations

import io
import os
import sys
from collections.abc import Callable
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QWidget

with redirect_stdout(io.StringIO()):
    from qfluentwidgets import InfoBar, InfoBarPosition, MessageBox

from open_router_key_viewer import __version__
from open_router_key_viewer.i18n import tr
from open_router_key_viewer.services.build_info import get_build_info
from open_router_key_viewer.services.installer import AppInstaller
from open_router_key_viewer.services.update_checker import (
    BinaryUpdater,
    GitHubReleaseChecker,
    ReleaseAsset,
    UpdateCheckResult,
    UpdateInstallError,
)
from open_router_key_viewer.state import (
    TextSpec,
    UpdateCardViewModel,
    build_asset_note,
    build_commit_note,
    build_dev_build_state,
    build_download_failed_state,
    build_downloaded_state,
    build_downloading_state,
    build_latest_state,
    build_update_available_state,
    build_update_checking_state,
    build_update_failure_state,
    build_update_intro_state,
)
from open_router_key_viewer.ui.runtime import (
    APP_REPOSITORY_URL,
    BINARY_ASSET_NAME,
    DISPLAY_DATETIME_FORMAT,
    UpdateCheckWorker,
    UpdateInstallWorker,
    disconnect_signal,
    show_error_bar,
    stop_thread,
)
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
        self._release_url = APP_REPOSITORY_URL + "/releases"
        self._latest_asset: ReleaseAsset | None = None
        self._update_worker: UpdateCheckWorker | None = None
        self._install_worker: UpdateInstallWorker | None = None
        self._binary_update_supported = bool(getattr(sys, "frozen", False))
        self._install_info = AppInstaller(
            Path(sys.executable),
            is_binary_runtime=self._binary_update_supported,
        ).inspect()
        relaunch_command = (
            [str(self._install_info.launcher_path)]
            if self._install_info.current_is_installed
            else None
        )
        self._binary_updater = (
            BinaryUpdater(Path(sys.executable), relaunch_command=relaunch_command)
            if self._binary_update_supported
            else None
        )
        self._build_info = get_build_info()
        self._startup_silent_check = False
        self._refresh_update_card_state: Callable[[], None] = lambda: None
        if self._binary_updater is not None:
            self._binary_updater.cleanup_stale_updates()
        owner, repo = self._parse_repo(APP_REPOSITORY_URL)
        self._release_checker = GitHubReleaseChecker(
            owner,
            repo,
            asset_name=BINARY_ASSET_NAME,
            current_version=__version__,
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

    def retranslate_ui(self) -> None:
        self.update_card.retranslate_ui()
        self._refresh_update_card_state()

    def show_intro_state(self) -> None:
        self._apply_update_card_state(build_update_intro_state(self._binary_update_supported))
        self._refresh_update_card_state = self.show_intro_state

    def check_updates(self) -> None:
        self._startup_silent_check = False
        self._start_update_check()

    def check_updates_silently(self) -> None:
        self._startup_silent_check = True
        self._start_update_check()

    def open_release_page(self) -> None:
        if not self._release_url:
            return
        QDesktopServices.openUrl(QUrl(self._release_url))

    def replace_current_binary(self) -> None:
        if not self._binary_update_supported or self._binary_updater is None:
            self._handle_update_failure(_tr("当前运行方式不支持直接替换二进制文件"))
            return
        if self._latest_asset is None:
            self._handle_update_failure(_tr("当前未找到可替换的二进制更新文件"))
            return

        supported, reason = self._binary_updater.can_replace_current_binary()
        if not supported:
            self._handle_update_failure(reason or _tr("当前环境不支持替换二进制文件"))
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
            self._show_downloading_state(
                name=self._latest_asset.name,
                meta=_tr("下载完成后将自动退出当前程序，替换二进制并重新启动。"),
            )
            self._install_worker = UpdateInstallWorker(
                self._binary_updater,
                self._latest_asset,
                os.getpid(),
                self.host,
            )
            self._install_worker.progress_changed.connect(self._handle_install_progress)
            self._install_worker.succeeded.connect(self._handle_install_success)
            self._install_worker.failed.connect(self._handle_install_failure)
            self._install_worker.finished.connect(self._handle_install_finished)
            self._install_worker.start()
        except UpdateInstallError as exc:
            self._handle_update_failure(str(exc))

    def stop(self) -> None:
        if self._update_worker is not None:
            disconnect_signal(self._update_worker.succeeded)
            disconnect_signal(self._update_worker.failed)
            disconnect_signal(self._update_worker.finished)
        if self._install_worker is not None:
            disconnect_signal(self._install_worker.progress_changed)
            disconnect_signal(self._install_worker.succeeded)
            disconnect_signal(self._install_worker.failed)
            disconnect_signal(self._install_worker.finished)
        stop_thread(self._update_worker)
        stop_thread(self._install_worker)

    def _start_update_check(self) -> None:
        if self._update_worker and self._update_worker.isRunning():
            return

        self.update_card.check_button.setEnabled(False)
        self.update_card.release_button.setEnabled(False)
        self.update_card.replace_button.setEnabled(False)
        if not self._startup_silent_check:
            self._apply_update_card_state(build_update_checking_state())
            self._refresh_update_card_state = self._start_update_check_state
        self._update_worker = UpdateCheckWorker(self._release_checker, self.host)
        self._update_worker.succeeded.connect(self._handle_update_success)
        self._update_worker.failed.connect(self._handle_update_failure)
        self._update_worker.finished.connect(self._handle_update_finished)
        self._update_worker.start()

    def _start_update_check_state(self) -> None:
        self._apply_update_card_state(build_update_checking_state())
        self._refresh_update_card_state = self._start_update_check_state

    def _show_update_available_state(
        self,
        *,
        current_version: str,
        release_version: str,
        asset_note: TextSpec,
        published_at: str,
        replace_note: str,
        can_replace: bool,
    ) -> None:
        self._apply_update_card_state(
            build_update_available_state(
                current_version=current_version,
                release_version=release_version,
                asset_note=asset_note,
                published_at=published_at,
                replace_note=replace_note,
                can_replace=can_replace,
            ),
        )
        self._refresh_update_card_state = lambda: self._show_update_available_state(
            current_version=current_version,
            release_version=release_version,
            asset_note=asset_note,
            published_at=published_at,
            replace_note=replace_note,
            can_replace=can_replace,
        )

    def _show_dev_build_state(
        self,
        *,
        current_version: str,
        release_version: str,
        tag_name: str,
        published_at: str,
        commit_note: TextSpec | None,
    ) -> None:
        self._apply_update_card_state(
            build_dev_build_state(
                current_version=current_version,
                release_version=release_version,
                tag_name=tag_name,
                published_at=published_at,
                commit_note=commit_note,
            ),
        )
        self._refresh_update_card_state = lambda: self._show_dev_build_state(
            current_version=current_version,
            release_version=release_version,
            tag_name=tag_name,
            published_at=published_at,
            commit_note=commit_note,
        )

    def _show_latest_state(self, *, current_version: str, tag_name: str, published_at: str) -> None:
        self._apply_update_card_state(
            build_latest_state(
                current_version=current_version,
                tag_name=tag_name,
                published_at=published_at,
            ),
        )
        self._refresh_update_card_state = lambda: self._show_latest_state(
            current_version=current_version,
            tag_name=tag_name,
            published_at=published_at,
        )

    def _show_update_failure_state(self, message: str) -> None:
        self._apply_update_card_state(build_update_failure_state(message))
        self._refresh_update_card_state = lambda: self._show_update_failure_state(message)

    def _show_downloading_state(self, *, name: str, meta: str, note: str | None = None) -> None:
        self._apply_update_card_state(
            build_downloading_state(
                name=name,
                note=TextSpec(note) if note is not None else None,
                meta=TextSpec(meta),
            )
        )
        self._refresh_update_card_state = lambda: self._show_downloading_state(
            name=name,
            meta=meta,
            note=note or _tr("正在下载 {name}。").format(name=name),
        )

    def _show_downloaded_state(self, *, filename: str) -> None:
        self._apply_update_card_state(build_downloaded_state(filename=filename))
        self._refresh_update_card_state = lambda: self._show_downloaded_state(filename=filename)

    def _show_download_failed_state(self, message: str) -> None:
        self._apply_update_card_state(
            build_download_failed_state(
                message,
                binary_update_supported=self._binary_update_supported,
                has_asset=self._latest_asset is not None,
            )
        )
        self._refresh_update_card_state = lambda: self._show_download_failed_state(message)

    def _handle_update_success(self, result: object) -> None:
        if not isinstance(result, UpdateCheckResult):
            self._handle_update_failure(_tr("检查更新失败：返回结果不符合预期"))
            return

        release = result.latest_release
        self._release_url = release.html_url
        self._latest_asset = release.asset
        asset_note = build_asset_note(release.asset.name if release.asset is not None else None)
        can_replace = bool(result.update_available and self._binary_update_supported and release.asset is not None)
        replace_note = ""
        if can_replace and self._binary_updater is not None:
            supported, reason = self._binary_updater.can_replace_current_binary()
            can_replace = supported
            if reason:
                replace_note = f"  {reason}"
        if result.update_available:
            self._show_update_available_state(
                current_version=result.current_version,
                release_version=release.version,
                asset_note=asset_note,
                published_at=self._format_release_time(release.published_at),
                replace_note=replace_note,
                can_replace=can_replace,
            )
            if self._startup_silent_check:
                InfoBar.info(
                    title=_tr("发现新版本"),
                    content=_tr("检测到 v{release.version} 可用，可在关于页查看并更新。").format(release=release),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=5000,
                    parent=self.host.window(),
                )
            return

        is_dev_build = (
            result.version_comparison < 0
            or self._build_info.dirty
            or (
                bool(release.commit_sha)
                and self._build_info.commit_sha != "unknown"
                and self._build_info.commit_sha != release.commit_sha
            )
        )
        if is_dev_build:
            commit_note: TextSpec | None = None
            if release.commit_sha:
                commit_note = build_commit_note(
                    self._short_commit(self._build_info.commit_sha),
                    self._short_commit(release.commit_sha),
                )
            self._latest_asset = None
            self._show_dev_build_state(
                current_version=result.current_version,
                release_version=release.version,
                tag_name=release.tag_name,
                published_at=self._format_release_time(release.published_at),
                commit_note=commit_note,
            )
            if self._startup_silent_check:
                InfoBar.info(
                    title=_tr("当前是开发版本"),
                    content=_tr("当前构建与最新 Release 不完全一致，可在关于页查看详情。"),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=5000,
                    parent=self.host.window(),
                )
            return

        self._latest_asset = None
        self._show_latest_state(
            current_version=result.current_version,
            tag_name=release.tag_name,
            published_at=self._format_release_time(release.published_at),
        )

    def _handle_update_failure(self, message: str) -> None:
        self._latest_asset = None
        if self._startup_silent_check:
            InfoBar.warning(
                title=_tr("自动检查更新失败"),
                content=message,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=5000,
                parent=self.host.window(),
            )
        else:
            self._show_update_failure_state(message)
            show_error_bar(self.host.window(), _tr("检查更新失败"), message)

    def _handle_update_finished(self) -> None:
        self.update_card.check_button.setEnabled(True)
        self.update_card.release_button.setEnabled(True)
        self._update_worker = None
        self._startup_silent_check = False

    def _handle_install_progress(self, received: int, total: int) -> None:
        if total > 0:
            percent = int(received * 100 / total)
            meta = _tr("已下载 {received} / {total} ({percent}%)").format(
                received=self._format_bytes(received),
                total=self._format_bytes(total),
                percent=percent,
            )
        else:
            meta = _tr("已下载 {received}").format(received=self._format_bytes(received))
        self._show_downloading_state(
            name="",
            note=_tr("下载完成后将自动退出当前程序，替换二进制并重新启动。"),
            meta=meta,
        )

    def _handle_install_success(self) -> None:
        self._show_downloaded_state(filename=os.path.basename(sys.executable))
        QTimer.singleShot(300, self._quit_application)

    def _handle_install_failure(self, message: str) -> None:
        self._show_download_failed_state(message)
        show_error_bar(self.host.window(), _tr("下载更新失败"), message)

    def _handle_install_finished(self) -> None:
        self._install_worker = None
        if QApplication.instance() is None:
            return
        self.update_card.check_button.setEnabled(True)
        self.update_card.release_button.setEnabled(True)

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
    def _format_bytes(value: int) -> str:
        units = ["B", "KB", "MB", "GB"]
        size = float(value)
        unit = units[0]
        for unit in units:
            if size < 1024 or unit == units[-1]:
                break
            size /= 1024
        return f"{size:.1f} {unit}"

    @staticmethod
    def _short_commit(commit_sha: str) -> str:
        stripped = commit_sha.strip()
        if not stripped or stripped == "unknown":
            return "unknown"
        return stripped[:8]

    @staticmethod
    def _format_release_time(value: str) -> str:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().strftime(
                DISPLAY_DATETIME_FORMAT
            )
        except ValueError:
            return value or "-"

    @staticmethod
    def _parse_repo(url: str) -> tuple[str, str]:
        parsed = urlparse(url)
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        if len(parts) >= 2:
            return parts[0], parts[1]
        return "SunAnICB", "open-router-key-viewer"

    @staticmethod
    def _default_quit_application() -> None:
        app = QApplication.instance()
        if app is not None:
            app.quit()
