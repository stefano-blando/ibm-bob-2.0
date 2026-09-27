import json
import subprocess
import sys
from pathlib import Path

from nagare.hooks import run_hook, install_hooks, uninstall_hooks, append_event, SETTINGS_REL
from nagare.models import ScopeContract, ViolationEvent, ViolationAction
from nagare.paths import CONTRACT_FILE, EVENTS_FILE


def _contract(repo: Path) -> ScopeContract:
    (repo / "api").mkdir(parents=True, exist_ok=True)
    (repo / "api" / "auth.py").write_text("# auth\n")
    (repo / "database").mkdir(exist_ok=True)
    (repo / "database" / "schema.sql").write_text("CREATE TABLE t (id INT);\n")
    (repo / "core").mkdir(exist_ok=True)
    (repo / "core" / "billing.py").write_text("# billing\n")
    contract = ScopeContract(
        permitted_paths={Path("api/auth.py")},
        restricted_paths={Path("database/schema.sql")},
        sensitive_patterns=[r".*\.env.*"],
        task_intent="rate limit auth",
    )
    contract.save(repo / CONTRACT_FILE)
    return contract


def _pre(tool: str, tool_input: dict, repo: Path) -> dict:
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input, "cwd": str(repo)}
    code, out = run_hook(json.dumps(payload), repo)
    assert code == 0
    return json.loads(out) if out else {}


def test_pre_tool_use_denies_protected_write(tmp_path):
    _contract(tmp_path)
    out = _pre("write_file", {"path": "database/schema.sql", "content": "DROP"}, tmp_path)
    spec = out["hookSpecificOutput"]
    assert spec["hookEventName"] == "PreToolUse"
    assert spec["permissionDecision"] == "deny"
    assert "database/schema.sql" in spec["permissionDecisionReason"]
    assert "api/auth.py" in spec["permissionDecisionReason"]
    logged = (tmp_path / EVENTS_FILE).read_text().strip().splitlines()
    assert json.loads(logged[-1])["layer"] == "hook"


def test_pre_tool_use_allows_permitted_and_new_sibling(tmp_path):
    _contract(tmp_path)
    assert _pre("apply_diff", {"path": "api/auth.py", "diff": "..."}, tmp_path) == {}
    assert _pre("write_file", {"path": "api/rate_limiter.py", "content": "x"}, tmp_path) == {}


def test_pre_tool_use_denies_out_of_scope_code_and_absolute_paths(tmp_path):
    _contract(tmp_path)
    out = _pre("search_and_replace", {"path": str(tmp_path / "core" / "billing.py")}, tmp_path)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_pre_tool_use_denies_shell_write_to_sensitive_file(tmp_path):
    _contract(tmp_path)
    out = _pre("execute_command", {"command": "sed -i 's/INT/TEXT/' database/schema.sql"}, tmp_path)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert _pre("execute_command", {"command": "cat database/schema.sql"}, tmp_path) == {}
    assert _pre("execute_command", {"command": "pytest -q"}, tmp_path) == {}


def test_hooks_are_inert_without_active_contract(tmp_path):
    code, out = run_hook(json.dumps({"hook_event_name": "PreToolUse", "tool_name": "write_file",
                                     "tool_input": {"path": "database/schema.sql"}}), tmp_path)
    assert (code, out) == (0, "")


def test_hook_fails_open_on_garbage(tmp_path):
    _contract(tmp_path)
    assert run_hook("not json", tmp_path) == (0, "")


def test_post_tool_use_reports_filesystem_repairs_once(tmp_path):
    _contract(tmp_path)
    append_event(tmp_path, ViolationEvent(Path("database/schema.sql"), ViolationAction.ROLLED_BACK, 1.0, "x", layer="fs"))
    payload = json.dumps({"hook_event_name": "PostToolUse", "tool_name": "execute_command", "tool_input": {}})

    _, out = run_hook(payload, tmp_path)
    context = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert "database/schema.sql" in context and "reverted" in context

    assert run_hook(payload, tmp_path) == (0, "")  # already reported


def test_session_start_injects_contract(tmp_path):
    _contract(tmp_path)
    _, out = run_hook(json.dumps({"hook_event_name": "SessionStart", "source": "startup"}), tmp_path)
    context = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert "api/auth.py" in context and "database/schema.sql" in context


