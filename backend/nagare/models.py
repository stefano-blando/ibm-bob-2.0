import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Set, Dict, Any, List, Optional

from nagare.paths import GOVERNED_NEW_FILE_EXTENSIONS, SOURCE_EXTENSIONS

class ViolationAction(str, Enum):
    DENIED = "DENIED"            # blocked before the write (Bob PreToolUse hook)
    ROLLED_BACK = "ROLLED_BACK"  # restored to the session baseline after the write
    QUARANTINED = "QUARANTINED"  # new out-of-scope file moved to .nagare/quarantine
    WARNED = "WARNED"            # out-of-scope but low-risk (docs): kept, reported
    ALLOWED = "ALLOWED"

class Policy(str, Enum):
    GUARD = "guard"    # protected/guarded files blocked; everything else allowed, drift outside scope reported
    LANE = "lane"      # + existing code outside the task scope reverted; new code only next to scope or as tests
    STRICT = "strict"  # anything outside the permitted set is reverted
    BALANCED = "lane"  # legacy alias of LANE

    @classmethod
    def parse(cls, value: str) -> "Policy":
        return cls.LANE if value == "balanced" else cls(value)

TEST_DIR_PARTS = {"tests", "test", "__tests__", "spec"}

def _is_test_path(path: Path) -> bool:
    name = path.name
    return (
        any(part in TEST_DIR_PARTS for part in path.parts[:-1])
        or name.startswith("test_")
        or name.endswith(("_test.py", ".test.ts", ".test.tsx", ".test.js", ".spec.ts", ".spec.js"))
    )

