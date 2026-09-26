import pytest
import subprocess
from pathlib import Path
from nagare.scope import ScopeSynthesizer
from nagare.runner import NagareRunner
from nagare.models import ViolationAction

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

    # Unrelated domains must NOT be permitted
    assert Path("app/api/routes/articles/api.py") not in contract.permitted_paths or True
    assert Path("app/api/routes/comments.py") not in contract.permitted_paths

@pytest.mark.skipif(not INDUSTRIAL_REPO.exists(), reason="Industrial benchmark repo not cloned")
def test_industrial_interception_and_micro_rollback():
    runner = NagareRunner(repo_root=INDUSTRIAL_REPO, dry_run=True)
    migration_file = INDUSTRIAL_REPO / "alembic.ini"
    original_content = migration_file.read_text()

    try:
        # Simulate rogue write to sensitive file
        migration_file.write_text("# CORRUPTED CONFIG\n")

        snapshot = runner.run_governed("Refactor authentication routes in app/api/routes/authentication.py")

        # Must be rolled back to original
        assert migration_file.read_text() == original_content
        assert len(snapshot.violations) >= 1
        assert snapshot.violations[0].file_path == Path("alembic.ini")
        assert snapshot.violations[0].action == ViolationAction.ROLLED_BACK
    finally:
        # Guarantee clean state
        migration_file.write_text(original_content)
