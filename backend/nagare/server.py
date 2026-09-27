"""Flight Recorder: live web view of a governed session.

The dashboard only shows what actually happened: the live contract (`.nagare/contract.json`),
the event log written by both enforcement layers (`.nagare/events.jsonl`) and the working-tree
changes, streamed over a WebSocket. Evidence panels read the committed result files.
"""

import asyncio
import json
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

from nagare.baseline import git_status_entries
from nagare.hooks import read_events
from nagare.models import ScopeContract
from nagare.paths import CONTRACT_FILE, should_ignore
from nagare.scope import ScopeSynthesizer

DASHBOARD_FILE = Path(__file__).parent / "static" / "dashboard.html"
EVIDENCE_RUN = Path("experiments") / "results" / "live_bob_20260927" / "summary.json"
BENCHMARK_FILE = Path("benchmarks") / "benchmark_results.json"
CASE_STUDY_DIR = Path("bob_sessions") / "live_ab_20260927"


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, data: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_text(json.dumps(data))
            except Exception:
                self.disconnect(connection)


def _contract_payload(contract: ScopeContract, live: bool) -> Dict[str, Any]:
    return {
        "live": live,
        "task": contract.task_intent,
        "policy": contract.policy.value,
        "permitted": sorted(p.as_posix() for p in contract.permitted_paths),
        "restricted": sorted(p.as_posix() for p in contract.restricted_paths),
    }


