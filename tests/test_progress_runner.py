from __future__ import annotations

from open_router_key_viewer.core.progress_runner import ProgressRunner
from open_router_key_viewer.state.progress import ProgressState, ProgressStep, step_by_id


def test_progress_runner_reports_before_action_and_processes_events() -> None:
    events: list[str] = []
    states: list[ProgressState] = []
    step = ProgressStep("load", 40, "Loading", "Details")
    runner = ProgressRunner(
        lambda state: states.append(state),
        process_events=lambda: events.append("pump"),
    )

    result = runner.run(step, lambda: events.append("action") or "done")

    assert result == "done"
    assert states == [ProgressState(40, "Loading", "Details")]
    assert events == ["pump", "action", "pump"]


def test_step_by_id_returns_matching_step() -> None:
    steps = (
        ProgressStep("a", 10, "A"),
        ProgressStep("b", 20, "B"),
    )

    assert step_by_id(steps, "b") == ProgressStep("b", 20, "B")
