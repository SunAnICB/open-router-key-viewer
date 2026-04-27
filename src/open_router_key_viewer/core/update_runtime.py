from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from open_router_key_viewer import __version__
from open_router_key_viewer.services.build_info import BuildInfo, get_build_info
from open_router_key_viewer.services.installer import AppInstaller, InstallInfo
from open_router_key_viewer.services.update_checker import BinaryUpdater, GitHubReleaseChecker
from open_router_key_viewer.state.app_metadata import APP_REPOSITORY_URL, BINARY_ASSET_NAME


@dataclass(frozen=True, slots=True)
class UpdateRuntimeContext:
    build_info: BuildInfo
    binary_update_supported: bool
    install_info: InstallInfo
    binary_updater: BinaryUpdater | None
    release_checker: GitHubReleaseChecker
    release_url: str


def build_update_runtime_context() -> UpdateRuntimeContext:
    binary_update_supported = bool(getattr(sys, "frozen", False))
    current_binary = Path(sys.executable)
    install_info = AppInstaller(current_binary, is_binary_runtime=binary_update_supported).inspect()
    relaunch_command = [str(install_info.launcher_path)] if install_info.current_is_installed else None
    binary_updater = (
        BinaryUpdater(current_binary, relaunch_command=relaunch_command) if binary_update_supported else None
    )
    if binary_updater is not None:
        binary_updater.cleanup_stale_updates()
    owner, repo = _parse_repo(APP_REPOSITORY_URL)
    return UpdateRuntimeContext(
        build_info=get_build_info(),
        binary_update_supported=binary_update_supported,
        install_info=install_info,
        binary_updater=binary_updater,
        release_checker=GitHubReleaseChecker(
            owner,
            repo,
            asset_name=BINARY_ASSET_NAME,
            current_version=__version__,
        ),
        release_url=APP_REPOSITORY_URL + "/releases",
    )


def _parse_repo(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) >= 2:
        return parts[0], parts[1]
    return "SunAnICB", "open-router-key-viewer"
