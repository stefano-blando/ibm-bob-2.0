from pathlib import Path
from typing import Set, Callable, Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from nagare.models import ScopeContract
from nagare.baseline import git_status_entries
from nagare.paths import should_ignore

class GitDiffObserver:
    """Reconciliation pass over `git status` (catches anything inotify missed, incl. deletions)."""

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
            entries = git_status_entries(self.repo_root)
        except Exception:
            return set()

        dirty_files: Set[Path] = set()
        for _, rel_path in entries:
            if should_ignore(rel_path) or rel_path in dirty_files:
                continue
            dirty_files.add(rel_path)
            if self.on_dirty:
                self.on_dirty(rel_path, self.contract.is_restricted(rel_path))

        return dirty_files


class _WatchdogHandler(FileSystemEventHandler):
    def __init__(self, repo_root: Path, contract: ScopeContract, on_change: Callable[[Path, bool], None]):
        self.repo_root = repo_root
        self.contract = contract
        self.on_change = on_change

    def _dispatch_path(self, raw_path) -> None:
        try:
            abs_path = Path(raw_path).resolve()
            rel_path = abs_path.relative_to(self.repo_root)
        except (ValueError, OSError):
            return
        if should_ignore(rel_path):
            return
        try:
            self.on_change(rel_path, self.contract.is_restricted(rel_path))
        except Exception:
            pass

    def _handle_event(self, event: FileSystemEvent):
        if event.is_directory:
            return
        self._dispatch_path(event.src_path)

    def on_created(self, event: FileSystemEvent):
        self._handle_event(event)

    def on_modified(self, event: FileSystemEvent):
        self._handle_event(event)

    def on_closed(self, event: FileSystemEvent):
        self._handle_event(event)

    def on_deleted(self, event: FileSystemEvent):
        self._handle_event(event)

    def on_moved(self, event: FileSystemEvent):
        # Editors save via temp-file + rename: check both ends of the move.
        if event.is_directory:
            return
        self._dispatch_path(event.src_path)
        self._dispatch_path(event.dest_path)


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
