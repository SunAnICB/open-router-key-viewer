from __future__ import annotations

import uuid

from PySide6.QtCore import QCoreApplication

from open_router_key_viewer.services.single_instance import SingleInstanceManager


def test_single_instance_manager_activates_existing_instance(qapp) -> None:
    _ = qapp
    app_id = f"open-router-key-viewer-test-{uuid.uuid4().hex}"
    first = SingleInstanceManager(app_id)
    activations: list[str] = []
    first.activation_requested.connect(lambda: activations.append("activate"))

    assert first.start_or_activate_existing() is True

    second = SingleInstanceManager(app_id)
    assert second.start_or_activate_existing() is False

    deadline = 50
    while not activations and deadline > 0:
        QCoreApplication.processEvents()
        deadline -= 1

    assert activations == ["activate"]
    first.close()
    second.close()


def test_single_instance_manager_prevents_parallel_start(qapp) -> None:
    _ = qapp
    app_id = f"open-router-key-viewer-test-{uuid.uuid4().hex}"
    first = SingleInstanceManager(app_id)
    third = SingleInstanceManager(app_id)

    assert first.start_or_activate_existing() is True
    assert third.start_or_activate_existing() is False

    first.close()
    third.close()
