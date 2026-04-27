from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from open_router_key_viewer.state.progress import ProgressState, ProgressStep

T = TypeVar("T")


class ProgressRunner:
    """Run synchronous initialization steps while reporting progress."""

    def __init__(
        self,
        on_progress: Callable[[ProgressState], None],
        *,
        process_events: Callable[[], None] | None = None,
    ) -> None:
        self.on_progress = on_progress
        self.process_events = process_events or (lambda: None)

    def update(self, step: ProgressStep) -> None:
        self.on_progress(ProgressState(step.percent, step.message, step.detail))
        self.process_events()

    def run(self, step: ProgressStep, action: Callable[[], T]) -> T:
        self.update(step)
        result = action()
        self.process_events()
        return result
