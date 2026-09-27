"""Session baseline: the exact working-tree state when Nagare started.

Rollbacks restore a file to *this* state, not to HEAD, so the developer's uncommitted
edits and untracked files are never destroyed by the governor.
"""

import subprocess
from pathlib import Path
from typing import Dict, Optional, Set, List, Tuple

from nagare.paths import should_ignore

# Untracked files larger than this are not snapshotted (restored as "leave alone").
MAX_SNAPSHOT_BYTES = 5 * 1024 * 1024


def git_status_entries(repo_root: Path) -> List[Tuple[str, Path]]:
    """Parse `git status --porcelain=v1 -z -uall` into (XY, path) pairs.

    -z avoids path quoting (spaces, non-ASCII) and -uall lists files inside untracked
    directories instead of collapsing them to `dir/`. Renames yield both the new and
    the original path.
    """
    res = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "-uall"],
        cwd=repo_root, capture_output=True, check=True,
    )
    records = res.stdout.decode("utf-8", errors="surrogateescape").split("\0")
    entries: List[Tuple[str, Path]] = []
    i = 0
    while i < len(records):
        rec = records[i]
        i += 1
        if len(rec) < 4:
            continue
        xy, path = rec[:2], rec[3:]
        entries.append((xy, Path(path)))
        if "R" in xy or "C" in xy:
            if i < len(records) and records[i]:
                entries.append((xy, Path(records[i])))
            i += 1
    return entries


def head_blob(repo_root: Path, rel: Path) -> Optional[bytes]:
    res = subprocess.run(
        ["git", "cat-file", "blob", f"HEAD:{Path(rel).as_posix()}"],
        cwd=repo_root, capture_output=True,
    )
    return res.stdout if res.returncode == 0 else None


class Baseline:
    """Working-tree snapshot. Files not captured here are expected to match HEAD."""

    def __init__(self, repo_root: Path, snapshot: Dict[Path, Optional[bytes]], untracked: Set[Path]):
        self.repo_root = Path(repo_root).resolve()
        # Path -> bytes at session start (None = file did not exist at session start).
        self.snapshot = snapshot
        # Files that were untracked when the session started (the developer's, not the agent's).
        self.untracked = untracked

    @classmethod
    def capture(cls, repo_root: Path) -> "Baseline":
        root = Path(repo_root).resolve()
        snapshot: Dict[Path, Optional[bytes]] = {}
        untracked: Set[Path] = set()
        try:
            entries = git_status_entries(root)
        except Exception:
            entries = []
        for xy, rel in entries:
            if should_ignore(rel):
                continue
            full = root / rel
            if xy == "??":
                untracked.add(rel)
            if full.is_file():
                if full.stat().st_size <= MAX_SNAPSHOT_BYTES:
                    snapshot[rel] = full.read_bytes()
            else:
                snapshot[rel] = None
        return cls(root, snapshot, untracked)

    @classmethod
    def head_only(cls, repo_root: Path) -> "Baseline":
        return cls(repo_root, {}, set())

    @property
    def preexisting_changes(self) -> int:
        return len(self.snapshot)

    def expected(self, rel: Path) -> Tuple[bool, Optional[bytes]]:
        """(known, bytes). bytes None means the file should not exist."""
        rel = Path(rel)
        if rel in self.snapshot:
            return True, self.snapshot[rel]
        if rel in self.untracked:
            # Untracked and too large to snapshot: we cannot restore it, so never touch it.
            return False, None
        return True, head_blob(self.repo_root, rel)

    def existed_at_start(self, rel: Path) -> bool:
        known, data = self.expected(rel)
        return (not known) or data is not None

    def differs(self, rel: Path) -> bool:
        known, expected = self.expected(rel)
        if not known:
            return False
        full = self.repo_root / rel
        if not full.is_file():
            return expected is not None
        if expected is None:
            return True
        try:
            return full.read_bytes() != expected
        except OSError:
            return False
