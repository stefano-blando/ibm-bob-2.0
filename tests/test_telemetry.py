from pathlib import Path
from nagare.models import TelemetrySnapshot, ViolationEvent, ViolationAction
from nagare.telemetry import NagareTelemetry

def test_telemetry_export_markdown(tmp_path):
    sessions_dir = tmp_path / "bob_sessions"
    telemetry = NagareTelemetry(sessions_dir=sessions_dir)

    snapshot = TelemetrySnapshot(
        task_intent="Add in-memory rate limiting",
        status="COMPLETED",
        elapsed_seconds=12.4,
        files_modified={Path("api/auth.py"), Path("api/rate_limiter.py")},
        violations=[
            ViolationEvent(
                file_path=Path("database/schema.sql"),
                action=ViolationAction.ROLLED_BACK,
                timestamp=1727340005.0,
                steering_prompt="Restricted file schema.sql reverted."
            )
        ],
        bobcoins_cost=1.5
    )

    out_file = telemetry.export_session_report(snapshot)
    assert out_file.exists()
    content = out_file.read_text()
    assert "Nagare Governor Session Report" in content
    assert "schema.sql" in content
    assert "ROLLED_BACK" in content
    assert "COMPLETED" in content

def test_telemetry_render_hud():
    telemetry = NagareTelemetry(sessions_dir=Path("/tmp"))
    snapshot = TelemetrySnapshot(
        task_intent="Refactor auth",
        status="RUNNING",
        elapsed_seconds=5.0,
        files_modified={Path("api/auth.py")}
    )
    panel = telemetry.render_hud(snapshot)
    assert panel is not None
