import time
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Dict
from nagare.models import ScopeContract, ViolationEvent, ViolationAction

class MicroSteerer:
    def __init__(self, repo_root: Path, contract: ScopeContract, debounce_seconds: float = 0.15):
        self.repo_root = Path(repo_root).resolve()
        self.contract = contract
        self.debounce_seconds = debounce_seconds
        self._last_revert: Dict[Path, float] = {}

    def is_dirty(self, rel: Path) -> bool:
        full_path = self.repo_root / rel
        if not full_path.exists():
            return False

        # Check unstaged diff
        diff_unstaged = subprocess.run(
            ["git", "diff", "--quiet", "--", str(rel)],
            cwd=self.repo_root
        ).returncode != 0
        if diff_unstaged:
            return True

        # Check staged diff
        diff_staged = subprocess.run(
            ["git", "diff", "--cached", "--quiet", "--", str(rel)],
            cwd=self.repo_root
        ).returncode != 0
        if diff_staged:
            return True

        # Check untracked
        res_untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", str(rel)],
            cwd=self.repo_root,
            capture_output=True,
            text=True
        )
        if res_untracked.stdout.strip():
            return True

        return False

    def revert_and_steer(self, relative_path: Path) -> Optional[ViolationEvent]:
        rel = Path(relative_path)
        full_path = self.repo_root / rel

        # Debounce rapid duplicate events
        now = time.time()
        if self.debounce_seconds > 0.0 and rel in self._last_revert and (now - self._last_revert[rel]) < self.debounce_seconds:
            return None

        # If file is not dirty, no rollback needed
        if not self.is_dirty(rel):
            return None

        self._last_revert[rel] = now

        # Check if tracked in git
        res = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(rel)],
            cwd=self.repo_root,
            capture_output=True
        )
        tracked = (res.returncode == 0)

        if tracked:
            # 1. Lockless Git blob restore: reads directly from .git/objects without touching .git/index.lock
            show_res = subprocess.run(
                ["git", "show", f"HEAD:{rel}"],
                cwd=self.repo_root,
                capture_output=True
            )
            if show_res.returncode == 0:
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_bytes(show_res.stdout)

            # 2. Attempt staging index reconciliation (non-fatal if index.lock is held concurrently)
            for _ in range(5):
                checkout_res = subprocess.run(
                    ["git", "checkout", "HEAD", "--", str(rel)],
                    cwd=self.repo_root,
                    capture_output=True
                )
                if checkout_res.returncode == 0:
                    break
                time.sleep(0.02)
        else:
            if full_path.exists():
                if full_path.is_dir():
                    shutil.rmtree(full_path)
                else:
                    full_path.unlink()

        permitted_list = ", ".join(str(p) for p in sorted(self.contract.permitted_paths)) or "designated module"
        prompt = (
            f"[NAGARE GOVERNOR INTERCEPTION]\n"
            f"Scope Violation Detected: Attempted modification of restricted file '{rel}'.\n"
            f"Action: Instant micro-rollback applied. The file has been restored to clean HEAD state.\n"
            f"Permitted Scope: {permitted_list}\n"
            f"Directive: Implement the solution strictly within permitted files without modifying '{rel}'."
        )

        # Write authoritative directive file in repo root for autonomous agent consumption
        try:
            directive_file = self.repo_root / ".nagare_directive.md"
            directive_file.write_text(
                f"# ⚠️ NAGARE GOVERNOR STEERING DIRECTIVE\n\n"
                f"> **Violation Intercepted at**: {now}\n"
                f"> **Restricted Target**: `{rel}` (Rolled Back)\n\n"
                f"### Active Scope Constraints\n"
                f"- **Permitted Files**: {permitted_list}\n"
                f"- **Restricted Files**: `{rel}`, database schemas, and global configs.\n\n"
                f"### Mandatory Agent Directive\n"
                f"The modification to `{rel}` was rolled back to pristine HEAD state by Nagare Governor.\n"
                f"**DO NOT** attempt to edit `{rel}` again.\n"
                f"Solve the user request exclusively by modifying the permitted files listed above.\n"
            )
        except Exception:
            pass

        return ViolationEvent(
            file_path=rel,
            action=ViolationAction.ROLLED_BACK,
            timestamp=now,
            steering_prompt=prompt
        )

