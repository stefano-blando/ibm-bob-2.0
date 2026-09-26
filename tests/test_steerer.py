import subprocess
from pathlib import Path
from nagare.models import ScopeContract, ViolationAction
from nagare.steerer import MicroSteerer

def test_micro_rollback_tracked_file(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    
    schema = tmp_path / "schema.sql"
    schema.write_text("CREATE TABLE users (id INT);\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True)

    contract = ScopeContract(
        permitted_paths={Path("api/auth.py")},
        restricted_paths={Path("schema.sql")}
    )
    steerer = MicroSteerer(repo_root=tmp_path, contract=contract)

    # Mutate restricted file
    schema.write_text("CORRUPTED DROP TABLE users;\n")
    assert "CORRUPTED" in schema.read_text()

    # Intervene
    event = steerer.revert_and_steer(Path("schema.sql"))
    assert event.action == ViolationAction.ROLLED_BACK
    # File must be reverted to original
    assert "CORRUPTED" not in schema.read_text()
    assert "CREATE TABLE" in schema.read_text()
    assert "schema.sql" in event.steering_prompt

def test_micro_rollback_untracked_forbidden_file(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)

    contract = ScopeContract(
        permitted_paths={Path("api/auth.py")},
        restricted_paths={Path("unwanted.txt")}
    )
    steerer = MicroSteerer(repo_root=tmp_path, contract=contract)

    # Create new untracked restricted file
    unwanted = tmp_path / "unwanted.txt"
    unwanted.write_text("rogue data\n")
    assert unwanted.exists()

    event = steerer.revert_and_steer(Path("unwanted.txt"))
    assert event.action == ViolationAction.ROLLED_BACK
    assert not unwanted.exists()

def test_micro_rollback_with_index_lock_contention(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)

    schema = tmp_path / "schema.sql"
    schema.write_text("CREATE TABLE users (id INT);\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True)

    contract = ScopeContract(
        permitted_paths={Path("api/auth.py")},
        restricted_paths={Path("schema.sql")}
    )
    steerer = MicroSteerer(repo_root=tmp_path, contract=contract)

    # Mutate restricted file
    schema.write_text("CORRUPTED DROP TABLE users;\n")

    # Simulate active concurrent git command holding index.lock
    lock_file = tmp_path / ".git" / "index.lock"
    lock_file.write_text("locked by external agent")

    try:
        # MicroSteerer must succeed despite index.lock contention
        event = steerer.revert_and_steer(Path("schema.sql"))
        assert event is not None
        assert event.action == ViolationAction.ROLLED_BACK
        assert "CORRUPTED" not in schema.read_text()
        assert "CREATE TABLE" in schema.read_text()
    finally:
        if lock_file.exists():
            lock_file.unlink()

def test_steering_directive_file_generated(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)

    schema = tmp_path / "schema.sql"
    schema.write_text("CREATE TABLE users (id INT);\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True)

    contract = ScopeContract(
        permitted_paths={Path("api/auth.py")},
        restricted_paths={Path("schema.sql")}
    )
    steerer = MicroSteerer(repo_root=tmp_path, contract=contract)

    schema.write_text("CORRUPTED;\n")
    steerer.revert_and_steer(Path("schema.sql"))

    directive_file = tmp_path / ".nagare_directive.md"
    assert directive_file.exists()
    content = directive_file.read_text()
    assert "NAGARE GOVERNOR STEERING DIRECTIVE" in content
    assert "schema.sql" in content
    assert "api/auth.py" in content

