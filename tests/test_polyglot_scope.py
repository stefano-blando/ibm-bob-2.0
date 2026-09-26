import pytest
from pathlib import Path
from nagare.scope import ScopeSynthesizer

def test_polyglot_typescript_and_python_scope(tmp_path):
    # Setup mock full-stack repository (FastAPI backend + Next.js / TypeScript frontend)
    # Frontend structure
    (tmp_path / "frontend" / "src" / "components").mkdir(parents=True)
    (tmp_path / "frontend" / "src" / "services").mkdir(parents=True)
    (tmp_path / "frontend" / "package.json").write_text('{"name": "frontend"}\n')
    (tmp_path / "frontend" / "package-lock.json").write_text('{}\n')

    # TS files with imports
    service_ts = tmp_path / "frontend" / "src" / "services" / "authService.ts"
    service_ts.write_text("export const login = () => {};\n")

    component_tsx = tmp_path / "frontend" / "src" / "components" / "LoginForm.tsx"
    component_tsx.write_text("import { login } from '../services/authService';\nexport default function LoginForm() {}\n")

    # Backend structure
    (tmp_path / "backend" / "api").mkdir(parents=True)
    (tmp_path / "backend" / "core").mkdir(parents=True)
    (tmp_path / "backend" / "database").mkdir(parents=True)

    auth_py = tmp_path / "backend" / "api" / "auth.py"
    auth_py.write_text("from backend.core.config import SECRET_KEY\n")

    config_py = tmp_path / "backend" / "core" / "config.py"
    config_py.write_text("SECRET_KEY = 'secret'\n")

    schema_sql = tmp_path / "backend" / "database" / "schema.sql"
    schema_sql.write_text("CREATE TABLE users (id INT);\n")

    synthesizer = ScopeSynthesizer(repo_root=tmp_path)
    
    # 1. Test TypeScript task scope
    contract_ts = synthesizer.synthesize_scope(
        "Update login form validation in frontend/src/components/LoginForm.tsx"
    )
    assert Path("frontend/src/components/LoginForm.tsx") in contract_ts.permitted_paths
    assert Path("frontend/src/services/authService.ts") in contract_ts.permitted_paths
    assert Path("frontend/package-lock.json") in contract_ts.restricted_paths
    assert Path("backend/database/schema.sql") in contract_ts.restricted_paths

    # 2. Test Python task scope
    contract_py = synthesizer.synthesize_scope(
        "Refactor auth logic in backend/api/auth.py"
    )
    assert Path("backend/api/auth.py") in contract_py.permitted_paths
    assert Path("backend/core/config.py") in contract_py.restricted_paths
    assert Path("backend/database/schema.sql") in contract_py.restricted_paths
