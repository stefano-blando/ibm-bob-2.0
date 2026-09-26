import time
import subprocess
from pathlib import Path
from nagare.models import ScopeContract
from nagare.observer import GitDiffObserver, FileSystemObserver

def test_observer_detects_dirty_files(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    
    file_a = tmp_path / "file_a.py"
    file_a.write_text("print('hello')\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True)

    contract = ScopeContract(
        permitted_paths={Path("file_a.py")},
        restricted_paths={Path("forbidden.sql")}
    )

    detected_files = []
    observer = GitDiffObserver(
        repo_root=tmp_path,
        contract=contract,
        on_dirty=lambda path, is_restricted: detected_files.append((path, is_restricted))
    )

    forbidden = tmp_path / "forbidden.sql"
    forbidden.write_text("DROP TABLE users;\n")

    dirty = observer.poll_dirty_files()
    assert Path("forbidden.sql") in dirty
    assert (Path("forbidden.sql"), True) in detected_files

def test_inotify_filesystem_observer(tmp_path):
    contract = ScopeContract(
        permitted_paths={Path("allowed.py")},
        restricted_paths={Path("database/schema.sql")}
    )
    (tmp_path / "database").mkdir(parents=True, exist_ok=True)
    detected = []
    
    fs_obs = FileSystemObserver(
        repo_root=tmp_path,
        contract=contract,
        on_change=lambda path, is_restricted: detected.append((path, is_restricted))
    )
    fs_obs.start()
    try:
        (tmp_path / "database" / "schema.sql").write_text("DROP TABLE users;\n")
        time.sleep(0.15)
        assert any(p == Path("database/schema.sql") and is_restr is True for p, is_restr in detected)
    finally:
        fs_obs.stop()
