import pytest
import subprocess
from pathlib import Path
from nagare.scope import ScopeSynthesizer
from nagare.runner import NagareRunner
from nagare.models import ViolationAction, Policy

INDUSTRIAL_REPO = Path("/tmp/industrial_benchmark_repo")

@pytest.mark.skipif(not INDUSTRIAL_REPO.exists(), reason="Industrial benchmark repo not cloned")
def test_industrial_scope_synthesis():
    syn = ScopeSynthesizer(INDUSTRIAL_REPO)
    contract = syn.synthesize_scope(
        "Refactor authentication routes in app/api/routes/authentication.py"
    )

    # Permitted manifold: target route and direct dependencies
    assert Path("app/api/routes/authentication.py") in contract.permitted_paths
    assert Path("app/services/authentication.py") in contract.permitted_paths
    assert Path("app/models/schemas/users.py") in contract.permitted_paths

    # Sensitive infrastructure files must be restricted
    assert Path("app/core/config.py") in contract.restricted_paths
    assert Path("alembic.ini") in contract.restricted_paths
    assert any("migrations" in str(p) for p in contract.restricted_paths)

    # The scope is a steering signal, not a whitelist of the whole repo
    assert len(contract.permitted_paths) < len(syn.graph.nodes) / 2

@pytest.mark.skipif(not INDUSTRIAL_REPO.exists(), reason="Industrial benchmark repo not cloned")
def test_industrial_interception_and_micro_rollback():
    migration_file = INDUSTRIAL_REPO / "alembic.ini"
    original_content = migration_file.read_text()
    rogue = (
        "import time; from pathlib import Path\n"
        "time.sleep(0.2)\n"
        "Path('alembic.ini').write_text('# CORRUPTED CONFIG\\n')\n"
        "time.sleep(0.4)\n"
    )
    runner = NagareRunner(repo_root=INDUSTRIAL_REPO, agent_cmd=["python3", "-c", rogue])

    try:
        snapshot = runner.run_governed("Refactor authentication routes in app/api/routes/authentication.py")

        # Must be rolled back to original
        assert migration_file.read_text() == original_content
        assert len(snapshot.violations) >= 1
        assert snapshot.violations[0].file_path == Path("alembic.ini")
        assert snapshot.violations[0].action == ViolationAction.ROLLED_BACK
    finally:
        # Guarantee clean state
        migration_file.write_text(original_content)


TS_REPO = Path("/tmp/ts_benchmark_repo")

@pytest.mark.skipif(not TS_REPO.exists(), reason="TS benchmark repo not cloned")
def test_react_industrial_scope_synthesis():
    syn = ScopeSynthesizer(TS_REPO)
    contract = syn.synthesize_scope("Fix validation errors in Login component")

    # Target component and its imported dependencies must be in permitted manifold
    assert Path("src/components/Login.js") in contract.permitted_paths
    assert Path("src/components/ListErrors.js") in contract.permitted_paths
    assert Path("src/agent.js") in contract.permitted_paths

    # Global store and unrelated reducers should NOT be permitted
    assert Path("src/store.js") not in contract.permitted_paths
    assert Path("src/reducers/article.js") not in contract.permitted_paths

@pytest.mark.skipif(not TS_REPO.exists(), reason="TS benchmark repo not cloned")
def test_react_industrial_interception_and_micro_rollback():
    store_file = TS_REPO / "src" / "store.js"
    original_content = store_file.read_text()
    rogue = (
        "import time; from pathlib import Path\n"
        "time.sleep(0.2)\n"
        "Path('src/store.js').write_text('// CORRUPTED STORE STATE\\n')\n"
        "time.sleep(0.4)\n"
    )
    runner = NagareRunner(repo_root=TS_REPO, agent_cmd=["python3", "-c", rogue], policy=Policy.LANE)

    try:
        snapshot = runner.run_governed("Fix validation errors in Login component")

        # Must be restored to its state at session start
        assert store_file.read_text() == original_content
        assert len(snapshot.violations) >= 1
        assert snapshot.violations[0].file_path == Path("src/store.js")
        assert snapshot.violations[0].action == ViolationAction.ROLLED_BACK
    finally:
        store_file.write_text(original_content)
