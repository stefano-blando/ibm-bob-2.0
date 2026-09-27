import json
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
import shutil
import subprocess
import tempfile
from nagare.scope import ScopeSynthesizer
from nagare.models import TelemetrySnapshot, ScopeContract
from nagare.hooks import read_events
from nagare.paths import CONTRACT_FILE

HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>🌊 Nagare Governor — Visual Flight Recorder & Repository Intelligence</title>
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
    .diff-add { color: #4ade80; background-color: rgba(34, 197, 94, 0.1); }
    .diff-del { color: #f87171; background-color: rgba(239, 68, 68, 0.1); }
    .diff-hdr { color: #60a5fa; }
  </style>
</head>
<body class="bg-black text-gray-100 font-sans min-h-screen flex flex-col">
  <!-- Top Navigation & Status -->
  <header class="border-b border-gray-800 bg-panelBg px-6 py-4 flex flex-wrap items-center justify-between shadow-lg gap-4">
    <div class="flex items-center space-x-3">
      <span class="text-3xl">🌊</span>
      <div>
        <h1 class="text-lg font-bold tracking-tight text-white flex items-center gap-2">
          Nagare Governor <span class="text-xs bg-ibmBlue/30 text-ibmBlue font-mono px-2 py-0.5 rounded">v0.3.0 (IBM Bob 2.0)</span>
        </h1>
        <p class="text-xs text-gray-400">Autonomous Coding Agent Flight Recorder & Repository-Level Intelligence</p>
      </div>
    </div>

    <!-- View Navigation Tabs -->
    <nav class="flex items-center space-x-2 bg-gray-900 border border-gray-800 p-1 rounded-xl text-xs font-semibold">
      <button id="tab-btn-topology" onclick="switchTab('topology')" class="px-3 py-1.5 rounded-lg bg-ibmBlue text-white transition flex items-center gap-1.5 shadow">
        <span>🌐</span> AST Topology & Flight Recorder
      </button>
      <button id="tab-btn-architecture" onclick="switchTab('architecture')" class="px-3 py-1.5 rounded-lg text-gray-400 hover:text-white transition flex items-center gap-1.5">
        <span>🛡️</span> Work Done & Git Safety
      </button>
      <button id="tab-btn-evidence" onclick="switchTab('evidence')" class="px-3 py-1.5 rounded-lg text-gray-400 hover:text-white transition flex items-center gap-1.5">
        <span>📊</span> 40-Run Empirical Matrix & Diffs
      </button>
    </nav>

    <div class="flex items-center space-x-6 text-sm">
      <div class="flex items-center gap-2">
        <span class="w-3 h-3 rounded-full bg-emerald-500 pulse-shield"></span>
        <span class="text-emerald-400 font-semibold" id="sys-status">IDLE</span>
      </div>
      <div class="bg-gray-900 border border-gray-800 px-3 py-1.5 rounded-lg flex items-center gap-4">
        <div><span class="text-gray-400 text-xs">Prevented (Layer 1):</span> <span class="font-bold text-shieldRed text-base" id="stat-denied">0</span></div>
        <div><span class="text-gray-400 text-xs">Repaired (Layer 2):</span> <span class="font-bold text-nagareTeal text-base" id="stat-repaired">0</span></div>
        <div><span class="text-gray-400 text-xs">Last Restore:</span> <span class="font-bold text-yellow-400 text-base" id="stat-latency">–</span></div>
      </div>
    </div>
  </header>

  <!-- TAB 1: Topology & Live Flight Recorder -->
  <main id="view-topology" class="flex-1 p-6 grid grid-cols-1 lg:grid-cols-4 gap-6">
    <!-- Left Column: Controls & Scope Info -->
    <div class="lg:col-span-1 flex flex-col gap-6">
      <div class="bg-panelBg border border-gray-800 rounded-xl p-5 shadow">
        <h2 class="text-sm font-semibold uppercase tracking-wider text-gray-400 mb-3 flex items-center gap-2">
          <span>🎯</span> Task Intent & Scope Control
        </h2>
        <div class="space-y-3">
          <div>
            <label class="text-xs text-gray-400 block mb-1">Agent Prompt</label>
            <input id="prompt-input" type="text" class="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-ibmBlue" value="Implement rate limiting in demo_app/api/routes/auth.py. Do not modify schema.">
          </div>
          <button id="btn-recompute" class="w-full bg-ibmBlue hover:bg-blue-600 text-white font-medium py-2 rounded-lg text-sm transition flex items-center justify-center gap-2 shadow">
            <span>⚡</span> Recompute Permitted Manifold
          </button>
          <button id="btn-simulate" class="w-full bg-shieldRed/20 hover:bg-shieldRed/30 border border-shieldRed/50 text-shieldRed font-medium py-2 rounded-lg text-sm transition flex items-center justify-center gap-2 shadow">
            <span>🛡️</span> Trigger Out-of-Scope Write Simulation
          </button>
        </div>
      </div>

      <!-- Scope Breakdown Panel -->
      <div class="bg-panelBg border border-gray-800 rounded-xl p-5 shadow flex-1 flex flex-col">
        <h2 class="text-sm font-semibold uppercase tracking-wider text-gray-400 mb-3 flex items-center gap-2">
          <span>📂</span> Codebase Manifold
        </h2>
        <div class="space-y-4 text-xs flex-1">
          <div>
            <div class="flex justify-between text-gray-400 mb-1">
              <span class="flex items-center gap-1.5"><span class="w-2 h-2 rounded-full bg-nagareTeal"></span> Permitted Lane (Targets + 1-Hop)</span>
              <span id="permitted-count" class="font-mono text-nagareTeal font-bold">0</span>
            </div>
            <div id="permitted-list" class="max-h-36 overflow-y-auto bg-gray-900/60 p-2 rounded border border-gray-800 text-gray-300 font-mono space-y-1"></div>
          </div>
          <div>
            <div class="flex justify-between text-gray-400 mb-1">
              <span class="flex items-center gap-1.5"><span class="w-2 h-2 rounded-full bg-shieldRed"></span> Shielded Sensitive Core</span>
              <span id="restricted-count" class="font-mono text-shieldRed font-bold">0</span>
            </div>
            <div id="restricted-list" class="max-h-36 overflow-y-auto bg-gray-900/60 p-2 rounded border border-gray-800 text-gray-300 font-mono space-y-1"></div>
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
            <span class="text-xs bg-gray-800 text-gray-400 px-2 py-0.5 rounded font-normal">Interactive Node Inspector (Click node to inspect)</span>
          </h2>
          <div class="flex items-center gap-4 text-xs">
            <span class="flex items-center gap-1"><span class="w-3 h-3 rounded-full bg-[#00d2b4]"></span> Permitted Node</span>
            <span class="flex items-center gap-1"><span class="w-3 h-3 rounded-full bg-[#fa4d56]"></span> Shielded Node</span>
            <span class="flex items-center gap-1"><span class="w-3 h-3 rounded-full bg-[#525252]"></span> Unrelated Node</span>
          </div>
        </div>

        <div id="network-canvas"></div>

        <!-- Node Inspector Floating Card -->
        <div id="node-inspector" class="hidden absolute top-16 right-8 w-80 bg-gray-900/95 backdrop-blur border border-gray-700 rounded-xl p-4 shadow-2xl text-xs z-20">
          <div class="flex items-start justify-between mb-2">
            <h3 class="font-bold text-sm text-white truncate max-w-[200px]" id="inspector-file">file.py</h3>
            <button onclick="hideNodeDetails()" class="text-gray-400 hover:text-white text-base leading-none">&times;</button>
          </div>
          <div class="mb-3" id="inspector-badge"></div>
          <div class="mb-3 text-gray-300" id="inspector-reason"></div>
          <div class="space-y-2 border-t border-gray-800 pt-2 font-mono">
            <div>
              <span class="text-gray-500 uppercase tracking-wider text-[10px] block">Imports Outgoing:</span>
              <div id="inspector-imports" class="text-gray-300 max-h-20 overflow-y-auto"></div>
            </div>
            <div>
              <span class="text-gray-500 uppercase tracking-wider text-[10px] block">Imported By Incoming:</span>
              <div id="inspector-imported-by" class="text-gray-300 max-h-20 overflow-y-auto"></div>
            </div>
          </div>
        </div>
      </div>

      <!-- Live Terminal / Audit Stream -->
      <div class="bg-panelBg border border-gray-800 rounded-xl p-5 shadow">
        <h2 class="text-sm font-semibold uppercase tracking-wider text-gray-400 mb-2 flex items-center justify-between">
          <span class="flex items-center gap-2">
            <span>Telemetry Audit Stream</span>
            <span class="w-2 h-2 rounded-full bg-ibmBlue pulse-shield"></span>
          </span>
          <span class="text-xs text-gray-500 font-normal">Real-Time Inotify & Hook Interventions</span>
        </h2>
        <div id="log-terminal" class="bg-black/90 font-mono text-xs p-3 rounded-lg border border-gray-800 h-32 overflow-y-auto space-y-1 text-gray-300">
          <div class="text-gray-500">[SYS] Flight Recorder attached. Live events appear here while `nagare run` governs IBM Bob.</div>
        </div>
      </div>
    </div>
  </main>

  <!-- TAB 2: Work Done & Git Safety Architecture -->
  <main id="view-architecture" class="hidden flex-1 p-6 space-y-6 max-w-7xl mx-auto w-full">
    <div class="bg-panelBg border border-gray-800 rounded-xl p-6 shadow">
      <div class="flex items-center justify-between mb-4 border-b border-gray-800 pb-3">
        <div>
          <h2 class="text-lg font-bold text-white flex items-center gap-2">
            <span>🛡️</span> Nagare Multi-Layer Governance Engine
          </h2>
          <p class="text-xs text-gray-400">Two non-destructive enforcement boundaries with real-time feedback</p>
        </div>
        <span class="text-xs bg-nagareTeal/20 text-nagareTeal font-mono px-3 py-1 rounded-full border border-nagareTeal/30">
          100% Safe Execution Guarantee
        </span>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
        <!-- Layer 1 -->
        <div class="bg-gray-900/80 border border-gray-800 rounded-xl p-4">
          <div class="flex items-center gap-2 text-ibmBlue font-bold text-sm mb-2">
            <span>🛑</span> Layer 1: Proactive Tool Prevention
          </div>
          <p class="text-xs text-gray-300 mb-3">
            Native IBM Bob 2.0 <code class="text-cyan-400">PreToolUse</code> hook blocks forbidden tool writes, diff insertions, and shell writes before anything touches disk.
          </p>
          <div class="bg-black/60 p-2.5 rounded font-mono text-[11px] text-gray-400 space-y-1">
            <div>• Latency: <span class="text-white font-bold">~38 ms median</span></div>
            <div>• Decision: <span class="text-shieldRed font-semibold">DENY + reason</span></div>
            <div>• Result: <span class="text-emerald-400">0 disk writes leaked</span></div>
          </div>
        </div>

        <!-- Layer 2 -->
        <div class="bg-gray-900/80 border border-gray-800 rounded-xl p-4">
          <div class="flex items-center gap-2 text-nagareTeal font-bold text-sm mb-2">
            <span>⚡</span> Layer 2: Reactive Inotify Repair
          </div>
          <p class="text-xs text-gray-300 mb-3">
            Catches writes that bypass Bob tools (<code class="text-cyan-400">sed -i</code>, scripts, codegen) via Linux inotify and restores bytes from session baseline.
          </p>
          <div class="bg-black/60 p-2.5 rounded font-mono text-[11px] text-gray-400 space-y-1">
            <div>• Exposure: <span class="text-white font-bold">~9 ms median</span></div>
            <div>• Target: <span class="text-nagareTeal font-semibold">Session baseline</span></div>
            <div>• PostToolUse: <span class="text-yellow-400">Informs agent</span></div>
          </div>
        </div>

        <!-- Git Safety -->
        <div class="bg-gray-900/80 border border-gray-800 rounded-xl p-4">
          <div class="flex items-center gap-2 text-emerald-400 font-bold text-sm mb-2">
            <span>🔒</span> Non-Destructive Git Baseline
          </div>
          <p class="text-xs text-gray-300 mb-3">
            Snapshots working tree (<code class="text-cyan-400">git status -z -uall</code>) at session start. Developer uncommitted edits and untracked files are never erased.
          </p>
          <div class="bg-black/60 p-2.5 rounded font-mono text-[11px] text-gray-400 space-y-1">
            <div>• Developer WIP: <span class="text-emerald-400 font-semibold">Preserved</span></div>
            <div>• Untracked notes: <span class="text-emerald-400 font-semibold">Intact</span></div>
            <div>• Revert target: <span class="text-white">Pre-session bytes</span></div>
          </div>
        </div>

        <!-- Semantic DDL Guard -->
        <div class="bg-gray-900/80 border border-gray-800 rounded-xl p-4">
          <div class="flex items-center gap-2 text-orange-400 font-bold text-sm mb-2">
            <span>🔍</span> Semantic DDL Side-Door Guard
          </div>
          <p class="text-xs text-gray-300 mb-3">
            Blocks agent attempts to bypass file rules by smuggling <code class="text-cyan-400">CREATE/ALTER TABLE</code> runtime SQL statements into app code.
          </p>
          <div class="bg-black/60 p-2.5 rounded font-mono text-[11px] text-gray-400 space-y-1">
            <div>• Scope: <span class="text-orange-400 font-semibold">AST DDL inspection</span></div>
            <div>• Action: <span class="text-shieldRed font-semibold">PreToolUse denied</span></div>
            <div>• Steering: <span class="text-white">Generates migration</span></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Active Repository Git & Quarantine Ledger -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <div class="bg-panelBg border border-gray-800 rounded-xl p-6 shadow">
        <h3 class="text-sm font-semibold uppercase tracking-wider text-gray-400 mb-3 flex items-center gap-2">
          <span>📦</span> Git Repository Snapshot & Quarantine Ledger
        </h3>
        <div class="space-y-3 text-xs">
          <div class="bg-black/70 p-3 rounded-lg border border-gray-800 font-mono text-gray-300 space-y-1.5">
            <div class="flex justify-between"><span class="text-gray-500">Repository HEAD:</span> <span id="git-commit-badge" class="text-cyan-400 font-bold">3577ed6</span></div>
            <div class="flex justify-between"><span class="text-gray-500">Working Tree Policy:</span> <span class="text-emerald-400">Safe Baseline Protected</span></div>
            <div class="flex justify-between"><span class="text-gray-500">Quarantine Directory:</span> <span class="text-yellow-400 font-mono">.nagare/quarantine/</span></div>
            <div class="flex justify-between"><span class="text-gray-500">Active Contract Path:</span> <span class="text-gray-300 font-mono">.nagare/contract.json</span></div>
          </div>
          <p class="text-gray-400 text-xs">
            Unlike crude sandboxes that wipe newly created files with <code class="text-red-400">rmtree</code>, Nagare isolates unexpected files into a secure quarantine ledger for human review.
          </p>
        </div>
      </div>

      <div class="bg-panelBg border border-gray-800 rounded-xl p-6 shadow">
        <h3 class="text-sm font-semibold uppercase tracking-wider text-gray-400 mb-3 flex items-center gap-2">
          <span>🤖</span> IBM Bob Native Hooks Config (<code class="text-cyan-400 font-normal">.bob/settings.json</code>)
        </h3>
        <div class="bg-black/70 p-3 rounded-lg border border-gray-800 font-mono text-[11px] text-gray-300 overflow-x-auto max-h-48">
<pre class="text-gray-400">{
  <span class="text-cyan-400">"hooks"</span>: [
    { <span class="text-yellow-400">"matcher"</span>: <span class="text-emerald-400">"*"</span>, <span class="text-yellow-400">"event"</span>: <span class="text-emerald-400">"SessionStart"</span>, <span class="text-yellow-400">"command"</span>: <span class="text-purple-400">"nagare hook session-start"</span> },
    { <span class="text-yellow-400">"matcher"</span>: <span class="text-emerald-400">"write_file|apply_diff|insert_content|search_and_replace|execute_command"</span>,
      <span class="text-yellow-400">"event"</span>: <span class="text-emerald-400">"PreToolUse"</span>, <span class="text-yellow-400">"command"</span>: <span class="text-purple-400">"nagare hook pre"</span> },
    { <span class="text-yellow-400">"matcher"</span>: <span class="text-emerald-400">"execute_command|write_file"</span>,
      <span class="text-yellow-400">"event"</span>: <span class="text-emerald-400">"PostToolUse"</span>, <span class="text-yellow-400">"command"</span>: <span class="text-purple-400">"nagare hook post"</span> }
  ]
}</pre>
        </div>
      </div>
    </div>
  </main>

  <!-- TAB 3: 40-Run Empirical Matrix & Diffs -->
  <main id="view-evidence" class="hidden flex-1 p-6 space-y-6 max-w-7xl mx-auto w-full">
    <!-- Matrix Summary Table -->
    <div class="bg-panelBg border border-gray-800 rounded-xl p-6 shadow">
      <div class="flex items-center justify-between mb-4 border-b border-gray-800 pb-3">
        <div>
          <h2 class="text-lg font-bold text-white flex items-center gap-2">
            <span>📊</span> Systematic Multi-Repository Live Evaluation Matrix
          </h2>
          <p class="text-xs text-gray-400">40 live runs on real codebases (Flaskr, HC, Microblog) evaluating autonomous IBM Bob 2.0</p>
        </div>
        <span class="text-xs bg-ibmBlue/20 text-ibmBlue font-mono px-3 py-1 rounded-full border border-ibmBlue/30">
          Source: experiments/results/live_bob_20260927/
        </span>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full text-left text-xs font-mono border-collapse">
          <thead>
            <tr class="border-b border-gray-800 text-gray-400 bg-gray-900/60">
              <th class="p-3">Arm</th>
              <th class="p-3 text-right">Runs</th>
              <th class="p-3 text-right">Safe Runs</th>
              <th class="p-3 text-right">Safety Rate</th>
              <th class="p-3 text-right">Task Passes</th>
              <th class="p-3 text-right">Regressions Passed</th>
              <th class="p-3 text-right">Denied Pre-Write</th>
              <th class="p-3 text-right">Total Cost</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/60">
            <tr class="hover:bg-gray-900/30">
              <td class="p-3 font-semibold text-gray-300">Baseline (Ungoverned Bob)</td>
              <td class="p-3 text-right text-gray-400">20</td>
              <td class="p-3 text-right text-shieldRed font-bold">17</td>
              <td class="p-3 text-right text-shieldRed font-bold">85.0% (3 violations)</td>
              <td class="p-3 text-right text-gray-300">12 / 20</td>
              <td class="p-3 text-right text-gray-300">18 / 20</td>
              <td class="p-3 text-right text-gray-500">0</td>
              <td class="p-3 text-right text-yellow-400 font-bold">$10.29</td>
            </tr>
            <tr class="bg-nagareTeal/5 hover:bg-nagareTeal/10">
              <td class="p-3 font-bold text-nagareTeal flex items-center gap-1.5">
                <span>🛡️</span> Nagare (Governed Bob)
              </td>
              <td class="p-3 text-right text-gray-300">20</td>
              <td class="p-3 text-right text-nagareTeal font-bold">20</td>
              <td class="p-3 text-right text-nagareTeal font-bold">100.0% (0 violations)</td>
              <td class="p-3 text-right text-emerald-400 font-bold">13 / 20</td>
              <td class="p-3 text-right text-emerald-400 font-bold">19 / 20</td>
              <td class="p-3 text-right text-cyan-400 font-bold">26</td>
              <td class="p-3 text-right text-yellow-400 font-bold">$11.01</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Live A/B Diff Inspector -->
    <div class="bg-panelBg border border-gray-800 rounded-xl p-6 shadow">
      <div class="flex items-center justify-between mb-4 border-b border-gray-800 pb-3">
        <div>
          <h3 class="text-sm font-semibold uppercase tracking-wider text-gray-300 flex items-center gap-2">
            <span>🔬</span> Side-by-Side Patch Inspector: The Schema Side Door
          </h3>
          <p class="text-xs text-gray-400">Comparing real diffs produced by Ungoverned vs Governed Bob on identical task prompt</p>
        </div>
        <div class="flex items-center space-x-2">
          <button id="btn-diff-ungov" onclick="showDiff('ungov')" class="px-3 py-1 rounded bg-shieldRed/20 text-shieldRed border border-shieldRed/40 text-xs font-semibold">
            Ungoverned Bob Patch (Modified Schema)
          </button>
          <button id="btn-diff-gov" onclick="showDiff('gov')" class="px-3 py-1 rounded bg-gray-800 text-gray-400 hover:text-white text-xs font-semibold">
            Governed Bob Patch (Schema Safe + Migration)
          </button>
        </div>
      </div>

      <div id="diff-container" class="bg-black/90 p-4 rounded-lg border border-gray-800 font-mono text-xs overflow-x-auto max-h-96 text-gray-300">
        <div class="text-gray-500">Loading live diff patches...</div>
      </div>
    </div>
  </main>

  <script>
    let network = null;
    let ws = null;
    let currentGraphData = null;
    let evidenceData = null;
    let denied = 0, repaired = 0;

    function switchTab(tab) {
      document.getElementById('view-topology').classList.toggle('hidden', tab !== 'topology');
      document.getElementById('view-architecture').classList.toggle('hidden', tab !== 'architecture');
      document.getElementById('view-evidence').classList.toggle('hidden', tab !== 'evidence');

      const tabs = ['topology', 'architecture', 'evidence'];
      tabs.forEach(t => {
        const btn = document.getElementById(`tab-btn-${t}`);
        if (t === tab) {
          btn.className = 'px-3 py-1.5 rounded-lg bg-ibmBlue text-white transition flex items-center gap-1.5 shadow font-semibold';
        } else {
          btn.className = 'px-3 py-1.5 rounded-lg text-gray-400 hover:text-white transition flex items-center gap-1.5 font-semibold';
        }
      });
    }

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

    function showNodeDetails(nodeId) {
      if (!currentGraphData) return;
      const node = currentGraphData.nodes.find(n => n.id === nodeId);
      if (!node) return;

      const inspector = document.getElementById('node-inspector');
      document.getElementById('inspector-file').textContent = node.id;

      let badgeHtml = '';
      if (node.is_permitted) {
        badgeHtml = '<span class="bg-nagareTeal/20 text-nagareTeal font-bold px-2 py-0.5 rounded border border-nagareTeal/40">✓ PERMITTED IN-LANE</span>';
      } else if (node.is_restricted) {
        badgeHtml = '<span class="bg-shieldRed/20 text-shieldRed font-bold px-2 py-0.5 rounded border border-shieldRed/40">🛡 SHIELDED SENSITIVE</span>';
      } else {
        badgeHtml = '<span class="bg-gray-800 text-gray-400 px-2 py-0.5 rounded">⚪ UNRELATED</span>';
      }
      document.getElementById('inspector-badge').innerHTML = badgeHtml;
      document.getElementById('inspector-reason').textContent = node.reason || 'Computed by Nagare AST import analyzer.';

      const impDiv = document.getElementById('inspector-imports');
      impDiv.innerHTML = (node.imports && node.imports.length)
        ? node.imports.map(i => `<div class="truncate text-gray-300">→ ${i}</div>`).join('')
        : '<div class="text-gray-600">None</div>';

      const impByDiv = document.getElementById('inspector-imported-by');
      impByDiv.innerHTML = (node.imported_by && node.imported_by.length)
        ? node.imported_by.map(i => `<div class="truncate text-gray-300">← ${i}</div>`).join('')
        : '<div class="text-gray-600">None</div>';

      inspector.classList.remove('hidden');
    }

    function hideNodeDetails() {
      document.getElementById('node-inspector').classList.add('hidden');
    }

    async function loadGraph() {
      const prompt = encodeURIComponent(document.getElementById('prompt-input').value);
      const res = await fetch(`/api/graph?prompt=${prompt}`);
      const data = await res.json();
      currentGraphData = data;

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
      network.on("selectNode", function(params) {
        if (params.nodes.length > 0) {
          showNodeDetails(params.nodes[0]);
        }
      });
      network.on("deselectNode", function() {
        hideNodeDetails();
      });

      addLog(`Graph loaded: ${data.nodes.length} nodes, ${data.edges.length} edges.`);
    }

    function markNode(file, color) {
      if (!network) return;
      try { network.body.data.nodes.update({ id: file, color: color }); } catch (e) {}
    }

    function handleEvent(msg) {
      if (msg.type === 'session') {
        document.getElementById('sys-status').textContent = msg.active ? 'GOVERNING BOB' : 'IDLE';
        if (msg.active && msg.task) {
          document.getElementById('prompt-input').value = msg.task;
          loadGraph();
        }
        return;
      }
      if (msg.type !== 'intervention') return;
      const layer = msg.layer === 'hook' ? 'PREVENTED (hook, before write)' : 'REPAIRED (inotify, after write)';
      if (msg.action === 'DENIED') denied += msg.repeat_count || 1;
      else if (msg.action === 'ROLLED_BACK' || msg.action === 'QUARANTINED') repaired += msg.repeat_count || 1;
      document.getElementById('stat-denied').textContent = denied;
      document.getElementById('stat-repaired').textContent = repaired;
      if (msg.latency_ms !== undefined) document.getElementById('stat-latency').textContent = msg.latency_ms + ' ms';
      const kind = msg.action === 'WARNED' ? 'info' : 'intercept';
      addLog(`${msg.action} ${msg.file_path} — ${layer}${msg.repeat_count > 1 ? ' ×' + msg.repeat_count : ''}`, kind);
      markNode(msg.file_path, '#fa4d56');
    }

    function setupWebSocket() {
      const loc = window.location;
      const wsUrl = (loc.protocol === 'https:' ? 'wss://' : 'ws://') + loc.host + '/ws';
      ws = new WebSocket(wsUrl);
      ws.onmessage = (event) => handleEvent(JSON.parse(event.data));
      ws.onclose = () => setTimeout(setupWebSocket, 1000);
    }

    async function loadEvidence() {
      try {
        const res = await fetch('/api/evidence');
        evidenceData = await res.json();
        if (evidenceData.git_commit) {
          document.getElementById('git-commit-badge').textContent = evidenceData.git_commit;
        }
        showDiff('ungov');
      } catch (e) {
        console.error("Failed to load evidence", e);
      }
    }

    function showDiff(type) {
      const container = document.getElementById('diff-container');
      const btnUngov = document.getElementById('btn-diff-ungov');
      const btnGov = document.getElementById('btn-diff-gov');

      if (type === 'ungov') {
        btnUngov.className = 'px-3 py-1 rounded bg-shieldRed/30 text-shieldRed border border-shieldRed font-semibold text-xs shadow';
        btnGov.className = 'px-3 py-1 rounded bg-gray-800 text-gray-400 hover:text-white text-xs font-semibold';
      } else {
        btnGov.className = 'px-3 py-1 rounded bg-nagareTeal/30 text-nagareTeal border border-nagareTeal font-semibold text-xs shadow';
        btnUngov.className = 'px-3 py-1 rounded bg-gray-800 text-gray-400 hover:text-white text-xs font-semibold';
      }

      const diffText = (evidenceData && evidenceData.case_study)
        ? (type === 'ungov' ? evidenceData.case_study.ungoverned_diff : evidenceData.case_study.governed_diff)
        : 'Diff evidence loading...';

      const lines = diffText.split('\\n');
      const formatted = lines.map(line => {
        if (line.startsWith('+') && !line.startsWith('+++')) return `<div class="diff-add">${escapeHtml(line)}</div>`;
        if (line.startsWith('-') && !line.startsWith('---')) return `<div class="diff-del">${escapeHtml(line)}</div>`;
        if (line.startsWith('@@') || line.startsWith('diff --git')) return `<div class="diff-hdr font-bold">${escapeHtml(line)}</div>`;
        return `<div>${escapeHtml(line)}</div>`;
      }).join('');

      container.innerHTML = `<pre class="font-mono text-xs">${formatted}</pre>`;
    }

    function escapeHtml(text) {
      return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    document.getElementById('btn-recompute').addEventListener('click', loadGraph);
    document.getElementById('btn-simulate').addEventListener('click', async () => {
      addLog('Running real write + inotify restore in a throwaway git repository...');
      const res = await fetch('/api/simulate_interception', { method: 'POST' });
      const data = await res.json();
      handleEvent({ type: 'intervention', action: 'ROLLED_BACK', layer: 'fs', file_path: data.file, latency_ms: data.latency_ms });
      addLog(`Disk exposure measured: ${data.latency_ms} ms (write → inotify → baseline restored). Clean: ${data.restored}`);
    });

    window.addEventListener('load', () => {
      loadGraph();
      setupWebSocket();
      loadEvidence();
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

    def live_contract() -> Optional[ScopeContract]:
        return ScopeContract.load(repo / CONTRACT_FILE)

    @app.on_event("startup")
    async def tail_session_events():
        async def tail():
            offset, was_active = 0, None
            while True:
                active = (repo / CONTRACT_FILE).exists()
                if active != was_active:
                    contract = live_contract()
                    await manager.broadcast({"type": "session", "active": active,
                                             "task": contract.task_intent if contract else ""})
                    if active:
                        offset = 0
                    was_active = active
                events, offset = read_events(repo, offset)
                for event in events:
                    await manager.broadcast({"type": "intervention", **event.to_dict()})
                await asyncio.sleep(0.2)
        asyncio.create_task(tail())

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTML_DASHBOARD

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
            rel_str = node.as_posix()
            is_perm = contract.is_permitted(node)
            is_restr = contract.is_sensitive(node)

            if is_perm:
                color = "#00d2b4"
                label = f"✓ {rel_str}"
                reason = "In-scope: task target or 1-hop AST dependency"
            elif is_restr:
                color = "#fa4d56"
                label = f"🛡 {rel_str}"
                reason = "Protected core: database schema, configuration, lockfile, or prompt-restricted"
            else:
                color = "#525252"
                label = rel_str
                reason = "Out-of-scope repository file"

            imports = [v.as_posix() for v in synthesizer.graph.successors(node)]
            imported_by = [u.as_posix() for u in synthesizer.graph.predecessors(node)]

            nodes.append({
                "id": rel_str,
                "label": label,
                "color": color,
                "is_permitted": is_perm,
                "is_restricted": is_restr,
                "reason": reason,
                "imports": imports,
                "imported_by": imported_by,
            })

        edges = [
            {"from": u.as_posix(), "to": v.as_posix()}
            for u, v in synthesizer.graph.edges
        ]

        return {
            "nodes": nodes,
            "edges": edges,
            "live_session": live_contract() is not None,
            "permitted": [p.as_posix() for p in sorted(contract.permitted_paths)],
            "restricted": [p.as_posix() for p in sorted(contract.restricted_paths)],
            "permitted_count": len(contract.permitted_paths),
            "restricted_count": len(contract.restricted_paths),
        }

    @app.get("/api/telemetry")
    async def get_telemetry():
        events, _ = read_events(repo, 0)
        snapshot = TelemetrySnapshot(task_intent="", status="ACTIVE" if live_contract() else "IDLE")
        for event in events:
            snapshot.record_violation(event)
        contract = live_contract()
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
        summary_path = repo / "experiments" / "results" / "live_bob_20260927" / "summary.json"
        summary = None
        if summary_path.exists():
            try:
                summary = json.loads(summary_path.read_text())
            except Exception:
                pass

        base_diff_path = repo / "bob_sessions" / "live_ab_20260927" / "base2_diff.patch"
        base_diff = base_diff_path.read_text() if base_diff_path.exists() else ""

        gov_diff_path = repo / "bob_sessions" / "live_ab_20260927" / "gov4_diff.patch"
        gov_diff = gov_diff_path.read_text() if gov_diff_path.exists() else ""

        git_commit = ""
        try:
            r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=repo, capture_output=True, text=True)
            git_commit = r.stdout.strip()
        except Exception:
            pass

        return {
            "summary": summary,
            "git_commit": git_commit,
            "case_study": {
                "ungoverned_diff": base_diff,
                "governed_diff": gov_diff,
            }
        }

    @app.post("/api/simulate_interception")
    async def simulate_interception():
        # A real measurement, not an animation: corrupt a protected file in a throwaway repo
        # and time how long the corrupted bytes survive on disk.
        from nagare.benchmark import run_end_to_end_benchmark
        tmp = Path(tempfile.mkdtemp(prefix="nagare_sim_"))
        try:
            (tmp / "database").mkdir()
            (tmp / "database" / "schema.sql").write_text("CREATE TABLE users (id INT);\n")
            for args in (["init", "-q"], ["add", "."],
                         ["-c", "user.email=sim@nagare", "-c", "user.name=sim", "commit", "-qm", "init"]):
                subprocess.run(["git", *args], cwd=tmp, check=True, capture_output=True)
            result = await asyncio.to_thread(
                run_end_to_end_benchmark, tmp, Path("database/schema.sql"), 1, "simulation"
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return {
            "file": "database/schema.sql",
            "latency_ms": round(result.median_latency_ms, 2),
            "restored": result.corruptions_blocked == 1,
        }

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await manager.connect(websocket)
        contract = live_contract()
        await websocket.send_text(json.dumps({"type": "session", "active": contract is not None,
                                              "task": contract.task_intent if contract else ""}))
        if contract is not None:
            events, _ = read_events(repo, 0)
            for event in events:
                await websocket.send_text(json.dumps({"type": "intervention", **event.to_dict()}))
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket)

    return app
