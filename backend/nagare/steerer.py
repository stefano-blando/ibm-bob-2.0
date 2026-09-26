import time
import shutil
import subprocess
from pathlib import Path
from nagare.models import ScopeContract, ViolationEvent, ViolationAction

class MicroSteerer:
    def __init__(self, repo_root: Path, contract: ScopeContract):
        self.repo_root = Path(repo_root).resolve()
        self.contract = contract

    def revert_and_steer(self, relative_path: Path) -> ViolationEvent:
        rel = Path(relative_path)
        full_path = self.repo_root / rel
        
        # Check if tracked in git
        res = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(rel)],
            cwd=self.repo_root,
            capture_output=True
        )
        tracked = (res.returncode == 0)

        if tracked:
            subprocess.run(
                ["git", "checkout", "--", str(rel)],
                cwd=self.repo_root,
                check=True,
                capture_output=True
            )
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
            timestamp=time.time(),
            steering_prompt=prompt
        )
