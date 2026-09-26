import pytest
from pathlib import Path
from nagare.scope import ScopeSynthesizer

def test_scope_synthesis_from_repo(tmp_path):
    # Setup mock repo structure
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "auth.py").write_text("from services.user_service import get_user\n")
    (tmp_path / "services").mkdir()
    (tmp_path / "services" / "user_service.py").write_text("def get_user(): pass\n")
    (tmp_path / "database").mkdir()
    (tmp_path / "database" / "schema.sql").write_text("CREATE TABLE users (id INT);\n")
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "config.py").write_text("SECRET_KEY = 'supersecret'\n")

    synthesizer = ScopeSynthesizer(repo_root=tmp_path)
    contract = synthesizer.synthesize_scope(
        task_prompt="Add rate limiting to the auth login endpoint"
    )

    # Permitted scope must include auth.py and reachable dependencies
    assert Path("api/auth.py") in contract.permitted_paths
    assert Path("services/user_service.py") in contract.permitted_paths
    # Restricted scope must strictly include database schema and core configs
    assert Path("database/schema.sql") in contract.restricted_paths
    assert Path("core/config.py") in contract.restricted_paths
