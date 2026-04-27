from __future__ import annotations

from open_router_key_viewer.services.about_info import build_about_view_model
from open_router_key_viewer.services.build_info import BuildInfo, get_build_info
from open_router_key_viewer.services.installer import InstallInfo
from open_router_key_viewer.state.about_view_model import AboutViewModel


class AboutCoordinator:
    """Own about-page metadata and view model construction."""

    def __init__(self, build_info: BuildInfo | None = None) -> None:
        self.build_info = build_info or get_build_info()

    def build_view_model(
        self,
        *,
        install_info: InstallInfo,
        binary_update_supported: bool,
    ) -> AboutViewModel:
        return build_about_view_model(
            build_info=self.build_info,
            install_info=install_info,
            binary_update_supported=binary_update_supported,
        )
