from __future__ import annotations

from dataclasses import dataclass

from open_router_key_viewer.state.app_config import AppConfig


@dataclass(frozen=True, slots=True)
class PathCardViewModel:
    title: str
    status: str
    note: str
    path: str
    exists: bool


@dataclass(frozen=True, slots=True)
class MetricViewModel:
    title: str
    value: str
    note: str


@dataclass(frozen=True, slots=True)
class SettingsSnapshotViewModel:
    config: AppConfig
    directory: PathCardViewModel
    config_file: PathCardViewModel
    file_count: MetricViewModel
    entry_count: MetricViewModel
    status: str
    parsed_rows: list[tuple[str, str, str]]
    raw_file_text: str
