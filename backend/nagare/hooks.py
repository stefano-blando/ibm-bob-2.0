"""IBM Bob native hook integration (layer 1: prevent + feed back into the agent's context).

Bob 2.x runs workspace hooks from `<repo>/.bob/settings.json`. Command hooks receive the
event JSON on stdin (`hook_event_name`, `tool_name`, `tool_input`, `cwd`, ...). A
PreToolUse hook can deny a tool call with `hookSpecificOutput.permissionDecision = "deny"`;
PreToolUse/PostToolUse/SessionStart hooks can inject `additionalContext` into the model.

Layer 2 (inotify + baseline restore, see runner.py) still repairs anything that bypasses
Bob's file tools, e.g. `sed -i` or a script run through `execute_command`. The PostToolUse
hook tells Bob what layer 2 did, so the agent learns instead of retrying blindly.
"""

import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from nagare.models import ScopeContract, ViolationAction, ViolationEvent
from nagare.paths import CONTRACT_FILE, EVENTS_FILE, NAGARE_DIR, should_ignore
from nagare.steerer import permitted_summary, steering_message

FILE_WRITE_TOOLS = {"write_file", "apply_diff", "insert_content", "search_and_replace", "office_edit"}
SHELL_TOOLS = {"execute_command"}
PATH_KEYS = {"path", "file_path", "filePath", "file", "target_file", "target"}
FEEDBACK_CURSOR = f"{NAGARE_DIR}/feedback_cursor"

# DDL that changes a database schema. When the contract protects schema/migration files,
# adding these statements to *other* files is the same change through a side door.
DDL_RE = re.compile(
    r"\b(CREATE|ALTER|DROP)\s+(TABLE|INDEX|VIEW|TRIGGER|SCHEMA)\b"
    # ORM schema changes: SQLAlchemy columns, Django model fields.
    r"|\b(sa\.Column|db\.Column|mapped_column|models\.[A-Z]\w*Field|models\.ForeignKey|models\.OneToOneField)\s*\(",
    re.IGNORECASE,
)
SCHEMA_FILE_RE = re.compile(r"(\.sql|\.prisma)$|(^|/)(migrations|alembic)(/|$)|alembic\.ini$")

# Shell fragments that write to their operands.
SHELL_WRITE_RE = re.compile(r"(>>?|\bsed\s+-i|\btee\b|\brm\b|\bmv\b|\bcp\b|\btruncate\b|\bdd\b|\bchmod\b|write_text|open\()")


# ---------------------------------------------------------------- event log (shared with runner)

def append_event(repo_root: Path, event: ViolationEvent) -> None:
    path = Path(repo_root) / EVENTS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event.to_dict()) + "\n")


def read_events(repo_root: Path, offset: int = 0) -> tuple[List[ViolationEvent], int]:
    """Events appended since byte `offset`; returns (events, new_offset)."""
    path = Path(repo_root) / EVENTS_FILE
    if not path.exists():
        return [], offset
    with path.open("rb") as fh:
        fh.seek(offset)
        data = fh.read()
    # Only consume complete lines; a concurrent writer may be mid-line.
    end = data.rfind(b"\n") + 1
    events = []
    for line in data[:end].splitlines():
        try:
            events.append(ViolationEvent.from_dict(json.loads(line)))
        except (ValueError, KeyError):
            continue
    return events, offset + end


# ---------------------------------------------------------------- payload helpers

