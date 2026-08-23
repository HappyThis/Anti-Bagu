from __future__ import annotations

from anti_bagu.mobile.hub import MobileHub


def test_signed_pairing_can_be_resolved_by_new_hub_instance(tmp_path) -> None:
    secret = tmp_path / "mobile-pairing.key"
    issued = MobileHub(secret).issue("task-1", "user-1")

    restored = MobileHub(secret).resolve(issued.token)

    assert restored is not None
    assert restored.task_id == "task-1"
    assert restored.owner_id == "user-1"
    assert secret.stat().st_mode & 0o777 == 0o600


def test_tampered_or_expired_pairing_is_rejected(tmp_path) -> None:
    secret = tmp_path / "mobile-pairing.key"
    issued = MobileHub(secret).issue("task-1", "user-1")
    assert MobileHub(secret).resolve(f"{issued.token}x") is None

    expired = MobileHub(tmp_path / "expired.key", ttl_seconds=-1).issue(
        "task-2", "user-2"
    )
    assert MobileHub(tmp_path / "expired.key").resolve(expired.token) is None


def test_revoked_pairing_cannot_reconnect_in_same_process(tmp_path) -> None:
    hub = MobileHub(tmp_path / "mobile-pairing.key")
    pairing = hub.issue("task-1", "user-1")

    hub.revoke("task-1")

    assert hub.resolve(pairing.token) is None
