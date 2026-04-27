from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DetailRowViewModel:
    label: str
    value: str
    note: str = ""
    url: str = ""


@dataclass(frozen=True, slots=True)
class AboutViewModel:
    title: str
    app_name: str
    version: str
    description: str
    details_title: str
    detail_rows: list[DetailRowViewModel]
    notes_title: str
    note_rows: list[DetailRowViewModel]
