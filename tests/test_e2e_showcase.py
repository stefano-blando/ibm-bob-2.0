import subprocess
from pathlib import Path
from nagare.runner import NagareRunner
from nagare.models import ViolationAction

def test_governor_intercepts_schema_corruption(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)

    db_dir = tmp_path / "database"
    db_dir.mkdir(parents=True)
    schema_file = db_dir / "schema.sql"
    original_schema = "CREATE TABLE users (id INT, email TEXT);\n"
    schema_file.write_text(original_schema)

    core_dir = tmp_path / "core"
    core_dir.mkdir(parents=True)
    config_file = core_dir / "config.py"
    original_config = "SECRET_KEY = 'secret'\n"
    config_file.write_text(original_config)

    api_dir = tmp_path / "api"
    api_dir.mkdir(parents=True)
    auth_file = api_dir / "auth.py"
    auth_file.write_text("def login(): pass\n")

    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True)

    # A rogue agent step corrupts schema.sql *during* the governed session
    rogue = (
        "import time; from pathlib import Path\n"
        "time.sleep(0.2)\n"
        "Path('database/schema.sql').write_text('DROP TABLE users; -- HACKED\\n')\n"
        "time.sleep(0.4)\n"
    )
    runner = NagareRunner(repo_root=tmp_path, agent_cmd=["python3", "-c", rogue])
    snapshot = runner.run_governed("Add rate limiting to auth login")

    # Verify that schema was rolled back to original
    assert schema_file.read_text() == original_schema
    assert len(snapshot.violations) == 1
    assert snapshot.total_rollbacks >= 1
    assert snapshot.violations[0].file_path == Path("database/schema.sql")
    assert snapshot.violations[0].action == ViolationAction.ROLLED_BACK

    # Verify session report export
    session_files = list((tmp_path / "bob_sessions").glob("nagare_session_*.md"))
    assert len(session_files) == 1
    report_content = session_files[0].read_text()
    assert "schema.sql" in report_content
    assert "ROLLED_BACK" in report_content
