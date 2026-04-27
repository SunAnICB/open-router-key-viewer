from __future__ import annotations

import sys
from pathlib import Path

from open_router_key_viewer.core.install_coordinator import InstallCoordinator
from open_router_key_viewer.services.installer import AppInstaller


def build_install_coordinator() -> InstallCoordinator:
    """Create the install coordinator for the current runtime."""
    return InstallCoordinator(
        AppInstaller(Path(sys.executable), is_binary_runtime=bool(getattr(sys, "frozen", False)))
    )
