import os
import time
import subprocess
from pathlib import Path
from typing import Optional, List
from rich.live import Live
from nagare.models import TelemetrySnapshot
from nagare.scope import ScopeSynthesizer
from nagare.observer import GitDiffObserver, FileSystemObserver
from nagare.steerer import MicroSteerer
from nagare.telemetry import NagareTelemetry

def _load_env_file(repo_root: Path):
    env_file = repo_root / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v

class NagareRunner:
    def __init__(
        self,
        repo_root: Path,
        dry_run: bool = False,
        agent_cmd: Optional[List[str]] = None
    ):
        self.repo_root = Path(repo_root).resolve()
        _load_env_file(self.repo_root)
        self.dry_run = dry_run
        self.agent_cmd = agent_cmd
        self.telemetry = NagareTelemetry(sessions_dir=self.repo_root / "bob_sessions")

    def run_governed(self, task_prompt: str) -> TelemetrySnapshot:
        start_time = time.time()
        
        # 1. Synthesize Scope
        synthesizer = ScopeSynthesizer(self.repo_root)
        contract = synthesizer.synthesize_scope(task_prompt)

        # 2. Setup Steerer and Telemetry Snapshot
        steerer = MicroSteerer(self.repo_root, contract)
        snapshot = TelemetrySnapshot(
            task_intent=task_prompt,
            status="INITIALIZING",
            elapsed_seconds=0.0,
            permitted_count=len(contract.permitted_paths),
            restricted_count=len(contract.restricted_paths),
        )

        import threading
        git_lock = threading.RLock()

        def on_dirty_file(file_path: Path, is_restricted: bool):
            with git_lock:
                if is_restricted:
                    event = steerer.revert_and_steer(file_path)
                    if event is not None:
                        snapshot.record_violation(event)
                        snapshot.status = "STEERING_APPLIED"
                else:
                    snapshot.files_modified.add(file_path)
                    if snapshot.status != "STEERING_APPLIED":
                        snapshot.status = "IN_LANE"

        # 3. Observers (Git polling + inotify)
        git_observer = GitDiffObserver(self.repo_root, contract, on_dirty=on_dirty_file)
        fs_observer = FileSystemObserver(self.repo_root, contract, on_change=on_dirty_file)
        fs_observer.start()

        try:
            # 4. Supervised Execution with Live Terminal HUD
            with Live(self.telemetry.render_hud(snapshot), refresh_per_second=8, auto_refresh=True) as live:
                snapshot.status = "RUNNING"
                live.update(self.telemetry.render_hud(snapshot))

                if not self.dry_run:
                    cmd = self.agent_cmd or ["bob", "run", "--trust", task_prompt]
                    try:
                        proc = subprocess.Popen(cmd, cwd=self.repo_root)
                        while proc.poll() is None:
                            with git_lock:
                                git_observer.poll_dirty_files()
                            snapshot.elapsed_seconds = time.time() - start_time
                            live.update(self.telemetry.render_hud(snapshot))
                            time.sleep(0.05)
                        # Final check after process exit
                        with git_lock:
                            git_observer.poll_dirty_files()
                    except Exception as e:
                        snapshot.status = f"FAILED: {e}"
                else:
                    with git_lock:
                        git_observer.poll_dirty_files()
                    time.sleep(0.1)

                if not snapshot.status.startswith("FAILED"):
                    snapshot.status = "COMPLETED"
                snapshot.elapsed_seconds = time.time() - start_time
                live.update(self.telemetry.render_hud(snapshot))
        finally:
            fs_observer.stop()

        # 5. Export session report
        self.telemetry.export_session_report(snapshot)
        return snapshot
