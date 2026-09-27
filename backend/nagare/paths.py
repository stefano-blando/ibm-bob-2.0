"""Shared path conventions: what Nagare never governs, and where it keeps its own state."""

from pathlib import Path

# Directory/file names Nagare never governs (agent state, tool caches, Nagare's own output).
IGNORE_PARTS = {
    ".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache", ".ruff_cache",
    ".mypy_cache", "node_modules", "bob_sessions", ".bob",
}

NAGARE_DIR = ".nagare"
CONTRACT_FILE = f"{NAGARE_DIR}/contract.json"
EVENTS_FILE = f"{NAGARE_DIR}/events.jsonl"
QUARANTINE_DIR = f"{NAGARE_DIR}/quarantine"
DIRECTIVE_FILE = ".nagare_directive.md"

SOURCE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".sql", ".prisma"}
DOC_EXTENSIONS = {".md", ".rst", ".txt"}
# New files with these extensions are code/config and fall under the scope contract;
# other new files (sqlite dbs, logs, build output) are runtime artifacts and only warned.
GOVERNED_NEW_FILE_EXTENSIONS = SOURCE_EXTENSIONS | {
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env", ".sh", ".go", ".rs", ".java", ".rb",
}


def should_ignore(rel_path: Path) -> bool:
    for part in Path(rel_path).parts:
        if part in IGNORE_PARTS or part.startswith(".nagare"):
            return True
        if part.endswith((".tmp", ".swp", "~")):
            return True
    return False
