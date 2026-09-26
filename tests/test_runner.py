import subprocess
import time
from pathlib import Path
from nagare.runner import NagareRunner
from nagare.models import ViolationAction

def test_runner_initialization(tmp_path):
    runner = NagareRunner(repo_root=tmp_path)
    assert runner.repo_root == tmp_path.resolve()

def test_runner_dry_run_cycle(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)

    (tmp_path / "app.py").write_text("print('ok')\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True)

    runner = NagareRunner(repo_root=tmp_path, dry_run=True)
    result = runner.run_governed(task_prompt="Optimize app.py")
    assert result.status == "COMPLETED"
    assert (tmp_path / "bob_sessions").exists()

def test_runner_active_interception_during_execution(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)

    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "auth.py").write_text("# auth\n")
    (tmp_path / "database").mkdir()
    schema_file = tmp_path / "database" / "schema.sql"
    schema_file.write_text("CREATE TABLE users (id INT);\n")

    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True)

    # Custom command simulating a rogue agent step modifying schema.sql then exiting
    rogue_script = (
        "import time, sys\n"
        "from pathlib import Path\n"
        "time.sleep(0.1)\n"
        "Path('database/schema.sql').write_text('ALTER TABLE users ADD evil VARCHAR;')\n"
        "time.sleep(0.3)\n"
    )
    script_path = tmp_path / "rogue.py"
    script_path.write_text(rogue_script)

    runner = NagareRunner(repo_root=tmp_path, agent_cmd=["python3", str(script_path)])
    snapshot = runner.run_governed(task_prompt="Update auth endpoint")

    assert snapshot.status == "COMPLETED"
    assert len(snapshot.violations) >= 1
    assert snapshot.violations[0].action == ViolationAction.ROLLED_BACK
    # Ensure file was reverted
    assert "ALTER TABLE" not in schema_file.read_text()
    assert "CREATE TABLE users" in schema_file.read_text()
