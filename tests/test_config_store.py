from __future__ import annotations

import json
from pathlib import Path

import pytest

from open_router_key_viewer.services.config_store import ConfigStore, ConfigStoreError


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
    assert any(item["path"] == "notes.txt" and item["size"] == 5 for item in files)
    assert all("content" not in item for item in files)


def test_read_raw_config_returns_exact_file_content(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    store = ConfigStore()
    store.config_dir.mkdir(parents=True, exist_ok=True)
    expected = {"api_key": "sk-test", "auto_check_updates": True}
    store.config_path.write_text(json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    raw = store.read_raw_config()

    assert raw == json.dumps(expected, ensure_ascii=False, indent=2) + "\n"


def test_delete_config_file_raises_wrapped_error(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    store = ConfigStore()
    store.save_value("api_key", "sk-test")

    monkeypatch.setattr(Path, "unlink", lambda self: (_ for _ in ()).throw(OSError("denied")))

    with pytest.raises(ConfigStoreError, match="删除配置文件失败"):
        store.delete_config_file()


def test_delete_config_dir_raises_wrapped_error(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    store = ConfigStore()
    store.save_value("api_key", "sk-test")

    monkeypatch.setattr("open_router_key_viewer.services.config_store.shutil.rmtree", lambda path: (_ for _ in ()).throw(OSError("busy")))

    with pytest.raises(ConfigStoreError, match="删除缓存目录失败"):
        store.delete_config_dir()
