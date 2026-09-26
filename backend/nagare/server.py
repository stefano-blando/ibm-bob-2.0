import json
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from nagare.scope import ScopeSynthesizer
from nagare.models import TelemetrySnapshot, ScopeContract

HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>🌊 Nagare Governor — Visual Flight Recorder</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          colors: {
            ibmBlue: '#0f62fe',
            ibmNavy: '#001141',
            nagareTeal: '#00d2b4',
            shieldRed: '#fa4d56',
            panelBg: '#161616',
          }
        }
      }
    }
  </script>
  <style>
    #network-canvas { width: 100%; height: 550px; background: #121212; border-radius: 0.75rem; }
    .pulse-shield { animation: pulse 1.5s infinite; }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
  </style>
</head>
<body class="bg-black text-gray-100 font-sans min-h-screen flex flex-col">
  <!-- Top Navigation & Status -->
  <header class="border-b border-gray-800 bg-panelBg px-6 py-4 flex items-center justify-between shadow-lg">
    <div class="flex items-center space-x-3">
      <span class="text-2xl">🌊</span>
      <div>
        <h1 class="text-lg font-bold tracking-tight text-white flex items-center gap-2">
          Nagare Governor <span class="text-xs bg-ibmBlue/30 text-ibmBlue font-mono px-2 py-0.5 rounded">v0.1.0 (IBM Bob 2.0)</span>
        </h1>
        <p class="text-xs text-gray-400">Autonomous Coding Agent Flight Recorder & Active In-Flight Lane Assist</p>
      </div>
    </div>
    <div class="flex items-center space-x-6 text-sm">
      <div class="flex items-center gap-2">
        <span class="w-3 h-3 rounded-full bg-emerald-500 pulse-shield"></span>
        <span class="text-emerald-400 font-semibold" id="sys-status">GOVERNOR ACTIVE</span>
      </div>
      <div class="bg-gray-900 border border-gray-800 px-3 py-1.5 rounded-lg flex items-center gap-4">
        <div><span class="text-gray-400 text-xs">Blocked:</span> <span class="font-bold text-shieldRed text-base" id="stat-interceptions">0</span></div>
        <div><span class="text-gray-400 text-xs">Rollback:</span> <span class="font-bold text-nagareTeal text-base" id="stat-latency">&lt; 15 ms</span></div>
        <div><span class="text-gray-400 text-xs">Bobcoins Saved:</span> <span class="font-bold text-yellow-400 text-base" id="stat-coins">0.00</span></div>
      </div>
    </div>
  </header>

  <!-- Main View -->
  <main class="flex-1 p-6 grid grid-cols-1 lg:grid-cols-4 gap-6">
    <!-- Left Column: Controls & Scope Info -->
    <div class="lg:col-span-1 flex flex-col gap-6">
      <div class="bg-panelBg border border-gray-800 rounded-xl p-5 shadow">
        <h2 class="text-sm font-semibold uppercase tracking-wider text-gray-400 mb-3">Task Intent & Scope Control</h2>
        <div class="space-y-3">
          <div>
            <label class="text-xs text-gray-400 block mb-1">Agent Prompt</label>
            <input id="prompt-input" type="text" class="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-ibmBlue" value="Implement rate limiting for auth login endpoint">
          </div>
          <button id="btn-recompute" class="w-full bg-ibmBlue hover:bg-blue-600 text-white font-medium py-2 rounded-lg text-sm transition">
            Recompute Permitted Manifold
          </button>
          <button id="btn-simulate" class="w-full bg-shieldRed/20 hover:bg-shieldRed/30 border border-shieldRed/50 text-shieldRed font-medium py-2 rounded-lg text-sm transition flex items-center justify-center gap-2">
            <span>🛡️</span> Trigger Out-of-Scope Write Simulation
          </button>
        </div>
      </div>

      <!-- Scope Breakdown Panel -->
      <div class="bg-panelBg border border-gray-800 rounded-xl p-5 shadow flex-1 flex flex-col">
        <h2 class="text-sm font-semibold uppercase tracking-wider text-gray-400 mb-3">Codebase Manifold</h2>
        <div class="space-y-4 text-xs flex-1">
          <div>
            <div class="flex justify-between text-gray-400 mb-1">
              <span class="flex items-center gap-1.5"><span class="w-2 h-2 rounded-full bg-nagareTeal"></span> Permitted Lane</span>
              <span id="permitted-count" class="font-mono text-nagareTeal font-bold">0</span>
            </div>
            <div id="permitted-list" class="max-h-32 overflow-y-auto bg-gray-900/60 p-2 rounded border border-gray-800 text-gray-300 font-mono space-y-1"></div>
          </div>
          <div>
            <div class="flex justify-between text-gray-400 mb-1">
              <span class="flex items-center gap-1.5"><span class="w-2 h-2 rounded-full bg-shieldRed"></span> Shielded Sensitive</span>
              <span id="restricted-count" class="font-mono text-shieldRed font-bold">0</span>
            </div>
            <div id="restricted-list" class="max-h-32 overflow-y-auto bg-gray-900/60 p-2 rounded border border-gray-800 text-gray-300 font-mono space-y-1"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Right Column: Interactive Graph & Live Telemetry -->
    <div class="lg:col-span-3 flex flex-col gap-6">
      <div class="bg-panelBg border border-gray-800 rounded-xl p-5 shadow relative">
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-sm font-semibold uppercase tracking-wider text-gray-400 flex items-center gap-2">
            <span>Codebase AST Dependency Topology</span>
            <span class="text-xs bg-gray-800 text-gray-400 px-2 py-0.5 rounded font-normal">Real-Time Manifold Projection</span>
          </h2>
          <div class="flex items-center gap-4 text-xs">
            <span class="flex items-center gap-1"><span class="w-3 h-3 rounded-full bg-[#00d2b4]"></span> Permitted Node</span>
            <span class="flex items-center gap-1"><span class="w-3 h-3 rounded-full bg-[#fa4d56]"></span> Shielded Node</span>
            <span class="flex items-center gap-1"><span class="w-3 h-3 rounded-full bg-[#454545]"></span> Unrelated Node</span>
          </div>
        </div>
        <div id="network-canvas"></div>
      </div>

      <!-- Live Terminal / Audit Stream -->
      <div class="bg-panelBg border border-gray-800 rounded-xl p-5 shadow">
        <h2 class="text-sm font-semibold uppercase tracking-wider text-gray-400 mb-2 flex items-center gap-2">
          <span>Telemetry Audit Stream</span>
          <span class="w-2 h-2 rounded-full bg-ibmBlue pulse-shield"></span>
        </h2>
        <div id="log-terminal" class="bg-black/80 font-mono text-xs p-3 rounded-lg border border-gray-800 h-28 overflow-y-auto space-y-1 text-gray-300">
          <div class="text-gray-500">[SYS] Nagare Flight Recorder connected to kernel inotify events.</div>
        </div>
      </div>
    </div>
  </main>

  <script>
    let network = null;
    let ws = null;
    let interceptionCount = 0;

    function addLog(msg, type = 'info') {
      const term = document.getElementById('log-terminal');
      const div = document.createElement('div');
      const time = new Date().toISOString().split('T')[1].slice(0, 8);
      if (type === 'intercept') {
        div.className = 'text-shieldRed font-semibold';
        div.textContent = `[${time}] [SHIELD INTERCEPT] ${msg}`;
      } else if (type === 'permitted') {
        div.className = 'text-nagareTeal';
        div.textContent = `[${time}] [IN LANE] ${msg}`;
      } else {
        div.className = 'text-gray-400';
        div.textContent = `[${time}] ${msg}`;
      }
      term.appendChild(div);
      term.scrollTop = term.scrollHeight;
    }

    async function loadGraph() {
      const prompt = encodeURIComponent(document.getElementById('prompt-input').value);
      const res = await fetch(`/api/graph?prompt=${prompt}`);
      const data = await res.json();

      document.getElementById('permitted-count').textContent = data.permitted_count;
      document.getElementById('restricted-count').textContent = data.restricted_count;

      const pList = document.getElementById('permitted-list');
      pList.innerHTML = data.permitted.map(p => `<div>✓ ${p}</div>`).join('') || '<div class="text-gray-500">None</div>';

      const rList = document.getElementById('restricted-list');
      rList.innerHTML = data.restricted.map(r => `<div class="text-shieldRed">🛡 ${r}</div>`).join('') || '<div class="text-gray-500">None</div>';

      const nodes = new vis.DataSet(data.nodes);
      const edges = new vis.DataSet(data.edges);

      const container = document.getElementById('network-canvas');
      const options = {
        nodes: {
          shape: 'dot',
          size: 16,
          font: { color: '#ffffff', size: 12, face: 'monospace' }
        },
        edges: {
          arrows: 'to',
          color: { color: '#393939', highlight: '#00d2b4' },
          smooth: { type: 'continuous' }
        },
        physics: {
          stabilization: true,
          barnesHut: { gravitationalConstant: -3000, springLength: 95 }
        }
      };

      network = new vis.Network(container, { nodes, edges }, options);
      addLog(`Graph loaded: ${data.nodes.length} nodes, ${data.edges.length} edges.`);
    }

    function setupWebSocket() {
      const loc = window.location;
      const wsUrl = (loc.protocol === 'https:' ? 'wss://' : 'ws://') + loc.host + '/ws';
      ws = new WebSocket(wsUrl);

      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === 'interception') {
          interceptionCount++;
          document.getElementById('stat-interceptions').textContent = interceptionCount;
          document.getElementById('stat-coins').textContent = (interceptionCount * 0.45).toFixed(2);
          addLog(`Interception on '${msg.file}': Sub-15ms Micro-Rollback applied!`, 'intercept');
        } else if (msg.type === 'mutation') {
          addLog(`Permitted write on '${msg.file}' verified.`, 'permitted');
        }
      };
    }

    document.getElementById('btn-recompute').addEventListener('click', loadGraph);
    document.getElementById('btn-simulate').addEventListener('click', async () => {
      addLog('Simulating agent out-of-scope write to database/schema.sql...');
      const res = await fetch('/api/simulate_interception', { method: 'POST' });
      const data = await res.json();
      interceptionCount++;
      document.getElementById('stat-interceptions').textContent = interceptionCount;
      document.getElementById('stat-coins').textContent = (interceptionCount * 0.45).toFixed(2);
      addLog(`Shield Triggered: ${data.detail} (Restored in ${data.latency_ms}ms)`, 'intercept');
    });

    window.addEventListener('load', () => {
      loadGraph();
      setupWebSocket();
    });
  </script>
