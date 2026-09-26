from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Set, Dict, Any, List

class ViolationAction(str, Enum):
    ROLLED_BACK = "ROLLED_BACK"
    WARNED = "WARNED"
    ALLOWED = "ALLOWED"

@dataclass
class ScopeContract:
    permitted_paths: Set[Path] = field(default_factory=set)
    restricted_paths: Set[Path] = field(default_factory=set)
    task_intent: str = ""

    def is_permitted(self, path: Path) -> bool:
        normalized = Path(path)
        return normalized in self.permitted_paths

    def is_restricted(self, path: Path) -> bool:
        normalized = Path(path)
        if normalized in self.restricted_paths:
            return True
        return normalized not in self.permitted_paths

@dataclass
class ViolationEvent:
    file_path: Path
    action: ViolationAction
    timestamp: float
    steering_prompt: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": str(self.file_path),
            "action": self.action.value,
            "timestamp": self.timestamp,
            "steering_prompt": self.steering_prompt,
        }

@dataclass
class TelemetrySnapshot:
    session_id: str
    task_prompt: str
    permitted_count: int = 0
    restricted_count: int = 0
    violations: List[ViolationEvent] = field(default_factory=list)
    total_rollbacks: int = 0

    def record_violation(self, event: ViolationEvent) -> None:
        self.violations.append(event)
        if event.action == ViolationAction.ROLLED_BACK:
            self.total_rollbacks += 1
