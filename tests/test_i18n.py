from __future__ import annotations

import ast
from pathlib import Path

import pytest
from PySide6.QtCore import QLocale

import open_router_key_viewer.i18n as i18n_module
from open_router_key_viewer.i18n import _TRANSLATIONS, resolve_language_code
from open_router_key_viewer.ui.runtime import resolve_theme_mode


def _collect_translation_keys() -> set[str]:
    root = Path(__file__).resolve().parents[1] / "src" / "open_router_key_viewer"
    keys: set[str] = set()
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not node.args:
                continue
            func = node.func
            if isinstance(func, ast.Name) and func.id in {"_tr", "tr"}:
                first_arg = node.args[0]
                if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                    keys.add(first_arg.value)
    return keys


def test_all_used_translation_keys_exist_in_non_default_languages() -> None:
    used_keys = _collect_translation_keys()

    for language_code in ("en", "zh_TW"):
        missing = sorted(key for key in used_keys if key not in _TRANSLATIONS[language_code])
        assert missing == []


def test_resolve_language_code_prefers_explicit_supported_value() -> None:
    assert resolve_language_code("en") == "en"
    assert resolve_language_code("zh_TW") == "zh_TW"


def test_resolve_language_code_uses_system_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(QLocale, "system", lambda: QLocale("zh_HK"))
    assert resolve_language_code(None) == "zh_TW"

    monkeypatch.setattr(QLocale, "system", lambda: QLocale("en_US"))
    assert resolve_language_code(None) == "en"

    monkeypatch.setattr(i18n_module.QLocale, "system", lambda: QLocale("fr_FR"))
    assert resolve_language_code(None) == "zh_CN"


def test_resolve_theme_mode_prefers_supported_value() -> None:
    assert resolve_theme_mode("auto") == "auto"
    assert resolve_theme_mode("light") == "light"
    assert resolve_theme_mode("dark") == "dark"
    assert resolve_theme_mode("unknown") == "auto"
    assert resolve_theme_mode(None) == "auto"
