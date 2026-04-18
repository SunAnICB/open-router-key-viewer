from __future__ import annotations

from pathlib import Path

import pytest

from open_router_key_viewer.services.installer import (
    APP_BINARY_NAME,
    APP_ICON_NAME,
    AppInstallError,
    AppInstaller,
)


def test_install_to_creates_binary_launcher_and_desktop(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    current_binary = tmp_path / "portable" / APP_BINARY_NAME
    current_binary.parent.mkdir(parents=True, exist_ok=True)
    current_binary.write_bytes(b"binary")

    installer = AppInstaller(current_binary, is_binary_runtime=True)
    icon_source = tmp_path / "assets" / APP_ICON_NAME
    icon_source.parent.mkdir(parents=True, exist_ok=True)
    icon_source.write_text("<svg />", encoding="utf-8")
    monkeypatch.setattr(installer, "_resolve_icon_source", lambda: icon_source)

    info = installer.install(app_display_name="OpenRouter Key Viewer")

    assert info.is_installed is True
    assert info.install_root == tmp_path / ".local" / "opt" / APP_BINARY_NAME
    assert (info.install_root / APP_BINARY_NAME).read_bytes() == b"binary"
    launcher_text = installer.launcher_path.read_text(encoding="utf-8")
    assert f'APP="{info.install_root / APP_BINARY_NAME}"' in launcher_text
    assert 'nohup "$APP" "$@" >/dev/null 2>/dev/null </dev/null &' in launcher_text
    desktop_text = installer.desktop_path.read_text(encoding="utf-8")
    assert "OpenRouter Key Viewer" in desktop_text
    assert str(installer.launcher_path) in desktop_text
    assert installer.inspect().is_installed is True


def test_install_rejects_source_runtime(tmp_path: Path) -> None:
    installer = AppInstaller(tmp_path / APP_BINARY_NAME, is_binary_runtime=False)

    with pytest.raises(AppInstallError):
        installer.install(app_display_name="OpenRouter Key Viewer")


def test_uninstall_removes_installed_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    current_binary = tmp_path / "portable" / APP_BINARY_NAME
    current_binary.parent.mkdir(parents=True, exist_ok=True)
    current_binary.write_bytes(b"binary")

    installer = AppInstaller(current_binary, is_binary_runtime=True)
    icon_source = tmp_path / "assets" / APP_ICON_NAME
    icon_source.parent.mkdir(parents=True, exist_ok=True)
    icon_source.write_text("<svg />", encoding="utf-8")
    monkeypatch.setattr(installer, "_resolve_icon_source", lambda: icon_source)

    installer.install(app_display_name="OpenRouter Key Viewer")
    installer.uninstall()

    assert not installer.install_root.exists()
    assert not installer.launcher_path.exists()
    assert not installer.desktop_path.exists()
    assert not installer.icon_path.exists()
