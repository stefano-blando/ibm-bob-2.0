import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from nagare.server import create_app

def test_web_server_endpoints(tmp_path):
    # Setup mock repo
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "auth.py").write_text("import os\n")
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "config.py").write_text("SECRET = 'abc'\n")

    app = create_app(repo_root=tmp_path)
    client = TestClient(app)

    # 1. Test HTML Dashboard
    res_html = client.get("/")
    assert res_html.status_code == 200
    assert "Nagare Governor" in res_html.text
    assert "Flight Recorder" in res_html.text

    # 2. Test Graph API
    res_graph = client.get("/api/graph?prompt=Refactor%20auth")
    assert res_graph.status_code == 200
    data = res_graph.json()
    assert "nodes" in data
    assert "edges" in data
    assert any(n["id"] == "api/auth.py" for n in data["nodes"])
    assert any(n["id"] == "core/config.py" for n in data["nodes"])

    # 3. Test Telemetry API
    res_telem = client.get("/api/telemetry")
    assert res_telem.status_code == 200
    telem = res_telem.json()
    assert "status" in telem
    assert "total_rollbacks" in telem


def test_contract_preview_and_evidence(tmp_path):
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "auth.py").write_text("import os\n")
    (tmp_path / "db").mkdir()
    (tmp_path / "db" / "schema.sql").write_text("CREATE TABLE users (id INT);\n")
    client = TestClient(create_app(repo_root=tmp_path))

    # No live session and no prompt: nothing to show.
    assert client.get("/api/contract").status_code == 404

    preview = client.get("/api/contract?prompt=Add%20rate%20limiting%20to%20api/auth.py").json()
    assert preview["live"] is False
    assert "api/auth.py" in preview["permitted"]
    # Non-code protected files (not import-graph nodes) must still be listed.
    assert "db/schema.sql" in preview["restricted"]

    evidence = client.get("/api/evidence").json()
    assert evidence["summary"] is None and evidence["benchmarks"] is None
    assert evidence["case_study"] == {"ungoverned_diff": "", "governed_diff": ""}


def test_scripted_demo_endpoint_runs_real_scenario(tmp_path):
    client = TestClient(create_app(repo_root=tmp_path))
    res = client.post("/api/demo/scripted?delay=0.2")
    assert res.status_code == 200
    data = res.json()
    assert data["passed"], data["checks"]
    labels = [c["label"] for c in data["checks"]]
    assert "hook denied write_file on schema.sql" in labels


def test_scripted_demo_accepts_per_step_pacing(tmp_path):
    client = TestClient(create_app(repo_root=tmp_path))
    assert client.post("/api/demo/scripted?delays=0.2,oops").status_code == 400
    res = client.post("/api/demo/scripted?delays=" + ",".join(["0.2"] * 8))
    assert res.status_code == 200 and res.json()["passed"]
