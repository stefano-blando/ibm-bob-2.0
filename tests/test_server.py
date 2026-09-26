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
