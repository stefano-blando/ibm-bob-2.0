"""Nagare Governor Model Context Protocol (MCP) Server

Exposes boundary checking and dynamic scope querying to AI agents (such as IBM Bob 2.0)
via standard stdio JSON-RPC 2.0.
"""

import sys
import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from nagare.scope import ScopeSynthesizer
from nagare.models import ScopeContract, ViolationAction, ViolationEvent
from nagare.hooks import append_event
from nagare.paths import CONTRACT_FILE, DIRECTIVE_FILE

logging.basicConfig(level=logging.ERROR, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("nagare.mcp")

TOOLS = [
    {
        "name": "nagare_get_scope",
        "description": "Get the currently active scope contract, including all permitted files and strictly restricted files.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "description": "Optional task prompt to dynamically synthesize scope if not already defined."
                }
            }
        }
    },
    {
        "name": "nagare_check_permission",
        "description": "Check whether a specific file path is permitted to be modified under the active Nagare Governor policy.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Relative path of the file to check (e.g. 'demo_app/database/schema.sql' or 'demo_app/api/routes/auth.py')."
                }
            },
            "required": ["file_path"]
        }
    }
]

class NagareMCPServer:
    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = Path(repo_root or Path.cwd()).resolve()
        self.synthesizer = ScopeSynthesizer(self.repo_root)

    def active_contract(self, intent: Optional[str] = None) -> ScopeContract:
        """The contract the governor is enforcing right now; falls back to synthesizing one."""
        live = ScopeContract.load(self.repo_root / CONTRACT_FILE)
        if live is not None:
            return live
        return self.synthesizer.synthesize_scope(intent or "Current Task")

    def handle_tool_call(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        directive_file = self.repo_root / DIRECTIVE_FILE

        if name == "nagare_get_scope":
            contract = self.active_contract(arguments.get("intent"))
            
            permitted = sorted(str(p) for p in contract.permitted_paths)
            restricted = sorted(str(p) for p in contract.restricted_paths)

            directive_text = ""
            if directive_file.exists():
                directive_text = f"\n\nActive In-Flight Directive:\n{directive_file.read_text()}"

            result_text = (
                f"=== NAGARE GOVERNOR SCOPE CONTRACT ===\n"
                f"Permitted Files ({len(permitted)}):\n" + "\n".join(f"  ✓ {p}" for p in permitted) + "\n\n"
                f"Restricted Files ({len(restricted)}):\n" + "\n".join(f"  ✕ {p}" for p in restricted) +
                directive_text
            )
            return {"content": [{"type": "text", "text": result_text}]}

        elif name == "nagare_check_permission":
            file_path_str = arguments.get("file_path", "")
            target_path = Path(file_path_str)

            contract = self.active_contract()
            rel = target_path
            if rel.is_absolute():
                try:
                    rel = rel.resolve().relative_to(self.repo_root)
                except ValueError:
                    pass
            decision = contract.decide(rel, is_new=not (self.repo_root / rel).exists())
            is_permitted = decision in (ViolationAction.ALLOWED, ViolationAction.WARNED)
            is_restricted = not is_permitted

            if is_restricted or not is_permitted:
                if (self.repo_root / CONTRACT_FILE).exists():
                    append_event(self.repo_root, ViolationEvent(
                        file_path=rel, action=ViolationAction.DENIED, timestamp=time.time(),
                        steering_prompt=f"MCP advisory: '{rel.as_posix()}' is outside the active scope contract.",
                        layer="mcp", detail="nagare_check_permission",
                    ))
                text = (
                    f"⛔ PERMISSION DENIED: Modification of '{file_path_str}' is STRICTLY PROHIBITED by Nagare Governor.\n"
                    f"Reason: This file is out-of-scope or contains critical infrastructure/schemas.\n"
                    f"Any writes to this file will be blocked or automatically reverted.\n"
                    f"Please implement your solution within permitted files."
                )
            else:
                text = (
                    f"✅ PERMISSION GRANTED: Modification of '{file_path_str}' is permitted within the current task scope."
                )

            return {"content": [{"type": "text", "text": text}]}

        else:
            return {"content": [{"type": "text", "text": f"Unknown tool: {name}"}], "isError": True}

    def process_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        msg_id = message.get("id")
        method = message.get("method")
        params = message.get("params", {})

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "nagare-governor", "version": "0.3.0"}
                }
            }

        elif method == "notifications/initialized":
            return None

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": TOOLS}
            }

        elif method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            call_res = self.handle_tool_call(tool_name, tool_args)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": call_res
            }

        elif method == "ping":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

        else:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"}
            }

    def run_stdio(self):
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                resp = self.process_message(msg)
                if resp is not None:
                    sys.stdout.write(json.dumps(resp) + "\n")
                    sys.stdout.flush()
            except Exception as e:
                logger.error(f"Error processing MCP message: {e}")

if __name__ == "__main__":
    server = NagareMCPServer()
    server.run_stdio()
