from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


class ConfigStoreError(Exception):
    """Raised when config file operations fail."""


class ConfigStore:
    def __init__(self) -> None:
        self.config_dir = Path.home() / ".config" / "open-router-key-viewer"
        self.config_path = self.config_dir / "config.json"

    def load(self) -> dict[str, Any] | None:
        if not self.config_path.exists():
            return None

        try:
            with self.config_path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
        except (OSError, json.JSONDecodeError):
            return None

        if not isinstance(payload, dict):
            return None
        return payload

    def save_value(self, key: str, value: Any) -> dict[str, Any]:
        payload = self.load() or {}
        payload[key] = value
        try:
            self._write(payload)
        except OSError as exc:
            raise ConfigStoreError(f"保存配置失败：{exc}") from exc
        return payload

    def save_flag(self, key: str, value: bool) -> dict[str, Any]:
        return self.save_value(key, value)

    def delete_value(self, key: str) -> None:
        payload = self.load()
        if not payload or key not in payload:
            return

        del payload[key]
        try:
            if payload:
                self._write(payload)
                return

            if self.config_path.exists():
                self.config_path.unlink()
        except OSError as exc:
            raise ConfigStoreError(f"删除配置项失败：{exc}") from exc

    def delete_config_file(self) -> None:
        try:
            if self.config_path.exists():
                self.config_path.unlink()
        except OSError as exc:
            raise ConfigStoreError(f"删除配置文件失败：{exc}") from exc

    def delete_config_dir(self) -> None:
        try:
            if self.config_dir.exists():
                shutil.rmtree(self.config_dir)
        except OSError as exc:
            raise ConfigStoreError(f"删除缓存目录失败：{exc}") from exc

    def inspect(self) -> dict[str, Any]:
        exists = self.config_dir.exists()
        files: list[dict[str, Any]] = []

        if exists:
            for path in sorted(self.config_dir.rglob("*")):
                relative = path.relative_to(self.config_dir)
                entry: dict[str, Any] = {
                    "path": str(relative) or ".",
                    "type": "directory" if path.is_dir() else "file",
                }
                if path.is_file():
                    entry["size"] = path.stat().st_size
                files.append(entry)

        return {
            "config_dir": str(self.config_dir),
            "config_path": str(self.config_path),
            "dir_exists": exists,
            "config_exists": self.config_path.exists(),
            "loaded_config": self.load(),
            "files": files,
        }

    def read_raw_config(self) -> str | None:
        if not self.config_path.exists():
            return None
        try:
            return self.config_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    def _write(self, payload: dict[str, Any]) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix="config-", suffix=".json.tmp", dir=self.config_dir)
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.chmod(temp_path, 0o600)
            os.replace(temp_path, self.config_path)
        except OSError:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise
