import time
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Dict, Set
from nagare.models import ScopeContract, ViolationEvent, ViolationAction
from nagare.baseline import Baseline
from nagare.paths import QUARANTINE_DIR, DIRECTIVE_FILE


def permitted_summary(contract: ScopeContract, limit: int = 12) -> str:
    items = sorted(p.as_posix() for p in contract.permitted_paths)
    if not items:
        return "designated module"
    shown = ", ".join(items[:limit])
    return shown + (f" (+{len(items) - limit} more)" if len(items) > limit else "")


def steering_message(rel: Path, action: ViolationAction, contract: ScopeContract, sensitive: bool) -> str:
    reason = "protected infrastructure (schema/migrations/secrets/lockfile)" if sensitive else "outside the task's permitted scope"
    what = {
        ViolationAction.DENIED: "The write was blocked before it happened.",
        ViolationAction.ROLLED_BACK: "The file was restored to its state at session start.",
        ViolationAction.QUARANTINED: "The new file was moved to .nagare/quarantine (not deleted).",
        ViolationAction.WARNED: "The change was kept but flagged for review.",
    }.get(action, "")
    return (
        f"[NAGARE GOVERNOR] '{rel.as_posix()}' is {reason}. {what}\n"
        f"Permitted files: {permitted_summary(contract)}\n"
        f"Do not retry this file. Implement the task within the permitted files "
        f"(new helper modules next to them or new tests are allowed)."
    )


class MicroSteerer:
    def __init__(
        self,
        repo_root: Path,
        contract: ScopeContract,
        debounce_seconds: float = 0.15,
        baseline: Optional[Baseline] = None,
        session_id: str = "adhoc",
    ):
        self.repo_root = Path(repo_root).resolve()
        self.contract = contract
        self.debounce_seconds = debounce_seconds
        self.baseline = baseline or Baseline.head_only(self.repo_root)
        self.session_id = session_id
        self._last_revert: Dict[Path, float] = {}
        self._warned: Dict[Path, bytes] = {}
        self._intercepted: Set[Path] = set()
        self._ignored_cache: Dict[Path, bool] = {}

    def is_dirty(self, rel: Path) -> bool:
        """True when the file differs from the session baseline (incl. deleted or newly created)."""
        return self.baseline.differs(Path(rel))

    def handle_change(self, relative_path: Path) -> Optional[ViolationEvent]:
        """Apply the contract policy to a file the agent touched. None = nothing to do."""
        rel = Path(relative_path)
        if not self.baseline.differs(rel):
            return None
        is_new = not self.baseline.existed_at_start(rel)
        if is_new and self._is_gitignored(rel):
            return None
        decision = self.contract.decide(rel, is_new=is_new)
        if decision == ViolationAction.ALLOWED:
            return None
        if decision == ViolationAction.WARNED:
            full = self.repo_root / rel
            current = full.read_bytes() if full.is_file() else b""
            if self._warned.get(rel) == current:
                return None
            self._warned[rel] = current
            return ViolationEvent(
                file_path=rel,
                action=ViolationAction.WARNED,
                timestamp=time.time(),
                steering_prompt=steering_message(rel, ViolationAction.WARNED, self.contract, False),
            )
        return self.revert_and_steer(rel)

    def _is_gitignored(self, rel: Path) -> bool:
        if rel not in self._ignored_cache:
            res = subprocess.run(["git", "check-ignore", "-q", rel.as_posix()], cwd=self.repo_root, capture_output=True)
            self._ignored_cache[rel] = res.returncode == 0
        return self._ignored_cache[rel]

    def revert_and_steer(self, relative_path: Path) -> Optional[ViolationEvent]:
        """Restore a file to the session baseline (or quarantine it if it is new)."""
        rel = Path(relative_path)
        full_path = self.repo_root / rel

        now = time.time()
        # Debounce only de-duplicates *events*; the restore itself always runs, so a second write
        # landing inside the window can never survive until the next reconciliation poll.
        duplicate = (
            self.debounce_seconds > 0.0 and rel in self._last_revert
            and (now - self._last_revert[rel]) < self.debounce_seconds
        )

        known, expected = self.baseline.expected(rel)
        if not known:
            return None
        current = full_path.read_bytes() if full_path.is_file() else None
        if current == expected:
            return None

        self._last_revert[rel] = now

        if expected is not None:
            # Lockless restore: write the baseline bytes directly, no .git/index.lock needed.
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_bytes(expected)
            action = ViolationAction.ROLLED_BACK
            if rel not in self.baseline.snapshot:
                # Baseline is HEAD: also drop anything the agent staged. Non-fatal under index.lock contention.
                subprocess.run(
                    ["git", "checkout", "HEAD", "--", rel.as_posix()],
                    cwd=self.repo_root, capture_output=True,
                )
        else:
            action = ViolationAction.QUARANTINED
            if full_path.exists():
                target = self.repo_root / QUARANTINE_DIR / self.session_id / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    target = target.with_name(f"{target.name}.{int(now * 1000)}")
                shutil.move(str(full_path), str(target))

        if duplicate:
            return None
        self._intercepted.add(rel)
        sensitive = self.contract.is_sensitive(rel)
        prompt = steering_message(rel, action, self.contract, sensitive)
        self._write_directive(now)

        return ViolationEvent(
            file_path=rel,
            action=action,
            timestamp=now,
            steering_prompt=prompt,
        )

    def _write_directive(self, now: float) -> None:
        # In-repo directive for agents that read AGENTS.md rules; the hook channel is primary.
        try:
            blocked = "\n".join(f"- `{p.as_posix()}`" for p in sorted(self._intercepted))
            (self.repo_root / DIRECTIVE_FILE).write_text(
                f"# NAGARE GOVERNOR STEERING DIRECTIVE\n\n"
                f"> Last intervention: {time.strftime('%H:%M:%S', time.localtime(now))}\n\n"
                f"### Files you must not modify (already restored)\n{blocked}\n\n"
                f"### Permitted files\n{permitted_summary(self.contract, limit=50)}\n\n"
                f"Solve the user request exclusively by modifying the permitted files listed above.\n",
                encoding="utf-8",
            )
        except OSError:
            pass
