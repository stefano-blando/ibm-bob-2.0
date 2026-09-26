import time
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Dict
from nagare.models import ScopeContract, ViolationEvent, ViolationAction

class MicroSteerer:
    def __init__(self, repo_root: Path, contract: ScopeContract):
        self.repo_root = Path(repo_root).resolve()
        self.contract = contract
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

        # Debounce rapid duplicate events (within 100ms)
        now = time.time()
        if rel in self._last_revert and (now - self._last_revert[rel]) < 0.15:
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

        return ViolationEvent(
            file_path=rel,
            action=ViolationAction.ROLLED_BACK,
            timestamp=now,
            steering_prompt=prompt
        )
