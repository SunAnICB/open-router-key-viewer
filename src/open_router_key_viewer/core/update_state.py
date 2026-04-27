from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from open_router_key_viewer.services.build_info import BuildInfo
from open_router_key_viewer.services.update_checker import BinaryUpdater, ReleaseAsset, UpdateCheckResult
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
from open_router_key_viewer.state.app_metadata import DISPLAY_DATETIME_FORMAT


@dataclass(frozen=True, slots=True)
class UpdateStatus:
    view_model: UpdateCardViewModel
    notification_title: str = ""
    notification_message: str = ""
    warning: bool = False


@dataclass(frozen=True, slots=True)
class ReplacementPlan:
    ok: bool
    asset: ReleaseAsset | None = None
    error: str = ""


class UpdateStateMachine:
    """Own update result interpretation and card state transitions."""

    def __init__(
        self,
        *,
        build_info: BuildInfo,
        binary_update_supported: bool,
        binary_updater: BinaryUpdater | None,
    ) -> None:
        self.build_info = build_info
        self.binary_update_supported = binary_update_supported
        self.binary_updater = binary_updater
        self.latest_asset: ReleaseAsset | None = None
        self.release_url = ""

    def intro(self) -> UpdateStatus:
        return UpdateStatus(build_update_intro_state(self.binary_update_supported))

    def checking(self) -> UpdateStatus:
        return UpdateStatus(build_update_checking_state())

    def handle_check_success(self, result: UpdateCheckResult, *, silent: bool) -> UpdateStatus:
        release = result.latest_release
        self.release_url = release.html_url
        self.latest_asset = release.asset
        asset_note = build_asset_note(release.asset.name if release.asset is not None else None)
        can_replace = bool(result.update_available and self.binary_update_supported and release.asset is not None)
        replace_note = ""
        if can_replace and self.binary_updater is not None:
            supported, reason = self.binary_updater.can_replace_current_binary()
            can_replace = supported
            if reason:
                replace_note = f"  {reason}"
        if result.update_available:
            status = UpdateStatus(
                build_update_available_state(
                    current_version=result.current_version,
                    release_version=release.version,
                    asset_note=asset_note,
                    published_at=self._format_release_time(release.published_at),
                    replace_note=replace_note,
                    can_replace=can_replace,
                )
            )
            if silent:
                return UpdateStatus(
                    status.view_model,
                    notification_title="发现新版本",
                    notification_message="检测到 v{version} 可用，可在关于页查看并更新。".format(version=release.version),
                )
            return status

        if self._is_dev_build(result):
            commit_note: TextSpec | None = None
            if release.commit_sha:
                commit_note = build_commit_note(
                    self._short_commit(self.build_info.commit_sha),
                    self._short_commit(release.commit_sha),
                )
            self.latest_asset = None
            status = UpdateStatus(
                build_dev_build_state(
                    current_version=result.current_version,
                    release_version=release.version,
                    tag_name=release.tag_name,
                    published_at=self._format_release_time(release.published_at),
                    commit_note=commit_note,
                )
            )
            if silent:
                return UpdateStatus(
                    status.view_model,
                    notification_title="当前是开发版本",
                    notification_message="当前构建与最新 Release 不完全一致，可在关于页查看详情。",
                )
            return status

        self.latest_asset = None
        return UpdateStatus(
            build_latest_state(
                current_version=result.current_version,
                tag_name=release.tag_name,
                published_at=self._format_release_time(release.published_at),
            )
        )

    def handle_check_failure(self, message: str, *, silent: bool) -> UpdateStatus:
        self.latest_asset = None
        if silent:
            return UpdateStatus(
                build_update_failure_state(message),
                notification_title="自动检查更新失败",
                notification_message=message,
                warning=True,
            )
        return UpdateStatus(build_update_failure_state(message))

    def downloading(self, *, name: str, meta: str, note: str | None = None) -> UpdateStatus:
        return UpdateStatus(
            build_downloading_state(
                name=name,
                note=TextSpec(note) if note is not None else None,
                meta=TextSpec(meta),
            )
        )

    def download_progress(self, *, received: int, total: int) -> UpdateStatus:
        if total > 0:
            percent = int(received * 100 / total)
            meta = "已下载 {received} / {total} ({percent}%)".format(
                received=self._format_bytes(received),
                total=self._format_bytes(total),
                percent=percent,
            )
        else:
            meta = "已下载 {received}".format(received=self._format_bytes(received))
        return self.downloading(
            name="",
            note="下载完成后将自动退出当前程序，替换二进制并重新启动。",
            meta=meta,
        )

    def downloaded(self, *, filename: str) -> UpdateStatus:
        return UpdateStatus(build_downloaded_state(filename=filename))

    def prepare_replacement(self) -> ReplacementPlan:
        if not self.binary_update_supported or self.binary_updater is None:
            return ReplacementPlan(False, error="当前运行方式不支持直接替换二进制文件")
        if self.latest_asset is None:
            return ReplacementPlan(False, error="当前未找到可替换的二进制更新文件")
        supported, reason = self.binary_updater.can_replace_current_binary()
        if not supported:
            return ReplacementPlan(False, error=reason or "当前环境不支持替换二进制文件")
        return ReplacementPlan(True, asset=self.latest_asset)

    def download_failed(self, message: str) -> UpdateStatus:
        return UpdateStatus(
            build_download_failed_state(
                message,
                binary_update_supported=self.binary_update_supported,
                has_asset=self.latest_asset is not None,
            )
        )

    def _is_dev_build(self, result: UpdateCheckResult) -> bool:
        release = result.latest_release
        return bool(
            result.version_comparison < 0
            or self.build_info.dirty
            or (
                bool(release.commit_sha)
                and self.build_info.commit_sha != "unknown"
                and self.build_info.commit_sha != release.commit_sha
            )
        )

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
