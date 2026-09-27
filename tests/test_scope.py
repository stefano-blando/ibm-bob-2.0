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

def test_dynamic_import_scope_synthesis(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "plugins").mkdir()
    # Python dynamic import
    (tmp_path / "app" / "loader.py").write_text("import importlib\nplugin = importlib.import_module('plugins.custom_plugin')\n")
    (tmp_path / "plugins" / "custom_plugin.py").write_text("def run(): pass\n")

    synthesizer = ScopeSynthesizer(repo_root=tmp_path)
    contract = synthesizer.synthesize_scope("Update plugin loader in app/loader.py")

    assert Path("app/loader.py") in contract.permitted_paths
    assert Path("plugins/custom_plugin.py") in contract.permitted_paths

def test_repo_config_override_nagare_json(tmp_path):
    import json
    (tmp_path / "services").mkdir()
    (tmp_path / "services" / "payment.py").write_text("def pay(): pass\n")
    (tmp_path / "services" / "audit.py").write_text("def audit(): pass\n")

    # Custom repository config
    config = {
        "extra_restricted": [r".*services/payment\.py$"],
        "extra_permitted": ["services/audit.py"]
    }
    (tmp_path / "nagare.json").write_text(json.dumps(config))

    synthesizer = ScopeSynthesizer(repo_root=tmp_path)
    contract = synthesizer.synthesize_scope("General maintenance")

    assert Path("services/payment.py") in contract.restricted_paths
    assert Path("services/audit.py") in contract.permitted_paths



def test_relative_imports_and_src_layout_resolve(tmp_path):
    """Found by scope_eval: v0.3 dropped `from . import x` and src/ layouts, so flask's graph had no edges."""
    pkg = tmp_path / "src" / "mypkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("from .app import App\n")
    (pkg / "app.py").write_text("from . import helpers\nfrom .sub.deep import thing\n")
    (pkg / "helpers.py").write_text("import json\n")
    (pkg / "sub").mkdir()
    (pkg / "sub" / "__init__.py").write_text("")
    (pkg / "sub" / "deep.py").write_text("from ..helpers import x\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text("from mypkg.app import App\nimport mypkg\n")

    graph = ScopeSynthesizer(tmp_path).build_dependency_graph()
    edges = {(u.as_posix(), v.as_posix()) for u, v in graph.edges}
    assert ("src/mypkg/__init__.py", "src/mypkg/app.py") in edges
    assert ("src/mypkg/app.py", "src/mypkg/helpers.py") in edges
    assert ("src/mypkg/app.py", "src/mypkg/sub/deep.py") in edges
    assert ("src/mypkg/sub/deep.py", "src/mypkg/helpers.py") in edges
    assert ("tests/test_app.py", "src/mypkg/app.py") in edges
    # stdlib `import json` must not resolve to anything in the repo
    assert not any(v.endswith("json.py") for _, v in edges)


def test_guarded_file_is_unlocked_only_when_named(tmp_path):
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "config.py").write_text("DEBUG = False\n")
    (tmp_path / "api.py").write_text("from core import config\n")
    syn = ScopeSynthesizer(tmp_path)
    assert Path("core/config.py") in syn.synthesize_scope("Add a health endpoint to api.py").restricted_paths
    unlocked = syn.synthesize_scope("Add a HEALTH_TIMEOUT setting to core/config.py")
    assert Path("core/config.py") not in unlocked.restricted_paths
    assert not unlocked.is_sensitive(Path("core/config.py"))


def test_owner_protected_paths_cannot_be_unlocked_by_the_prompt(tmp_path):
    import json
    (tmp_path / "db").mkdir()
    (tmp_path / "db" / "schema.sql").write_text("CREATE TABLE t (id INT);\n")
    (tmp_path / "nagare.json").write_text(json.dumps({"protected": [r"db/schema\.sql$"]}))
    contract = ScopeSynthesizer(tmp_path).synthesize_scope("Add a likes table to db/schema.sql")
    assert contract.is_sensitive(Path("db/schema.sql"))
