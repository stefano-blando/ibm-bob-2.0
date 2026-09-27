import os
import json
import time
import threading
import subprocess
import datetime
from pathlib import Path
from typing import Optional, List
from rich.live import Live
from nagare.models import TelemetrySnapshot, Policy
from nagare.scope import ScopeSynthesizer
from nagare.observer import GitDiffObserver, FileSystemObserver
from nagare.steerer import MicroSteerer
from nagare.baseline import Baseline
from nagare.telemetry import NagareTelemetry
from nagare.paths import CONTRACT_FILE, EVENTS_FILE, NAGARE_DIR, DIRECTIVE_FILE
from nagare import hooks as bob_hooks

def _load_env_file(repo_root: Path):
    candidates = [
        repo_root / ".env",
        Path.cwd() / ".env",
        Path(__file__).resolve().parent.parent.parent / ".env"
    ]
    for env_file in candidates:
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k and k not in os.environ:
                        os.environ[k] = v


def _extract_cost(stream_file: Path) -> tuple[Optional[float], Optional[int]]:
    """Best-effort cost/token extraction from `bob run -f stream-json` output.

    Returns (None, None) when the stream carries no such fields: we never report a made-up 0.00.
    """
    cost, tokens = None, None
    if not stream_file.exists():
        return cost, tokens

    def walk(node):
        nonlocal cost, tokens
        if isinstance(node, dict):
            for key, value in node.items():
                lk = key.lower()
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    if lk in ("session_costs", "totalcost", "total_cost", "cost", "costusd", "bobcoins"):
                        cost = float(value)
                    elif lk in ("totaltokens", "total_tokens"):
                        tokens = int(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for line in stream_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            walk(json.loads(line))
        except ValueError:
            continue
    return cost, tokens


class NagareRunner:
    def __init__(
        self,
        repo_root: Path,
        dry_run: bool = False,
        agent_cmd: Optional[List[str]] = None,
        policy: Policy = Policy.GUARD,
        use_hooks: bool = True,
        max_turns: Optional[int] = None,
        max_cost: Optional[float] = None,
        extra_bob_args: Optional[List[str]] = None,
        briefing: bool = True,
    ):
        self.repo_root = Path(repo_root).resolve()
        _load_env_file(self.repo_root)
        self.dry_run = dry_run
        self.agent_cmd = agent_cmd
        self.policy = policy
        self.use_hooks = use_hooks
        self.max_turns = max_turns
        self.max_cost = max_cost
        self.extra_bob_args = list(extra_bob_args or [])
        self.briefing = briefing
        self.telemetry = NagareTelemetry(sessions_dir=self.repo_root / "bob_sessions")

    def _bob_command(self, task_prompt: str, stream_file: Path) -> List[str]:
        cmd = ["bob", "run", "--accept-license", "--trust", "-f", "stream-json"]
        if self.max_turns:
            cmd += ["--max-turns", str(self.max_turns)]
        if self.max_cost:
            cmd += ["--max-cost", str(self.max_cost)]
        return cmd + self.extra_bob_args + [task_prompt]

    def run_governed(self, task_prompt: str) -> TelemetrySnapshot:
        start_time = time.time()
        session_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        nagare_dir = self.repo_root / NAGARE_DIR
        nagare_dir.mkdir(parents=True, exist_ok=True)

        # 1. Baseline first: everything dirty/untracked right now belongs to the developer.
        baseline = Baseline.capture(self.repo_root)

        # 2. Synthesize and publish the scope contract (read by Bob hooks and the MCP server).
        synthesizer = ScopeSynthesizer(self.repo_root)
        contract = synthesizer.synthesize_scope(task_prompt, policy=self.policy)
        contract.baseline_untracked = set(baseline.untracked)
        contract_path = self.repo_root / CONTRACT_FILE
        contract.save(contract_path)
        events_path = self.repo_root / EVENTS_FILE
        events_path.write_text("", encoding="utf-8")
        (self.repo_root / bob_hooks.FEEDBACK_CURSOR).write_text("0", encoding="utf-8")

        steerer = MicroSteerer(self.repo_root, contract, baseline=baseline, session_id=session_id)
        snapshot = TelemetrySnapshot(
            task_intent=task_prompt,
            status="INITIALIZING",
            elapsed_seconds=0.0,
            session_id=session_id,
            permitted_count=len(contract.permitted_paths),
            restricted_count=len(contract.restricted_paths),
            preserved_user_files=baseline.preexisting_changes,
            policy=self.policy.value,
        )

        git_lock = threading.RLock()
        events_offset = 0

        def on_file_change(file_path: Path, _is_restricted: bool):
            with git_lock:
                event = steerer.handle_change(file_path)
                if event is not None:
                    snapshot.record_violation(event)
                    bob_hooks.append_event(self.repo_root, event)
                    snapshot.status = "STEERING_APPLIED"
                elif steerer.is_dirty(file_path):
                    snapshot.files_modified.add(file_path)
                    if snapshot.status == "RUNNING":
                        snapshot.status = "IN_LANE"

        def drain_hook_events():
            nonlocal events_offset
            events, events_offset = bob_hooks.read_events(self.repo_root, events_offset)
            for event in events:
                if event.layer in ("hook", "mcp"):
                    snapshot.record_violation(event)
                    snapshot.status = "STEERING_APPLIED"

        # 3. Layer 1: Bob native hooks (prevent + feedback). Layer 2: inotify + git reconciliation.
        installed_hooks = False
        if self.use_hooks and not self.dry_run and self.agent_cmd is None:
            try:
                bob_hooks.install_hooks(self.repo_root, briefing=self.briefing)
                installed_hooks = True
                snapshot.hooks_enabled = True
            except Exception as exc:  # hooks are an optimisation; layer 2 still enforces
                snapshot.status = f"HOOKS_UNAVAILABLE: {exc}"

        git_observer = GitDiffObserver(self.repo_root, contract, on_dirty=on_file_change)
        fs_observer = FileSystemObserver(self.repo_root, contract, on_change=on_file_change)
        fs_observer.start()
        stream_file = nagare_dir / f"bob_stream_{session_id}.jsonl"

        try:
            with Live(self.telemetry.render_hud(snapshot), refresh_per_second=8, auto_refresh=True) as live:
                snapshot.status = "RUNNING"
                live.update(self.telemetry.render_hud(snapshot))

                if not self.dry_run:
                    cmd = self.agent_cmd or self._bob_command(task_prompt, stream_file)
                    try:
                        with stream_file.open("wb") as out:
                            proc = subprocess.Popen(
                                cmd, cwd=self.repo_root,
                                stdout=out if self.agent_cmd is None else None,
                            )
                            last_poll = 0.0
                            while proc.poll() is None:
                                now = time.time()
                                if now - last_poll > 0.5:  # inotify is primary; git status is the safety net
                                    with git_lock:
                                        git_observer.poll_dirty_files()
                                    last_poll = now
                                drain_hook_events()
                                snapshot.elapsed_seconds = now - start_time
                                live.update(self.telemetry.render_hud(snapshot))
                                time.sleep(0.05)
                        time.sleep(0.2)  # let trailing inotify events land
                        with git_lock:
                            git_observer.poll_dirty_files()
                        if proc.returncode not in (0, None):
                            snapshot.status = f"AGENT_EXIT_{proc.returncode}"
                    except KeyboardInterrupt:
                        proc.terminate()
                        proc.wait(timeout=5)
                        snapshot.status = "STOPPED"
                    except Exception as e:
                        snapshot.status = f"FAILED: {e}"
                else:
                    with git_lock:
                        git_observer.poll_dirty_files()
                    time.sleep(0.1)

                drain_hook_events()
                if not snapshot.status.startswith(("FAILED", "AGENT_EXIT", "STOPPED")):
                    snapshot.status = "COMPLETED"
                snapshot.elapsed_seconds = time.time() - start_time
                live.update(self.telemetry.render_hud(snapshot))
        finally:
            fs_observer.stop()
            if installed_hooks:
                bob_hooks.uninstall_hooks(self.repo_root)
            if contract_path.exists():
                contract_path.unlink()
            directive = self.repo_root / DIRECTIVE_FILE
            if directive.exists() and not baseline.existed_at_start(Path(DIRECTIVE_FILE)):
                directive.unlink()

        if self.agent_cmd is None and not self.dry_run:
            snapshot.bobcoins_cost, snapshot.tokens_estimate = _extract_cost(stream_file)
        elif stream_file.exists() and stream_file.stat().st_size == 0:
            stream_file.unlink()

        # 4. Export session report (includes the contract so the audit is self-contained).
        self.telemetry.export_session_report(snapshot, contract=contract)
        return snapshot
