from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


APP_BINARY_NAME = "open-router-key-viewer"
APP_ICON_NAME = "open-router-key-viewer.svg"
INSTALL_MANIFEST_NAME = ".open-router-key-viewer-install.json"


class AppInstallError(Exception):
    """Raised when installing the application fails."""


@dataclass(slots=True)
class InstallInfo:
    is_binary_runtime: bool
    is_installed: bool
    current_is_installed: bool
    install_root: Path | None
    binary_path: Path | None
    launcher_path: Path
    desktop_path: Path


class AppInstaller:
    """Install the current binary into a fixed user-local directory."""

    def __init__(self, current_binary: Path, *, is_binary_runtime: bool) -> None:
        self.current_binary = current_binary
        self.is_binary_runtime = is_binary_runtime
        self.install_root = Path.home() / ".local" / "opt" / APP_BINARY_NAME
        self.binary_path = self.install_root / APP_BINARY_NAME
        self.manifest_path = self.install_root / INSTALL_MANIFEST_NAME
        self.launcher_path = Path.home() / ".local" / "bin" / APP_BINARY_NAME
        self.desktop_path = Path.home() / ".local" / "share" / "applications" / f"{APP_BINARY_NAME}.desktop"
        self.icon_path = Path.home() / ".local" / "share" / "icons" / "hicolor" / "scalable" / "apps" / APP_ICON_NAME

    def inspect(self) -> InstallInfo:
        installed = self.binary_path.exists() and self.manifest_path.exists()
        current_is_installed = False
        if installed and self.current_binary.exists():
            try:
                current_is_installed = self.current_binary.resolve() == self.binary_path.resolve()
            except OSError:
                current_is_installed = False

        if not self.is_binary_runtime or not self.current_binary.exists():
            return InstallInfo(
                is_binary_runtime=False,
                is_installed=installed,
                current_is_installed=current_is_installed,
                install_root=self.install_root if installed else None,
                binary_path=self.binary_path if installed else None,
                launcher_path=self.launcher_path,
                desktop_path=self.desktop_path,
            )

        return InstallInfo(
            is_binary_runtime=True,
            is_installed=installed,
            current_is_installed=current_is_installed,
            install_root=self.install_root if installed else None,
            binary_path=self.binary_path if installed else None,
            launcher_path=self.launcher_path,
            desktop_path=self.desktop_path,
        )

    def install(self, *, app_display_name: str) -> InstallInfo:
        if not self.is_binary_runtime or not self.current_binary.exists():
            raise AppInstallError("当前不是可安装的二进制运行模式。")

        if self.install_root.exists() and self.install_root.is_file():
            raise AppInstallError("固定安装路径被文件占用，无法继续安装。")

        current_is_target = self._is_same_path(self.current_binary, self.binary_path)
        previously_installed = self.binary_path.exists() and self.manifest_path.exists()
        created_paths: list[Path] = []
        backup_dir: Path | None = None
        backups: dict[Path, Path] = {}

        try:
            if previously_installed:
                backup_dir = Path(tempfile.mkdtemp(prefix="install-backup-", dir=self.install_root.parent))
                backups = self._backup_existing_install(backup_dir)

            self.install_root.mkdir(parents=True, exist_ok=True)
            if not current_is_target:
                shutil.copy2(self.current_binary, self.binary_path)
                created_paths.append(self.binary_path)
            os.chmod(self.binary_path, 0o755)

            self.launcher_path.parent.mkdir(parents=True, exist_ok=True)
            self.launcher_path.write_text(self._launcher_script(self.binary_path), encoding="utf-8")
            created_paths.append(self.launcher_path)
            os.chmod(self.launcher_path, 0o755)

            icon_source = self._resolve_icon_source()
            self.icon_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(icon_source, self.icon_path)
            created_paths.append(self.icon_path)

            self.desktop_path.parent.mkdir(parents=True, exist_ok=True)
            self.desktop_path.write_text(
                self._desktop_file(app_display_name, self.launcher_path, self.icon_path),
                encoding="utf-8",
            )
            created_paths.append(self.desktop_path)

            self.manifest_path.write_text(
                json.dumps(
                    {
                        "install_root": str(self.install_root),
                        "binary_path": str(self.binary_path),
                        "launcher_path": str(self.launcher_path),
                        "desktop_path": str(self.desktop_path),
                        "icon_path": str(self.icon_path),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            created_paths.append(self.manifest_path)
        except OSError as exc:
            if previously_installed:
                self._restore_install_backup(backups)
            else:
                self._rollback_install(created_paths)
            raise AppInstallError(f"安装失败：{exc}") from exc
        finally:
            if backup_dir is not None:
                shutil.rmtree(backup_dir, ignore_errors=True)

        return InstallInfo(
            is_binary_runtime=True,
            is_installed=True,
            current_is_installed=current_is_target,
            install_root=self.install_root,
            binary_path=self.binary_path,
            launcher_path=self.launcher_path,
            desktop_path=self.desktop_path,
        )

    def uninstall(self) -> None:
        try:
            if self.launcher_path.exists():
                self.launcher_path.unlink()
            if self.desktop_path.exists():
                self.desktop_path.unlink()
            if self.icon_path.exists():
                self.icon_path.unlink()
            if self.install_root.exists():
                shutil.rmtree(self.install_root)
        except OSError as exc:
            raise AppInstallError(f"移除安装失败：{exc}") from exc

    def _rollback_install(self, created_paths: list[Path]) -> None:
        for path in reversed(created_paths):
            try:
                if path.is_file() or path.is_symlink():
                    path.unlink(missing_ok=True)
            except OSError:
                continue
        self._remove_empty_parents(self.launcher_path.parent)
        self._remove_empty_parents(self.desktop_path.parent)
        self._remove_empty_parents(self.icon_path.parent)
        self._remove_empty_parents(self.install_root)

    def _backup_existing_install(self, backup_dir: Path) -> dict[Path, Path]:
        backups: dict[Path, Path] = {}
        for index, path in enumerate(self._managed_install_paths()):
            if not path.exists():
                continue
            backup_path = backup_dir / f"{index}-{path.name}"
            shutil.copy2(path, backup_path)
            backups[path] = backup_path
        return backups

    def _restore_install_backup(self, backups: dict[Path, Path]) -> None:
        for path in self._managed_install_paths():
            backup_path = backups.get(path)
            if backup_path is None:
                try:
                    if path.exists():
                        path.unlink()
                except OSError:
                    continue
                continue
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup_path, path)
            except OSError:
                continue

    def _resolve_icon_source(self) -> Path:
        candidates = [
            self.current_binary.parent / "assets" / APP_ICON_NAME,
            Path(getattr(sys, "_MEIPASS", self.current_binary.parent)) / "assets" / APP_ICON_NAME,
            Path(__file__).resolve().parents[3] / "assets" / APP_ICON_NAME,
            Path.cwd() / "assets" / APP_ICON_NAME,
        ]
        for path in candidates:
            if path.exists():
                return path
        raise AppInstallError("未找到安装所需图标资源。")

    def _managed_install_paths(self) -> tuple[Path, ...]:
        return (
            self.binary_path,
            self.launcher_path,
            self.icon_path,
            self.desktop_path,
            self.manifest_path,
        )

    @staticmethod
    def _is_same_path(left: Path, right: Path) -> bool:
        try:
            return left.resolve() == right.resolve()
        except OSError:
            return False

    @staticmethod
    def _remove_empty_parents(path: Path) -> None:
        for candidate in (path, *path.parents):
            if candidate == candidate.parent:
                break
            try:
                candidate.rmdir()
            except OSError:
                break

    @staticmethod
    def _launcher_script(binary_path: Path) -> str:
        return (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n\n"
            f'APP="{binary_path}"\n'
            'PYINSTALLER_RESET_ENVIRONMENT=1 nohup "$APP" "$@" >/dev/null 2>/dev/null </dev/null &\n'
        )

    @staticmethod
    def _desktop_file(app_display_name: str, launcher_path: Path, icon_path: Path) -> str:
        return (
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={app_display_name}\n"
            f"Exec={launcher_path}\n"
            f"Icon={icon_path}\n"
            "Terminal=false\n"
            "Categories=Utility;\n"
        )
