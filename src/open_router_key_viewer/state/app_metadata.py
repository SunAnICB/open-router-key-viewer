from __future__ import annotations

APP_DISPLAY_NAME = "OpenRouter Key Viewer"
APP_AUTHOR = "SunAnICB"
APP_AUTHOR_URL = "https://github.com/SunAnICB"
APP_REPOSITORY_URL = "https://github.com/SunAnICB/open-router-key-viewer"
APP_LICENSE_NAME = "MIT"
APP_DATA_SOURCE_URL = "https://openrouter.ai/docs/api-reference/overview"
BINARY_ASSET_NAME = "open-router-key-viewer"
DISPLAY_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
DISPLAY_BACKEND_OPTIONS: list[tuple[str, str]] = [
    ("auto", "自动"),
    ("wayland", "Wayland"),
    ("x11", "X11"),
]
THEME_MODE_OPTIONS: list[tuple[str, str]] = [
    ("auto", "跟随系统"),
    ("light", "浅色"),
    ("dark", "深色"),
]
