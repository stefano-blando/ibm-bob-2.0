import subprocess
from pathlib import Path
from typing import Set, Callable, Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from nagare.models import ScopeContract

IGNORE_PATTERNS = {".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache", ".ruff_cache", "bob_sessions"}

class GitDiffObserver:
    def __init__(
        self,
        repo_root: Path,
        contract: ScopeContract,
        on_dirty: Optional[Callable[[Path, bool], None]] = None
    ):
        self.repo_root = Path(repo_root).resolve()
        self.contract = contract
        self.on_dirty = on_dirty

    def poll_dirty_files(self) -> Set[Path]:
        try:
            res = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True
            )
        except Exception:
            return set()

        dirty_files: Set[Path] = set()
        for line in res.stdout.splitlines():
            if not line.strip():
                continue
            # Format: XY PATH or XY "PATH"
            parts = line[3:].strip().strip('"')
            # Handle renames R  foo -> bar
            if " -> " in parts:
                parts = parts.split(" -> ")[1].strip('"')
            rel_path = Path(parts)
            if any(part in IGNORE_PATTERNS or part.startswith(".nagare") for part in rel_path.parts):
                continue
            dirty_files.add(rel_path)

            if self.on_dirty:
                is_restr = self.contract.is_restricted(rel_path)
                self.on_dirty(rel_path, is_restr)

        return dirty_files


class _WatchdogHandler(FileSystemEventHandler):
    def __init__(self, repo_root: Path, contract: ScopeContract, on_change: Callable[[Path, bool], None]):
        self.repo_root = repo_root
        self.contract = contract
        self.on_change = on_change

    def _should_ignore(self, path: Path) -> bool:
        for part in path.parts:
            if part in IGNORE_PATTERNS or part.startswith(".nagare") or part.endswith(".tmp") or part.endswith(".swp"):
                return True
        return False

    def _handle_event(self, event: FileSystemEvent):
        if event.is_directory:
            return
        try:
            abs_path = Path(event.src_path).resolve()
            rel_path = abs_path.relative_to(self.repo_root)
            if self._should_ignore(rel_path):
                return
            is_restr = self.contract.is_restricted(rel_path)
            self.on_change(rel_path, is_restr)
        except (ValueError, Exception):
            pass

    def on_created(self, event: FileSystemEvent):
        self._handle_event(event)

    def on_modified(self, event: FileSystemEvent):
        self._handle_event(event)


class FileSystemObserver:
    def __init__(
        self,
        repo_root: Path,
        contract: ScopeContract,
        on_change: Callable[[Path, bool], None]
    ):
        self.repo_root = Path(repo_root).resolve()
        self.contract = contract
        self.on_change = on_change
        self._observer = Observer()
        self._handler = _WatchdogHandler(self.repo_root, self.contract, self.on_change)

    def start(self):
        self._observer.schedule(self._handler, str(self.repo_root), recursive=True)
        self._observer.start()

    def stop(self):
        if self._observer.is_alive():
            self._observer.stop()
            self._observer.join(timeout=1.0)
