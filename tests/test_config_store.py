from __future__ import annotations

import json
from pathlib import Path

from open_router_key_viewer.services.config_store import ConfigStore


def test_save_and_load_value(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    store = ConfigStore()

    payload = store.save_value("api_key", "sk-test")

    assert payload["api_key"] == "sk-test"
    assert store.load() == {"api_key": "sk-test"}
    assert store.config_path.exists()


def test_delete_last_value_removes_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    store = ConfigStore()
    store.save_value("api_key", "sk-test")

    store.delete_value("api_key")

    assert store.load() is None
    assert not store.config_path.exists()


def test_inspect_reports_files_and_loaded_config(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    store = ConfigStore()
    store.save_value("api_key", "sk-test")
    extra_file = store.config_dir / "notes.txt"
    extra_file.write_text("hello", encoding="utf-8")

    snapshot = store.inspect()

    assert snapshot["dir_exists"] is True
    assert snapshot["config_exists"] is True
    assert snapshot["loaded_config"] == {"api_key": "sk-test"}
    files = snapshot["files"]
    assert any(item["path"] == "config.json" for item in files)
    assert any(item["path"] == "notes.txt" and item["content"] == "hello" for item in files)


def test_read_raw_config_returns_exact_file_content(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    store = ConfigStore()
    store.config_dir.mkdir(parents=True, exist_ok=True)
    expected = {"api_key": "sk-test", "auto_check_updates": True}
    store.config_path.write_text(json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    raw = store.read_raw_config()

    assert raw == json.dumps(expected, ensure_ascii=False, indent=2) + "\n"
