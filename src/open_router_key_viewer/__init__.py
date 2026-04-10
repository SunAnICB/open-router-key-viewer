"""OpenRouter key viewer."""

from importlib.metadata import PackageNotFoundError, version

__all__ = ["__version__"]

try:
    __version__ = version("open-router-key-viewer")
except PackageNotFoundError:
    __version__ = "0.0.0"