</body>
</html>
"""

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

def create_app(repo_root: Path = Path(".")) -> FastAPI:
    repo = Path(repo_root).resolve()
    app = FastAPI(title="Nagare Governor Flight Recorder")
    manager = ConnectionManager()
    latest_snapshot = TelemetrySnapshot(task_intent="Default Session", status="ACTIVE")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTML_DASHBOARD

    @app.get("/api/graph")
    async def get_graph(prompt: str = "Refactor authentication"):
        synthesizer = ScopeSynthesizer(repo)
        contract = synthesizer.synthesize_scope(prompt)

        nodes = []
        for node in synthesizer.graph.nodes:
            rel_str = str(node)
            is_perm = contract.is_permitted(node)
            is_restr = contract.is_restricted(node)

            if is_perm:
                color = "#00d2b4"
                label = f"✓ {rel_str}"
            elif is_restr:
                color = "#fa4d56"
                label = f"🛡 {rel_str}"
            else:
                color = "#525252"
                label = rel_str

            nodes.append({
                "id": rel_str,
                "label": label,
                "color": color,
                "is_permitted": is_perm,
                "is_restricted": is_restr,
            })

        edges = [
            {"from": str(u), "to": str(v)}
            for u, v in synthesizer.graph.edges
        ]

        return {
            "nodes": nodes,
            "edges": edges,
            "permitted": [str(p) for p in sorted(contract.permitted_paths)],
            "restricted": [str(p) for p in sorted(contract.restricted_paths)],
            "permitted_count": len(contract.permitted_paths),
            "restricted_count": len(contract.restricted_paths),
        }

    @app.get("/api/telemetry")
    async def get_telemetry():
        return {
            "status": latest_snapshot.status,
            "task_intent": latest_snapshot.task_intent,
            "elapsed_seconds": latest_snapshot.elapsed_seconds,
            "total_rollbacks": latest_snapshot.total_rollbacks,
            "violations": [v.to_dict() for v in latest_snapshot.violations],
        }

    @app.post("/api/simulate_interception")
    async def simulate_interception():
        import time
        t0 = time.perf_counter()
        # Simulate quick rollback
        time.sleep(0.004) # 4ms
        t1 = time.perf_counter()
        latency_ms = round((t1 - t0) * 1000.0, 2)

        event_data = {
            "type": "interception",
            "file": "database/schema.sql",
            "action": "ROLLED_BACK",
            "latency_ms": latency_ms,
            "timestamp": time.time(),
        }
        await manager.broadcast(event_data)
        return {
            "detail": "Interception simulated on database/schema.sql",
            "latency_ms": latency_ms
        }

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await manager.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket)

    return app
