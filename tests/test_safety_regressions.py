"""Regression tests for the data-loss and scope bugs found in the 2026-09-27 audit."""

import subprocess
from pathlib import Path

from nagare.models import ScopeContract, ViolationAction, Policy
from nagare.runner import NagareRunner
from nagare.scope import ScopeSynthesizer
from nagare.mcp_server import NagareMCPServer
from nagare.paths import CONTRACT_FILE

TASK = "Implement rate limiter in api/routes/auth.py"


def _repo(tmp_path: Path) -> Path:
    for args in (["init", "-q"], ["config", "user.name", "T"], ["config", "user.email", "t@e.com"]):
        subprocess.run(["git", *args], cwd=tmp_path, check=True)
    (tmp_path / "api" / "routes").mkdir(parents=True)
    (tmp_path / "api" / "routes" / "auth.py").write_text("from services.user_service import get_user\n")
    (tmp_path / "api" / "main.py").write_text("from api.routes import auth\n")
    (tmp_path / "services").mkdir()
    (tmp_path / "services" / "user_service.py").write_text("def get_user(): pass\n")
    (tmp_path / "database").mkdir()
    (tmp_path / "database" / "schema.sql").write_text("CREATE TABLE users (id INT);\n")
    (tmp_path / "README.md").write_text("readme\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    return tmp_path


def _agent(script: str) -> list:
    return ["python3", "-c", "import time, os, shutil\nfrom pathlib import Path\ntime.sleep(0.2)\n" + script + "\ntime.sleep(0.5)\n"]


def test_developer_uncommitted_work_survives_dry_run(tmp_path):
    repo = _repo(tmp_path)
    (repo / "README.md").write_text("readme\nMY UNCOMMITTED NOTES\n")
    (repo / "TODO.md").write_text("private untracked todo\n")
    (repo / "services" / "user_service.py").write_text("def get_user(): return 'wip'\n")

    snapshot = NagareRunner(repo, dry_run=True).run_governed(TASK)

    assert "UNCOMMITTED" in (repo / "README.md").read_text()
    assert (repo / "TODO.md").read_text() == "private untracked todo\n"
    assert "wip" in (repo / "services" / "user_service.py").read_text()
    assert snapshot.total_interventions == 0
    assert snapshot.preserved_user_files == 3


def test_rollback_restores_session_baseline_not_head(tmp_path):
    repo = _repo(tmp_path)
    schema = repo / "database" / "schema.sql"
    schema.write_text("CREATE TABLE users (id INT, email TEXT); -- dev WIP\n")

    NagareRunner(repo, agent_cmd=_agent("Path('database/schema.sql').write_text('DROP TABLE users;')")).run_governed(TASK)

    assert schema.read_text() == "CREATE TABLE users (id INT, email TEXT); -- dev WIP\n"


def test_agent_created_test_directory_is_not_deleted(tmp_path):
    repo = _repo(tmp_path)
    script = "Path('tests').mkdir(); Path('tests/test_auth.py').write_text('def test(): pass\\n')"
    snapshot = NagareRunner(repo, agent_cmd=_agent(script)).run_governed(TASK)

    assert (repo / "tests" / "test_auth.py").exists()
    assert snapshot.total_interventions == 0


def test_out_of_scope_new_file_is_quarantined_not_deleted(tmp_path):
    repo = _repo(tmp_path)
    script = "Path('scripts').mkdir(); Path('scripts/rogue.py').write_text('EVIL = 1\\n')"
    snapshot = NagareRunner(repo, agent_cmd=_agent(script), policy=Policy.LANE).run_governed(TASK)

    assert not (repo / "scripts" / "rogue.py").exists()
    moved = list((repo / ".nagare" / "quarantine").rglob("rogue.py"))
    assert len(moved) == 1 and moved[0].read_text() == "EVIL = 1\n"
    assert snapshot.total_quarantined == 1


def test_deleted_protected_file_is_restored(tmp_path):
    repo = _repo(tmp_path)
    snapshot = NagareRunner(repo, agent_cmd=_agent("os.remove('database/schema.sql')")).run_governed(TASK)

    assert (repo / "database" / "schema.sql").read_text() == "CREATE TABLE users (id INT);\n"
    assert snapshot.total_rollbacks >= 1


def test_agent_state_dirs_are_never_governed(tmp_path):
    repo = _repo(tmp_path)
    script = "Path('.bob').mkdir(); Path('.bob/state.json').write_text('{}')"
    snapshot = NagareRunner(repo, agent_cmd=_agent(script)).run_governed(TASK)

    assert (repo / ".bob" / "state.json").exists()
    assert snapshot.total_interventions == 0


def test_doc_edits_are_warned_not_reverted_in_balanced_policy(tmp_path):
    repo = _repo(tmp_path)
    script = "Path('README.md').write_text('readme\\nusage notes\\n')"
    snapshot = NagareRunner(repo, agent_cmd=_agent(script)).run_governed(TASK)

    assert "usage notes" in (repo / "README.md").read_text()
    assert snapshot.total_warned == 1


def test_strict_policy_reverts_doc_edits(tmp_path):
    repo = _repo(tmp_path)
    script = "Path('README.md').write_text('readme\\nusage notes\\n')"
    snapshot = NagareRunner(repo, agent_cmd=_agent(script), policy=Policy.STRICT).run_governed(TASK)

    assert (repo / "README.md").read_text() == "readme\n"
    assert snapshot.total_rollbacks >= 1


def test_write_loops_are_collapsed_in_the_report(tmp_path):
    repo = _repo(tmp_path)
    script = (
        "for i in range(12):\n"
        "    Path('database/schema.sql').write_text(f'DROP {i};')\n"
        "    time.sleep(0.2)"
    )
    snapshot = NagareRunner(repo, agent_cmd=_agent(script)).run_governed(TASK)

    assert snapshot.total_rollbacks >= 10
    assert len(snapshot.violations) == 1
    assert snapshot.violations[0].repeat_count == snapshot.total_rollbacks


def test_negated_file_is_protected_not_seeded(tmp_path):
    repo = _repo(tmp_path)
    contract = ScopeSynthesizer(repo).synthesize_scope("Add rate limiting to auth. Do NOT touch user_service.")

    assert Path("services/user_service.py") not in contract.permitted_paths
    assert Path("services/user_service.py") in contract.restricted_paths
    assert Path("api/routes/auth.py") in contract.permitted_paths


def test_stem_match_uses_word_boundaries(tmp_path):
    repo = _repo(tmp_path)
    contract = ScopeSynthesizer(repo).synthesize_scope("Update the author field in api/routes/auth.py")
    seeds = ScopeSynthesizer.split_intent("Update the author field")[0]
    assert not ScopeSynthesizer._mentions(seeds, Path("api/routes/auth.py"))
    assert Path("api/routes/auth.py") in contract.permitted_paths


def test_mcp_answers_match_the_enforced_contract(tmp_path):
    repo = _repo(tmp_path)
    contract = ScopeSynthesizer(repo).synthesize_scope(TASK)
    contract.save(repo / CONTRACT_FILE)
    server = NagareMCPServer(repo)

    for rel in ["api/main.py", "api/routes/auth.py", "database/schema.sql"]:
        text = server.handle_tool_call("nagare_check_permission", {"file_path": rel})["content"][0]["text"]
        enforced_ok = contract.decide(Path(rel), is_new=False) in (ViolationAction.ALLOWED, ViolationAction.WARNED)
        assert ("GRANTED" in text) == enforced_ok, rel


# --- Found in the live Bob A/B run (2026-09-27) --------------------------------------------

def test_runtime_artifacts_are_kept_and_warned(tmp_path):
    repo = _repo(tmp_path)
    snapshot = NagareRunner(repo, agent_cmd=_agent("Path('demo_app.db').write_bytes(b'SQLite format 3')")).run_governed(TASK)

    assert (repo / "demo_app.db").exists()
    assert snapshot.total_quarantined == 0 and snapshot.total_warned == 1


def test_gitignored_new_files_are_not_governed(tmp_path):
    repo = _repo(tmp_path)
    (repo / ".gitignore").write_text("build/\n")
    subprocess.run(["git", "add", ".gitignore"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "ignore"], cwd=repo, check=True)
    script = "Path('build').mkdir(); Path('build/out.js').write_text('bundle')"
    snapshot = NagareRunner(repo, agent_cmd=_agent(script)).run_governed(TASK)

    assert (repo / "build" / "out.js").exists()
    assert snapshot.total_interventions == 0


def test_directive_file_is_cleaned_up_after_session(tmp_path):
    repo = _repo(tmp_path)
    NagareRunner(repo, agent_cmd=_agent("Path('database/schema.sql').write_text('DROP')")).run_governed(TASK)

    assert not (repo / ".nagare_directive.md").exists()
