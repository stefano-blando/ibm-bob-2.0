from pathlib import Path
from nagare.models import ScopeContract, ViolationEvent, ViolationAction, TelemetrySnapshot

def test_scope_contract_evaluation():
    contract = ScopeContract(
        permitted_paths={Path("api/routes/auth.py"), Path("services/user_service.py")},
        restricted_paths={Path("database/schema.sql"), Path("core/config.py")},
        task_intent="Add in-memory rate limiting to login endpoint"
    )
    assert contract.is_permitted(Path("api/routes/auth.py")) is True
    assert contract.is_permitted(Path("services/user_service.py")) is True
    assert contract.is_permitted(Path("database/schema.sql")) is False
    assert contract.is_restricted(Path("database/schema.sql")) is True
    assert contract.is_permitted(Path("random/other.py")) is False
    assert contract.is_restricted(Path("random/other.py")) is True

def test_violation_event_serialization():
    event = ViolationEvent(
        file_path=Path("database/schema.sql"),
        action=ViolationAction.ROLLED_BACK,
        timestamp=1727340000.0,
        steering_prompt="File database/schema.sql is outside permitted scope. Reverted changes."
    )
    data = event.to_dict()
    assert data["file_path"] == "database/schema.sql"
    assert data["action"] == "ROLLED_BACK"
    assert data["timestamp"] == 1727340000.0
    assert "reverted" in data["steering_prompt"].lower()

def test_telemetry_snapshot_accumulation():
    snapshot = TelemetrySnapshot(
        session_id="nagare-demo-001",
        task_prompt="Implement rate limiting",
        permitted_count=2,
        restricted_count=2,
    )
    event = ViolationEvent(
        file_path=Path("database/schema.sql"),
        action=ViolationAction.ROLLED_BACK,
        timestamp=1727340010.0,
        steering_prompt="File database/schema.sql is outside permitted scope."
    )
    snapshot.record_violation(event)
    assert len(snapshot.violations) == 1
    assert snapshot.total_rollbacks == 1
    assert snapshot.violations[0].file_path == Path("database/schema.sql")
