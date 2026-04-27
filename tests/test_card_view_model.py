from __future__ import annotations

from pathlib import Path

from open_router_key_viewer.services.installer import InstallInfo
from open_router_key_viewer.state import (
    build_asset_note,
    build_install_state,
    build_update_intro_state,
)


def test_update_intro_state_differs_by_runtime() -> None:
    binary_state = build_update_intro_state(True)
    source_state = build_update_intro_state(False)

    assert binary_state.title.source == "可检查二进制更新"
    assert binary_state.can_open_release is True
    assert source_state.title.source == "可检查更新"
    assert source_state.can_replace is False


def test_asset_note_keeps_template_arguments() -> None:
    note = build_asset_note("open-router-key-viewer")

    assert note.source == "下载文件：{name}"
    assert note.args["name"] == "open-router-key-viewer"


def test_install_state_for_installed_binary() -> None:
    install_root = Path("/tmp/open-router-key-viewer")
    info = InstallInfo(
        is_binary_runtime=True,
        is_installed=True,
        current_is_installed=True,
        install_root=install_root,
        binary_path=install_root / "open-router-key-viewer",
        launcher_path=Path("/tmp/bin/open-router-key-viewer"),
        desktop_path=Path("/tmp/share/applications/open-router-key-viewer.desktop"),
    )

    state = build_install_state(info, install_root)

    assert state.title.source == "已安装"
    assert state.can_open_directory is True
    assert state.can_remove is True
    assert state.install_button_text is not None
    assert state.install_button_text.source == "重新安装到固定位置"
