from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from open_router_key_viewer.services.installer import AppInstallError, AppInstaller, InstallInfo
from open_router_key_viewer.state import InstallCardViewModel, build_install_state


@dataclass(frozen=True, slots=True)
class InstallActionResult:
    ok: bool
    info: InstallInfo
    view_model: InstallCardViewModel
    message: str = ""


class InstallCoordinator:
    """Own installed-copy inspection, install, and uninstall operations."""

    def __init__(self, installer: AppInstaller) -> None:
        self.installer = installer
        self.install_info = self.installer.inspect()

    @property
    def install_root(self) -> Path:
        return self.installer.install_root

    def current_view_model(self) -> InstallCardViewModel:
        return build_install_state(self.install_info, self.installer.install_root)

    def refresh(self) -> InstallCardViewModel:
        self.install_info = self.installer.inspect()
        return self.current_view_model()

    def install_or_upgrade(self, app_display_name: str) -> InstallActionResult:
        try:
            self.install_info = self.installer.install(app_display_name=app_display_name)
        except AppInstallError as exc:
            return self._error(exc)
        return InstallActionResult(True, self.install_info, self.current_view_model())

    def remove_installation(self) -> InstallActionResult:
        try:
            self.installer.uninstall()
            self.install_info = self.installer.inspect()
        except (AppInstallError, OSError) as exc:
            return self._error(exc)
        return InstallActionResult(True, self.install_info, self.current_view_model())

    def _error(self, exc: Exception) -> InstallActionResult:
        return InstallActionResult(False, self.install_info, self.current_view_model(), str(exc))