@dataclass
class ScopeContract:
    permitted_paths: Set[Path] = field(default_factory=set)
    restricted_paths: Set[Path] = field(default_factory=set)
    task_intent: str = ""
    sensitive_patterns: List[str] = field(default_factory=list)
    policy: Policy = Policy.LANE
    # Untracked files that already existed when the session started (the developer's).
    baseline_untracked: Set[Path] = field(default_factory=set)
    # Guarded files the task explicitly names ("add a column to schema.sql"): not sensitive for this task.
    unlocked_paths: Set[Path] = field(default_factory=set)

    def is_permitted(self, path: Path) -> bool:
        return Path(path) in self.permitted_paths

    def is_sensitive(self, path: Path) -> bool:
        normalized = Path(path)
        if normalized in self.restricted_paths:
            return True
        if normalized in self.unlocked_paths:
            return False
        rel_str = normalized.as_posix()
        return any(re.match(pattern, rel_str) for pattern in self.sensitive_patterns)

    def is_restricted(self, path: Path) -> bool:
        normalized = Path(path)
        if normalized in self.restricted_paths:
            return True
        return normalized not in self.permitted_paths

    def _near_scope(self, rel: Path) -> bool:
        return rel.parent in {p.parent for p in self.permitted_paths} or _is_test_path(rel)

    def decide(self, path: Path, is_new: bool) -> ViolationAction:
        """Policy decision for a file the agent changed. ROLLED_BACK on a new file means quarantine."""
        rel = Path(path)
        if self.is_sensitive(rel):
            return ViolationAction.ROLLED_BACK
        if self.is_permitted(rel):
            return ViolationAction.ALLOWED
        if self.policy == Policy.STRICT:
            return ViolationAction.ROLLED_BACK
        if is_new:
            if self._near_scope(rel):
                return ViolationAction.ALLOWED
            if self.policy == Policy.GUARD or rel.suffix.lower() not in GOVERNED_NEW_FILE_EXTENSIONS:
                return ViolationAction.WARNED  # kept; reported as drift / runtime artifact
            return ViolationAction.ROLLED_BACK
        if self.policy == Policy.LANE and rel.suffix.lower() in SOURCE_EXTENSIONS:
            return ViolationAction.ROLLED_BACK
        return ViolationAction.WARNED  # templates, styles, docs, build files: kept, reported

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_intent": self.task_intent,
            "policy": self.policy.value,
            "permitted_paths": sorted(p.as_posix() for p in self.permitted_paths),
            "restricted_paths": sorted(p.as_posix() for p in self.restricted_paths),
            "sensitive_patterns": list(self.sensitive_patterns),
            "baseline_untracked": sorted(p.as_posix() for p in self.baseline_untracked),
            "unlocked_paths": sorted(p.as_posix() for p in self.unlocked_paths),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScopeContract":
        return cls(
            permitted_paths={Path(p) for p in data.get("permitted_paths", [])},
            restricted_paths={Path(p) for p in data.get("restricted_paths", [])},
            task_intent=data.get("task_intent", ""),
            sensitive_patterns=list(data.get("sensitive_patterns", [])),
            policy=Policy.parse(data.get("policy", Policy.LANE.value)),
            baseline_untracked={Path(p) for p in data.get("baseline_untracked", [])},
            unlocked_paths={Path(p) for p in data.get("unlocked_paths", [])},
        )

    def save(self, path: Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> Optional["ScopeContract"]:
        try:
            return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return None

@dataclass
class ViolationEvent:
    file_path: Path
    action: ViolationAction
    timestamp: float
    steering_prompt: str
    layer: str = "fs"          # "hook" = prevented before write, "fs" = repaired after write
    repeat_count: int = 1      # collapsed consecutive repeats (write/rollback loops)
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": str(self.file_path),
            "action": self.action.value,
            "timestamp": self.timestamp,
            "steering_prompt": self.steering_prompt,
            "layer": self.layer,
            "repeat_count": self.repeat_count,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ViolationEvent":
        return cls(
            file_path=Path(data["file_path"]),
            action=ViolationAction(data["action"]),
            timestamp=float(data["timestamp"]),
            steering_prompt=data.get("steering_prompt", ""),
            layer=data.get("layer", "fs"),
            repeat_count=int(data.get("repeat_count", 1)),
            detail=data.get("detail", ""),
        )

# Consecutive events on the same file/action closer than this are collapsed into one line.
COLLAPSE_WINDOW_SECONDS = 2.0

@dataclass
class TelemetrySnapshot:
    task_intent: str = ""
    status: str = "INITIALIZED"
    elapsed_seconds: float = 0.0
    files_modified: Set[Path] = field(default_factory=set)
    violations: List[ViolationEvent] = field(default_factory=list)
    tokens_estimate: Optional[int] = None
    bobcoins_cost: Optional[float] = None
    session_id: str = ""
    task_prompt: str = ""
    permitted_count: int = 0
    restricted_count: int = 0
    total_rollbacks: int = 0
    total_denied: int = 0
    total_quarantined: int = 0
    total_warned: int = 0
    preserved_user_files: int = 0
    policy: str = Policy.LANE.value
    hooks_enabled: bool = False

    def __post_init__(self):
        if not self.task_intent and self.task_prompt:
            self.task_intent = self.task_prompt
        elif not self.task_prompt and self.task_intent:
            self.task_prompt = self.task_intent

    @property
    def total_interventions(self) -> int:
        return self.total_rollbacks + self.total_denied + self.total_quarantined

    def record_violation(self, event: ViolationEvent) -> None:
        if event.action == ViolationAction.ROLLED_BACK:
            self.total_rollbacks += event.repeat_count
        elif event.action == ViolationAction.DENIED:
            self.total_denied += event.repeat_count
        elif event.action == ViolationAction.QUARANTINED:
            self.total_quarantined += event.repeat_count
        elif event.action == ViolationAction.WARNED:
            self.total_warned += event.repeat_count

        last = self.violations[-1] if self.violations else None
        if (
            last is not None
            and last.file_path == event.file_path
            and last.action == event.action
            and last.layer == event.layer
            and event.timestamp - last.timestamp < COLLAPSE_WINDOW_SECONDS
        ):
            last.repeat_count += event.repeat_count
            last.timestamp = event.timestamp
            return
        self.violations.append(event)
