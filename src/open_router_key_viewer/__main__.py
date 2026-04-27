from __future__ import annotations

import os

from open_router_key_viewer.services.config_store import ConfigStore


DISPLAY_BACKEND_OPTIONS = {"auto", "wayland", "x11"}


def _apply_display_backend() -> None:
    if os.environ.get("QT_QPA_PLATFORM"):
        return

    backend = ConfigStore().load_config().display_backend
    if backend not in DISPLAY_BACKEND_OPTIONS:
        return

    mapping = {
        "auto": "",
        "wayland": "wayland",
        "x11": "xcb",
    }
    platform = mapping.get(backend, "")
    if platform:
        os.environ["QT_QPA_PLATFORM"] = platform


_apply_display_backend()

from open_router_key_viewer.app import main

if __name__ == "__main__":
    raise SystemExit(main())
