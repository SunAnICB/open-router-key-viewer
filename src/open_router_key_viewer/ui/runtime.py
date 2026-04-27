from __future__ import annotations

import io
from contextlib import redirect_stdout

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

with redirect_stdout(io.StringIO()):
    from qfluentwidgets import InfoBar, InfoBarPosition, Theme, setTheme

from open_router_key_viewer.i18n import DictTranslator, tr
from open_router_key_viewer.state.app_metadata import THEME_MODE_OPTIONS


def format_currency_value(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"${value:.4f}"
    return "-"


def install_language(app: QApplication, language_code: str) -> None:
    translator = getattr(app, "_dict_translator", None)
    if translator is not None:
        app.removeTranslator(translator)

    new_translator = DictTranslator(language_code)
    app.installTranslator(new_translator)
    app._dict_translator = new_translator  # type: ignore[attr-defined]


def resolve_theme_mode(config_value: object) -> str:
    if isinstance(config_value, str) and config_value in {code for code, _ in THEME_MODE_OPTIONS}:
        return config_value
    return "auto"


def apply_theme_mode(theme_mode: str) -> None:
    resolved = resolve_theme_mode(theme_mode)
    mapping = {
        "auto": Theme.AUTO,
        "light": Theme.LIGHT,
        "dark": Theme.DARK,
    }
    setTheme(mapping.get(resolved, Theme.AUTO))


def show_error_bar(parent: QWidget, title: str, message: str) -> None:
    InfoBar.error(
        title=title,
        content=message,
        orient=Qt.Orientation.Horizontal,
        isClosable=True,
        position=InfoBarPosition.TOP_RIGHT,
        duration=3000,
        parent=parent,
    )