def _extract_paths(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, inner in value.items():
            if key in PATH_KEYS and isinstance(inner, str):
                yield inner
            else:
                yield from _extract_paths(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from _extract_paths(inner)


def _to_rel(repo_root: Path, raw: str) -> Optional[Path]:
    candidate = Path(raw)
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(repo_root)
        except (ValueError, OSError):
            return None  # outside the repo: not ours to govern
    return Path(os.path.normpath(raw))


def _existed_at_start(repo_root: Path, rel: Path, contract: ScopeContract) -> bool:
    """A file the agent created earlier in this session is still "new" when it is rewritten."""
    if rel in contract.baseline_untracked:
        return True
    res = subprocess.run(["git", "cat-file", "-e", f"HEAD:{rel.as_posix()}"], cwd=repo_root, capture_output=True)
    return res.returncode == 0


def _command_targets(command: str, contract: ScopeContract, repo_root: Path) -> List[Path]:
    """Protected files that a shell command visibly writes to (best effort, layer 2 covers the rest)."""
    if not SHELL_WRITE_RE.search(command):
        return []
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = command.split()
    hits = []
    for tok in tokens:
        tok = tok.lstrip(">").strip("'\"")
        if not tok or tok.startswith("-"):
            continue
        rel = _to_rel(repo_root, tok)
        if rel is not None and not should_ignore(rel) and contract.is_sensitive(rel):
            hits.append(rel)
    return hits


def _protects_schema(contract: ScopeContract) -> bool:
    return any(SCHEMA_FILE_RE.search(p.as_posix()) for p in contract.restricted_paths)


def _new_text(tool: str, tool_input: Dict[str, Any]) -> tuple[str, str]:
    """(removed_text, added_text) for a file-writing tool call, best effort."""
    if tool == "apply_diff":
        diff = str(tool_input.get("diff", ""))
        removed, added = [], []
        for block in re.split(r"<{7}\s*SEARCH", diff)[1:]:
            search, _, rest = block.partition("=======")
            replace = rest.split(">>>>>>>")[0]
            removed.append(search)
            added.append(replace)
        return "\n".join(removed), "\n".join(added)
    if tool == "search_and_replace":
        return str(tool_input.get("search", "")), str(tool_input.get("replace", ""))
    return "", str(tool_input.get("content", ""))


def _adds_ddl(tool: str, tool_input: Dict[str, Any], repo_root: Path, rel: Path) -> bool:
    removed, added = _new_text(tool, tool_input)
    if tool == "write_file":
        try:
            removed = (repo_root / rel).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            removed = ""
    return len(DDL_RE.findall(added)) > len(DDL_RE.findall(removed))


def _output(event_name: str, **fields: Any) -> Dict[str, Any]:
    return {"hookSpecificOutput": {"hookEventName": event_name, **fields}}


# ---------------------------------------------------------------- handlers

def handle_pre_tool_use(payload: Dict[str, Any], repo_root: Path, contract: ScopeContract) -> Optional[Dict[str, Any]]:
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    now = time.time()

    if tool in FILE_WRITE_TOOLS:
        targets = [r for r in (_to_rel(repo_root, p) for p in _extract_paths(tool_input)) if r is not None]
    elif tool in SHELL_TOOLS:
        targets = _command_targets(str(tool_input.get("command", "")), contract, repo_root)
    else:
        return None

    warnings = []
    for rel in targets:
        if should_ignore(rel):
            continue
        decision = contract.decide(rel, is_new=not _existed_at_start(repo_root, rel, contract))
        if tool in SHELL_TOOLS:
            decision = ViolationAction.ROLLED_BACK  # only sensitive targets reach here
        if decision == ViolationAction.ROLLED_BACK:
            reason = steering_message(rel, ViolationAction.DENIED, contract, contract.is_sensitive(rel))
            append_event(repo_root, ViolationEvent(
                file_path=rel, action=ViolationAction.DENIED, timestamp=now,
                steering_prompt=reason, layer="hook", detail=tool,
            ))
            return _output("PreToolUse", permissionDecision="deny", permissionDecisionReason=reason)
        if decision == ViolationAction.WARNED:
            warnings.append(rel.as_posix())
        if (
            tool in FILE_WRITE_TOOLS
            and not SCHEMA_FILE_RE.search(rel.as_posix())
            and _protects_schema(contract)
            and _adds_ddl(tool, tool_input, repo_root, rel)
        ):
            protected = ", ".join(sorted(p.as_posix() for p in contract.restricted_paths if SCHEMA_FILE_RE.search(p.as_posix())))
            reason = (
                f"[NAGARE GOVERNOR] This edit to '{rel.as_posix()}' adds a schema change (SQL DDL or an ORM column/field). "
                f"The database schema ({protected}) is protected for this task, and creating tables from "
                f"application code is the same schema change through a side door. Keep the feature in memory, "
                f"or leave a clearly marked TODO for a human-reviewed migration."
            )
            append_event(repo_root, ViolationEvent(
                file_path=rel, action=ViolationAction.DENIED, timestamp=now,
                steering_prompt=reason, layer="hook", detail=f"{tool}:schema-ddl",
            ))
            return _output("PreToolUse", permissionDecision="deny", permissionDecisionReason=reason)

    if warnings:
        return _output(
            "PreToolUse",
            permissionDecision="allow",
            additionalContext=f"[NAGARE GOVERNOR] {', '.join(warnings)} is outside the task scope; "
                              f"keep changes there minimal. Permitted files: {permitted_summary(contract)}",
        )
    return None


def handle_post_tool_use(payload: Dict[str, Any], repo_root: Path, contract: ScopeContract) -> Optional[Dict[str, Any]]:
    """Report layer-2 repairs (rollbacks/quarantines) that happened since the last feedback."""
    cursor_file = repo_root / FEEDBACK_CURSOR
    try:
        offset = int(cursor_file.read_text())
    except (OSError, ValueError):
        offset = 0
    # Give the filesystem layer a moment to finish repairing writes made by this tool call.
    time.sleep(0.05)
    events, new_offset = read_events(repo_root, offset)
    cursor_file.parent.mkdir(parents=True, exist_ok=True)
    cursor_file.write_text(str(new_offset))

    repaired = [e for e in events if e.layer == "fs" and e.action in (ViolationAction.ROLLED_BACK, ViolationAction.QUARANTINED)]
    if not repaired:
        return None
    lines = sorted({f"- {e.file_path.as_posix()} ({e.action.value.lower().replace('_', ' ')})" for e in repaired})
    context = (
        "[NAGARE GOVERNOR] Your last action modified files outside the task scope. "
        "They were automatically reverted:\n" + "\n".join(lines) +
        f"\nDo not retry them. Permitted files: {permitted_summary(contract)}"
    )
    return _output("PostToolUse", additionalContext=context)


def handle_session_start(payload: Dict[str, Any], repo_root: Path, contract: ScopeContract) -> Optional[Dict[str, Any]]:
    protected = sorted(p.as_posix() for p in contract.restricted_paths)
    context = (
        "[NAGARE GOVERNOR ACTIVE] This session is governed by a task-scoped write contract.\n"
        f"Permitted files: {permitted_summary(contract, limit=30)}\n"
        f"Protected files (writes are blocked or reverted): {', '.join(protected[:30]) or 'none'}\n"
        "New helper modules next to permitted files and new tests are allowed. "
        "Anything else will be reverted automatically; plan your changes inside the permitted files."
    )
    return _output("SessionStart", additionalContext=context)


HANDLERS = {
    "PreToolUse": handle_pre_tool_use,
    "PostToolUse": handle_post_tool_use,
    "SessionStart": handle_session_start,
}


def run_hook(stdin_text: str, repo_root: Optional[Path] = None) -> tuple[int, str]:
    """Entry point shared by the CLI and tests. Returns (exit_code, stdout).

    Fails open (exit 0, no output) on any internal error: a Nagare bug must never wedge Bob;
    the filesystem layer still enforces the contract.
    """
    try:
        payload = json.loads(stdin_text or "{}")
        root = Path(repo_root or payload.get("cwd") or os.getcwd()).resolve()
        if os.environ.get("NAGARE_HOOK_LOG"):
            # Debug aid: record raw Bob payloads to learn/verify the hook contract.
            with open(os.environ["NAGARE_HOOK_LOG"], "a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload) + "\n")
        contract = ScopeContract.load(root / CONTRACT_FILE)
        if contract is None:
            return 0, ""
        handler = HANDLERS.get(payload.get("hook_event_name", ""))
        if handler is None:
            return 0, ""
        result = handler(payload, root, contract)
        return 0, json.dumps(result) if result else ""
    except Exception as exc:  # noqa: BLE001 - fail open by design
        try:
            log = Path(repo_root or os.getcwd()) / NAGARE_DIR / "hook_errors.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("a", encoding="utf-8") as fh:
                fh.write(f"{time.time()} {exc!r}\n")
        except OSError:
            pass
        return 0, ""


# ---------------------------------------------------------------- install / uninstall

HOOK_MARKER = "nagare.hooks"
SETTINGS_REL = ".bob/settings.json"
BACKUP_REL = f"{NAGARE_DIR}/bob_settings_backup.json"


def _hook_command(repo_root: Path) -> str:
    return f"{shlex.quote(sys.executable)} -m {HOOK_MARKER} --repo {shlex.quote(str(repo_root))}"


def install_hooks(repo_root: Path, briefing: bool = True) -> Path:
    """Merge Nagare hooks into <repo>/.bob/settings.json, keeping a byte-exact backup."""
    root = Path(repo_root).resolve()
    settings_path = root / SETTINGS_REL
    backup_path = root / BACKUP_REL
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    if settings_path.exists():
        original = settings_path.read_text(encoding="utf-8")
        if not backup_path.exists():
            backup_path.write_text(original, encoding="utf-8")
        settings = json.loads(original or "{}")
    else:
        backup_path.write_text("__ABSENT__", encoding="utf-8")
        settings = {}

    command = _hook_command(root)
    hooks = settings.setdefault("hooks", {})
    wanted = {
        "PreToolUse": "|".join(sorted(FILE_WRITE_TOOLS | SHELL_TOOLS)),
        "PostToolUse": "|".join(sorted(FILE_WRITE_TOOLS | SHELL_TOOLS)),
    }
    if briefing:
        wanted["SessionStart"] = None
    for event, matcher in wanted.items():
        entries = [e for e in hooks.get(event, []) if not any(HOOK_MARKER in h.get("command", "") for h in e.get("hooks", []))]
        entry: Dict[str, Any] = {"hooks": [{"type": "command", "command": command, "timeout": 5}]}
        if matcher:
            entry["matcher"] = f"^({matcher})$"
        entries.insert(0, entry)
        hooks[event] = entries

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    return settings_path


def uninstall_hooks(repo_root: Path) -> None:
    """Restore the user's .bob/settings.json exactly as it was before install_hooks."""
    root = Path(repo_root).resolve()
    settings_path = root / SETTINGS_REL
    backup_path = root / BACKUP_REL
    if not backup_path.exists():
        return
    original = backup_path.read_text(encoding="utf-8")
    if original == "__ABSENT__":
        if settings_path.exists():
            settings_path.unlink()
        try:
            settings_path.parent.rmdir()  # only if we created an empty .bob/
        except OSError:
            pass
    else:
        settings_path.write_text(original, encoding="utf-8")
    backup_path.unlink()


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    repo = None
    if "--repo" in argv:
        idx = argv.index("--repo")
        repo = Path(argv[idx + 1])
    code, out = run_hook(sys.stdin.read(), repo)
    if out:
        sys.stdout.write(out)
    return code


if __name__ == "__main__":
    sys.exit(main())
