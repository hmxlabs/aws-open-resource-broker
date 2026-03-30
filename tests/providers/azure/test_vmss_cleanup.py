from unittest.mock import MagicMock

from orb.providers.azure.infrastructure.vmss_cleanup import (
    PendingVmssCleanup,
    VmssCleanupCoordinator,
)


def test_pending_vmss_cleanup_round_trips_metadata():
    cleanup = PendingVmssCleanup.create(
        resource_group="test-rg",
        vmss_name="vmss-demo",
        machine_ids=["vm-a", "vm-a", "vm-b"],
        delete_vmss_when_empty=True,
        delete_retry_pending=True,
        last_delete_error="transient delete failure",
    )

    restored = PendingVmssCleanup.from_metadata(cleanup.to_metadata())

    assert restored is not None
    assert restored.to_metadata() == {
        "resource_group": "test-rg",
        "vmss_name": "vmss-demo",
        "machine_ids": ["vm-a", "vm-b"],
        "delete_vmss_when_empty": True,
        "delete_submission_semantics": "best_effort_without_reverification",
        "delete_submitted": False,
        "delete_retry_pending": True,
        "last_delete_error": "transient delete failure",
    }


def test_pending_vmss_cleanup_merge_preserves_ids_and_retry_state():
    base = PendingVmssCleanup.from_metadata(
        {
            "resource_group": "test-rg",
            "vmss_name": "vmss-demo",
            "machine_ids": ["vm-a"],
            "delete_vmss_when_empty": True,
        }
    )
    update = PendingVmssCleanup.from_metadata(
        {
            "resource_group": "test-rg",
            "vmss_name": "vmss-demo",
            "machine_ids": ["vm-b"],
            "delete_vmss_when_empty": True,
            "delete_retry_pending": True,
            "last_delete_error": "still deleting",
        }
    )

    assert base is not None
    assert update is not None

    merged = base.combine_for_same_vmss(update)

    assert merged.to_status_detail() == {
        "resource_group": "test-rg",
        "vmss_name": "vmss-demo",
        "machine_ids": ["vm-a", "vm-b"],
        "delete_vmss_when_empty": True,
        "delete_submission_semantics": "best_effort_without_reverification",
        "delete_submitted": False,
        "delete_retry_pending": True,
        "last_delete_error": "still deleting",
    }


def test_vmss_cleanup_coordinator_reconciles_delete_retry_state():
    logger = MagicMock()
    coordinator = VmssCleanupCoordinator(
        logger=logger,
        get_vmss_member_count=lambda **_: 0,
        vmss_exists=lambda **_: True,
        begin_delete_vmss=lambda **_: (_ for _ in ()).throw(RuntimeError("delete blocked")),
    )

    coordinator.record(
        {
            "provider_data": {
                "pending_vmss_cleanup": {
                    "resource_group": "test-rg",
                    "vmss_name": "vmss-demo",
                    "machine_ids": ["vm-a"],
                    "delete_vmss_when_empty": True,
                }
            }
        }
    )

    coordinator.reconcile(
        resource_group="test-rg",
        resource_ids=["vmss-demo"],
        observed_ids=set(),
    )

    assert coordinator.status_metadata(
        resource_group="test-rg",
        resource_ids=["vmss-demo"],
    ) == {
        "termination_follow_up_pending": True,
        "termination_follow_up_details": [
            {
                "resource_group": "test-rg",
                "vmss_name": "vmss-demo",
                "machine_ids": ["vm-a"],
                "delete_vmss_when_empty": True,
                "delete_submission_semantics": "best_effort_without_reverification",
                "delete_submitted": False,
                "delete_retry_pending": True,
                "last_delete_error": "delete blocked",
            }
        ],
    }
    logger.warning.assert_called_once()
