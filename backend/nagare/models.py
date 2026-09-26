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
    task_intent: str = ""
    status: str = "INITIALIZED"
    elapsed_seconds: float = 0.0
    files_modified: Set[Path] = field(default_factory=set)
    violations: List[ViolationEvent] = field(default_factory=list)
    tokens_estimate: int = 0
    bobcoins_cost: float = 0.0
    session_id: str = ""
    task_prompt: str = ""
    permitted_count: int = 0
    restricted_count: int = 0
    total_rollbacks: int = 0

    def __post_init__(self):
        if not self.task_intent and self.task_prompt:
            self.task_intent = self.task_prompt
        elif not self.task_prompt and self.task_intent:
            self.task_prompt = self.task_intent

    def record_violation(self, event: ViolationEvent) -> None:
        self.violations.append(event)
        if event.action == ViolationAction.ROLLED_BACK:
            self.total_rollbacks += 1
