from app.core.audit import record_audit
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_round_trip() -> None:
    hashed = hash_password("correct-horse")
    assert hashed != "correct-horse"
    assert verify_password("correct-horse", hashed)
    assert not verify_password("wrong-horse", hashed)


def test_jwt_round_trip() -> None:
    token = create_access_token("42", role="admin")
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == "admin"


def test_audit_event_contains_request_id(caplog) -> None:
    with caplog.at_level("INFO"):
        event = record_audit(
            action="profile.update", target="user:1", request_id="req-9", actor_id="1"
        )
    assert event["request_id"] == "req-9"
    assert "profile.update" in caplog.text
