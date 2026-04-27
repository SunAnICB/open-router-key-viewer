from __future__ import annotations

from pathlib import Path

from open_router_key_viewer.services.about_info import build_about_view_model
from open_router_key_viewer.services.build_info import BuildInfo
from open_router_key_viewer.services.installer import InstallInfo


def test_about_view_model_contains_version_and_links() -> None:
    install_root = Path("/tmp/open-router-key-viewer")
    model = build_about_view_model(
        build_info=BuildInfo(commit_sha="abcdef1234567890", dirty=False, source="git"),
        install_info=InstallInfo(
            is_binary_runtime=True,
            is_installed=True,
            current_is_installed=True,
            install_root=install_root,
            binary_path=install_root / "open-router-key-viewer",
            launcher_path=Path("/tmp/bin/open-router-key-viewer"),
            desktop_path=Path("/tmp/share/open-router-key-viewer.desktop"),
        ),
        binary_update_supported=True,
    )

    version_row = next(row for row in model.detail_rows if row.label == "版本")
    install_row = next(row for row in model.detail_rows if row.label == "安装状态")

    assert version_row.note == "abcdef12 · clean"
    assert install_row.value == "已安装"
    assert install_row.note == str(install_root)
    assert any(row.label == "仓库地址" and row.url for row in model.note_rows)