def _dirty_files(repo: Path) -> List[str]:
    try:
        entries = git_status_entries(repo)
    except Exception:
        return []
    return sorted({rel.as_posix() for _, rel in entries if not should_ignore(rel)})


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def create_app(repo_root: Path = Path(".")) -> FastAPI:
    repo = Path(repo_root).resolve()
    app = FastAPI(title="Nagare Governor Flight Recorder")
    manager = ConnectionManager()
    # The watched repo is normally `repo`; the scripted demo points it at its throwaway copy.
    state: Dict[str, Any] = {"watched": repo, "demo_running": False, "preexisting": []}
    demo_lock = threading.Lock()

    def watched() -> Path:
        return state["watched"]

    def live_contract() -> Optional[ScopeContract]:
        return ScopeContract.load(watched() / CONTRACT_FILE)

    def session_message() -> Dict[str, Any]:
        contract = live_contract()
        msg: Dict[str, Any] = {"type": "session", "active": contract is not None,
                               "demo": state["demo_running"]}
        if contract is not None:
            msg["contract"] = _contract_payload(contract, live=True)
            # Working-tree changes already present when the session started: the developer's.
            msg["preexisting"] = state["preexisting"]
        return msg

    @app.on_event("startup")
    async def tail_session_events():
        async def tail():
            offset, was_active, last_root, last_dirty, tick = 0, None, None, None, 0
            while True:
                root = watched()
                if root != last_root:
                    offset, was_active, last_root, last_dirty = 0, None, root, None
                active = (root / CONTRACT_FILE).exists()
                if active != was_active:
                    if active:
                        offset, last_dirty = 0, None
                        state["preexisting"] = await asyncio.to_thread(_dirty_files, root)
                    await manager.broadcast(session_message())
                    was_active = active
                if active:
                    events, offset = await asyncio.to_thread(read_events, root, offset)
                    for event in events:
                        await manager.broadcast({"type": "intervention", **event.to_dict()})
                    tick += 1
                    if tick % 3 == 0:
                        dirty = await asyncio.to_thread(_dirty_files, root)
                        if dirty != last_dirty:
                            await manager.broadcast({"type": "changes", "files": dirty})
                            last_dirty = dirty
                await asyncio.sleep(0.2)
        asyncio.create_task(tail())

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return DASHBOARD_FILE.read_text(encoding="utf-8")

    @app.get("/api/contract")
    async def get_contract(prompt: str = ""):
        """The live contract during a session, otherwise a preview synthesized from `prompt`."""
        contract = live_contract()
        if contract is not None:
            return _contract_payload(contract, live=True)
        if not prompt:
            return JSONResponse({"error": "no live session and no prompt"}, status_code=404)
        preview = await asyncio.to_thread(ScopeSynthesizer(repo).synthesize_scope, prompt)
        return _contract_payload(preview, live=False)

    @app.get("/api/graph")
    async def get_graph(prompt: str = "Refactor authentication"):
        synthesizer = ScopeSynthesizer(repo)
        contract = live_contract()
        if contract is None:
            contract = synthesizer.synthesize_scope(prompt)
        else:
            synthesizer.build_dependency_graph()

        nodes = []
        for node in synthesizer.graph.nodes:
            nodes.append({
                "id": node.as_posix(),
                "is_permitted": contract.is_permitted(node),
                "is_restricted": contract.is_sensitive(node),
                "imports": [v.as_posix() for v in synthesizer.graph.successors(node)],
                "imported_by": [u.as_posix() for u in synthesizer.graph.predecessors(node)],
            })
        return {
            "nodes": nodes,
            "edges": [{"from": u.as_posix(), "to": v.as_posix()} for u, v in synthesizer.graph.edges],
            "live_session": live_contract() is not None,
            "permitted": [p.as_posix() for p in sorted(contract.permitted_paths)],
            "restricted": [p.as_posix() for p in sorted(contract.restricted_paths)],
            "permitted_count": len(contract.permitted_paths),
            "restricted_count": len(contract.restricted_paths),
        }

    @app.get("/api/telemetry")
    async def get_telemetry():
        from nagare.models import TelemetrySnapshot
        events, _ = read_events(watched(), 0)
        contract = live_contract()
        snapshot = TelemetrySnapshot(task_intent="", status="ACTIVE" if contract else "IDLE")
        for event in events:
            snapshot.record_violation(event)
        return {
            "status": snapshot.status,
            "task_intent": contract.task_intent if contract else "",
            "total_denied": snapshot.total_denied,
            "total_rollbacks": snapshot.total_rollbacks,
            "total_quarantined": snapshot.total_quarantined,
            "violations": [v.to_dict() for v in snapshot.violations],
        }

    @app.get("/api/evidence")
    async def get_evidence():
        def diff(name: str) -> str:
            path = repo / CASE_STUDY_DIR / name
            return path.read_text(encoding="utf-8") if path.exists() else ""

        git_commit = ""
        try:
            r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=repo, capture_output=True, text=True)
            git_commit = r.stdout.strip()
        except Exception:
            pass

        return {
            "summary": _read_json(repo / EVIDENCE_RUN),
            "benchmarks": _read_json(repo / BENCHMARK_FILE),
            "git_commit": git_commit,
            "case_study": {"ungoverned_diff": diff("base2_diff.patch"), "governed_diff": diff("gov4_diff.patch")},
        }

    @app.post("/api/demo/scripted")
    async def run_scripted_demo(delay: float = 1.1, delays: str = ""):
        """Run the deterministic rogue-agent scenario on a throwaway copy and stream its real events.

        `delays` (comma-separated seconds, one per step) paces the steps, e.g. to match a voice-over.
        """
        from nagare.demo import run_demo

        if not demo_lock.acquire(blocking=False):
            return JSONResponse({"error": "demo already running"}, status_code=409)
        if live_contract() is not None:
            demo_lock.release()
            return JSONResponse({"error": "a governed session is live in this repo"}, status_code=409)
        clamp = lambda d: max(0.2, min(float(d), 8.0))
        try:
            pacing = [clamp(d) for d in delays.split(",") if d.strip()] if delays else clamp(delay)
        except ValueError:
            demo_lock.release()
            return JSONResponse({"error": "delays must be comma-separated numbers"}, status_code=400)
        try:
            state["demo_running"] = True
            result = await asyncio.to_thread(
                run_demo, pacing, True, lambda copy: state.update(watched=copy),
            )
            await asyncio.sleep(0.8)  # let the tail loop flush the last events and the session end
            return {"passed": result.passed, "checks": [{"label": l, "ok": ok} for l, ok in result.checks]}
        finally:
            copy = state["watched"]
            state.update(watched=repo, demo_running=False)
            demo_lock.release()
            if copy != repo:
                import shutil
                shutil.rmtree(copy.parent, ignore_errors=True)

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await manager.connect(websocket)
        msg = session_message()
        await websocket.send_text(json.dumps(msg))
        if msg["active"]:
            events, _ = read_events(watched(), 0)
            for event in events:
                await websocket.send_text(json.dumps({"type": "intervention", "replay": True, **event.to_dict()}))
            await websocket.send_text(json.dumps({"type": "changes", "files": _dirty_files(watched())}))
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket)

    return app
