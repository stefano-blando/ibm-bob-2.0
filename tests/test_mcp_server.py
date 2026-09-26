import pytest
from pathlib import Path
from nagare.mcp_server import NagareMCPServer

def test_mcp_initialize(tmp_path):
    server = NagareMCPServer(repo_root=tmp_path)
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {}
    }
    resp = server.process_message(req)
    assert resp["id"] == 1
    assert resp["result"]["serverInfo"]["name"] == "nagare-governor"
    assert "tools" in resp["result"]["capabilities"]

def test_mcp_tools_list(tmp_path):
    server = NagareMCPServer(repo_root=tmp_path)
    req = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }
    resp = server.process_message(req)
    assert resp["id"] == 2
    tool_names = [t["name"] for t in resp["result"]["tools"]]
    assert "nagare_get_scope" in tool_names
    assert "nagare_check_permission" in tool_names

def test_mcp_check_permission(tmp_path):
    # Setup files
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "routes.py").write_text("def hello(): pass\n")
    (tmp_path / "database").mkdir()
    (tmp_path / "database" / "schema.sql").write_text("CREATE TABLE t (id INT);\n")

    server = NagareMCPServer(repo_root=tmp_path)

    # Check permission for restricted file
    req_denied = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "nagare_check_permission",
            "arguments": {"file_path": "database/schema.sql"}
        }
    }
    resp_denied = server.process_message(req_denied)
    text_denied = resp_denied["result"]["content"][0]["text"]
    assert "PERMISSION DENIED" in text_denied

    # Check permission for permitted file
    req_allowed = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "nagare_check_permission",
            "arguments": {"file_path": "api/routes.py"}
        }
    }
    resp_allowed = server.process_message(req_allowed)
    text_allowed = resp_allowed["result"]["content"][0]["text"]
    assert "PERMISSION GRANTED" in text_allowed
