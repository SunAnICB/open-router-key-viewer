from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any


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
        self._write(payload)
        return payload

    def save_flag(self, key: str, value: bool) -> dict[str, Any]:
        return self.save_value(key, value)

    def delete_value(self, key: str) -> None:
        payload = self.load()
        if not payload or key not in payload:
            return

        del payload[key]
        if payload:
            self._write(payload)
            return

        if self.config_path.exists():
            self.config_path.unlink()

    def delete_config_file(self) -> None:
        if self.config_path.exists():
            self.config_path.unlink()

    def delete_config_dir(self) -> None:
        if self.config_dir.exists():
            shutil.rmtree(self.config_dir)

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
                    entry["content"] = path.read_text(encoding="utf-8", errors="replace")
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
        with self.config_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.chmod(self.config_path, 0o600)