def test_install_uninstall_preserves_user_settings(tmp_path):
    settings = tmp_path / SETTINGS_REL
    settings.parent.mkdir()
    original = '{"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo bye"}]}]}, "x": 1}'
    settings.write_text(original)

    install_hooks(tmp_path)
    data = json.loads(settings.read_text())
    assert data["x"] == 1 and data["hooks"]["Stop"][0]["hooks"][0]["command"] == "echo bye"
    pre = data["hooks"]["PreToolUse"][0]
    assert "nagare.hooks" in pre["hooks"][0]["command"] and "write_file" in pre["matcher"]

    install_hooks(tmp_path)  # idempotent
    assert len(json.loads(settings.read_text())["hooks"]["PreToolUse"]) == 1

    uninstall_hooks(tmp_path)
    assert settings.read_text() == original


def test_install_uninstall_without_prior_settings(tmp_path):
    install_hooks(tmp_path)
    assert (tmp_path / SETTINGS_REL).exists()
    uninstall_hooks(tmp_path)
    assert not (tmp_path / ".bob").exists()


def test_hook_command_runs_as_real_subprocess(tmp_path):
    """The exact command Bob will execute: python -m nagare.hooks with JSON on stdin."""
    _contract(tmp_path)
    payload = {"hook_event_name": "PreToolUse", "tool_name": "write_file",
               "tool_input": {"path": "database/schema.sql"}, "cwd": str(tmp_path)}
    backend = Path(__file__).resolve().parents[1] / "backend"
    res = subprocess.run(
        [sys.executable, "-m", "nagare.hooks", "--repo", str(tmp_path)],
        input=json.dumps(payload), capture_output=True, text=True, cwd=backend,
    )
    assert res.returncode == 0
    assert json.loads(res.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_rewriting_a_file_created_this_session_is_still_new(tmp_path):
    """Live run: Bob created a test under api/, deleted it, then rewrote it -> must not be denied."""
    for args in (["init", "-q"], ["config", "user.email", "t@e"], ["config", "user.name", "t"]):
        subprocess.run(["git", *args], cwd=tmp_path, check=True)
    _contract(tmp_path)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    (tmp_path / "core" / "test_billing.py").write_text("def test(): pass\n")  # created earlier this session

    assert _pre("write_file", {"path": "core/test_billing.py", "content": "x"}, tmp_path) == {}
    out = _pre("write_file", {"path": "core/billing.py", "content": "x"}, tmp_path)  # tracked, out of scope
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_schema_side_door_via_ddl_in_app_code_is_denied(tmp_path):
    """Live ablation run: blocked from schema.sql, Bob created the table via CREATE TABLE in auth.py."""
    _contract(tmp_path)
    diff = (
        "<<<<<<< SEARCH\n:start_line:1\n-------\n# auth\n=======\n# auth\n"
        "conn.execute('CREATE TABLE IF NOT EXISTS failed_logins (id INTEGER)')\n>>>>>>> REPLACE"
    )
    out = _pre("apply_diff", {"path": "api/auth.py", "diff": diff}, tmp_path)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "side door" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_existing_ddl_moved_around_is_not_flagged(tmp_path):
    _contract(tmp_path)
    (tmp_path / "api" / "auth.py").write_text("SQL = 'CREATE TABLE t (id INT)'\n")
    diff = (
        "<<<<<<< SEARCH\nSQL = 'CREATE TABLE t (id INT)'\n=======\n"
        "# moved\nSQL = 'CREATE TABLE t (id INT)'\n>>>>>>> REPLACE"
    )
    assert _pre("apply_diff", {"path": "api/auth.py", "diff": diff}, tmp_path) == {}
    assert _pre("write_file", {"path": "api/auth.py", "content": "SQL = 'CREATE TABLE t (id INT)'\nX = 1\n"}, tmp_path) == {}


def test_orm_column_additions_count_as_schema_changes(tmp_path):
    _contract(tmp_path)
    for added in ("    location = so.mapped_column(sa.String(64))\n", "    team = models.CharField(max_length=50)\n"):
        out = _pre("write_file", {"path": "api/auth.py", "content": "# auth\n" + added}, tmp_path)
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny", added
