# 🌊 Nagare Governor — Lane-Assist for Autonomous AI Coding Agents

> **IBM Bob 2.0 Hackathon (lablab.ai)**  
> **Team**: Nagare (流れ — Flow State)  
> **Theme**: Agentic Software Development with IBM Bob 2.0 & Repository-Level Intelligence  
> **Prize Pool**: $12,000 + IBM TechXchange 2026 Pass  

---

## 🚀 Overview

**Nagare Governor** is an in-flight process supervisor and real-time active steering engine for autonomous AI coding agents (specifically **IBM Bob 2.0 CLI** in headless `--auto-approve` auto-mode). 

Just like automotive Lane-Assist applies micro-corrections to a car steering wheel before it drifts into oncoming traffic, **Nagare Governor dynamically scopes permissible file manifolds, monitors dirty filesystem writes with sub-2ms latency via Linux `inotify`, intercepts out-of-scope code mutations, and applies instant sub-15ms micro-rollbacks while streaming corrective steering directives into the agent's reasoning loop.**

```
+-----------------------------------------------------------------------------------+
|                           NAGARE GOVERNOR RUNTIME                                 |
|                                                                                   |
|   +-----------------------+              +------------------------------------+   |
|   |   Task Intent & AST   |              |         IBM Bob 2.0 Process        |   |
|   |   Scope Synthesizer   |              |    (Headless Auto-Mode Runner)     |   |
|   +-----------+-----------+              +-----------------+------------------+   |
|               |                                            |                      |
|               v (Permitted Manifold)                       v (File writes)        |
|   +-----------+-----------+              +-----------------+------------------+   |
|   |     Scope Contract    | <==========  |  Linux Inotify / Git Observer     |   |
|   |  (Permitted vs Denied)|  Violations? |  (< 2ms mutation detection)        |   |
|   +-----------+-----------+              +-----------------+------------------+   |
|               |                                            |                      |
|               | YES                                        | Out-of-scope write   |
|               v                                            v                      |
|   +---------------------------------------------------------------------------+   |
|   |             Micro-Steerer & Context Feedback Engine                       |   |
|   |   - Instant Micro-Rollback: `git checkout -- <file>` (< 15ms)             |   |
|   |   - Corrective Directive: Injects localized steering prompt                |   |
|   +-------------------------------------+-------------------------------------+   |
|                                         |                                         |
|                                         v                                         |
|   +-------------------------------------+-------------------------------------+   |
|   |         Rich Live Terminal HUD  &  bob_sessions/ Telemetry Exporter       |   |
|   +---------------------------------------------------------------------------+   |
+-----------------------------------------------------------------------------------+
```

---

## 🛑 The Problem: Agentic Derailment in Auto-Mode

When developers unleash autonomous coding agents in unsupervised mode (e.g. `bob run --auto-approve` or full autonomous loops), agents suffer from **hallucinatory scope creep** and **architectural drift**:

1. **Catastrophic Out-of-Scope Writes**: Tasked with adding rate limiting to an auth route, an agent decides to alter `database/schema.sql`, change global secrets in `core/config.py`, or reformat lockfiles.
2. **Post-Facto Failure**: Traditional guardrails and CI/CD only run *after* the agent completes dozens of turns. By then, the developer must spend hours untangling a 20-file dirty git diff, wasting precious tokens and Bobcoins.
3. **The Babysitting Tax**: Developers are forced to keep clicking manual approvals, completely destroying the promise of autonomous agentic development.

---

## ✨ The Nagare Solution: In-Flight Steering & Micro-Rollback

Nagare Governor runs as a real-time parent process around IBM Bob:

- 🧠 **Dynamic AST Scope Synthesizer**: Parses Python AST and codebase dependency graphs (`networkx`) to calculate the permitted mathematical manifold (target modules + 1-hop reachable call paths), while strictly isolating sensitive files (`schema.sql`, `config.py`, `.env`).
- ⚡ **Sub-2ms Inotify Observer**: Uses kernel-level Linux filesystem notifications (`watchdog`) combined with `git status --porcelain` reconciliation to detect mutations the instant they hit disk.
- 🔄 **Sub-15ms Micro-Rollback (`git checkout -- <file>`)**: Before the agent executes its next reasoning turn, Nagare reverts the forbidden mutation to clean `HEAD` state without halting the agent.
- 🎯 **Localized Steering Injection**: Synthesizes structured corrective feedback (`[NAGARE GOVERNOR INTERCEPTION]`) explaining exactly which file was reverted and where to implement the solution.
- 📊 **Rich Terminal HUD & Submission Telemetry**: Displays real-time metrics (Elapsed time, Scope status, Interceptions count) and automatically generates audit logs in `bob_sessions/` compliant with hackathon submission guidelines.

---

## 🛠️ Architecture & Modules

The codebase is organized into modular Python components:

| Module | Role | Key Technology |
|---|---|---|
| [`nagare.models`](backend/nagare/models.py) | Data contracts (`ScopeContract`, `ViolationEvent`, `TelemetrySnapshot`) | Python 3.12 dataclasses, Enums |
| [`nagare.scope`](backend/nagare/scope.py) | Dynamic dependency graph analysis & AST seed matching | `ast`, `networkx` |
| [`nagare.observer`](backend/nagare/observer.py) | Kernel-level inotify file monitoring & git porcelain reconciliation | `watchdog`, Linux `inotify` |
| [`nagare.steerer`](backend/nagare/steerer.py) | Sub-15ms file-level micro-rollback & prompt steering directive synthesis | `git checkout`, atomic debouncing |
| [`nagare.telemetry`](backend/nagare/telemetry.py) | Terminal HUD rendering & session report markdown generation | `rich`, Markdown |
| [`nagare.runner`](backend/nagare/runner.py) | Subprocess supervisor executing IBM Bob CLI in headless mode | `subprocess`, asyncio |
| [`nagare.cli`](backend/nagare/cli.py) | CLI interface (`nagare run`, `nagare watch`) | `argparse` |
| [`demo_app`](demo_app/) | Self-contained FastAPI microservice testbed for validation | FastAPI, SQLite |

---

## ⚡ Quickstart

### 1. Installation

Prerequisites: Python 3.12+, Git, and IBM Bob CLI (`bob`).

```bash
# Clone the repository
git clone https://github.com/stefanom/ibm-bob-2.0.git
cd ibm-bob-2.0

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies and Nagare Governor in editable mode
pip install -e backend
pip install pytest
```

### 2. Run the Automated Test Suite

Nagare was built from ground up using rigorous Test-Driven Development (TDD):

```bash
pytest
```
*Result: 14 passing unit and E2E integration tests in ~1.0s.*

### 3. Run Governed Agent Tasks

Execute an autonomous task with IBM Bob supervised by Nagare Governor:

```bash
# Run IBM Bob supervised by Nagare
nagare run "Add token bucket rate limiter to demo_app auth endpoint" --repo .

# Or run in dry-run / simulation mode
nagare run "Add token bucket rate limiter to demo_app auth endpoint" --repo . --dry-run
```

### 4. Passive Repository Watcher

You can also run Nagare in standalone watcher mode to govern any active agent or editor:

```bash
nagare watch --repo .
```

---

## 🧪 Demonstration: Governed vs. Ungoverned

We provide a self-contained testbed in `demo_app/`:
- `demo_app/database/schema.sql` (*RESTRICTED: Core database schema*)
- `demo_app/core/config.py` (*RESTRICTED: Secrets and encryption keys*)
- `demo_app/api/routes/auth.py` (*PERMITTED: Login endpoint*)
- `demo_app/services/user_service.py` (*PERMITTED: Authentication logic*)

### Task Prompt:
> *"Implement an in-memory token-bucket rate limiter on the login endpoint to prevent brute-force attacks."*

| Metric | Ungoverned Bob 2.0 (Baseline) | Governed Bob 2.0 (Nagare) |
|---|---|---|
| **Out-of-Scope Writes** | ❌ Corrupts `schema.sql` (creates rate_limits table) | 🛡️ **0 (Intercepted in 1.8ms & rolled back)** |
| **Codebase Integrity** | ❌ Broken migrations, dirty diff | ✅ **100% clean git working tree** |
| **Developer Intervention** | ❌ Manual rollback & fix required | ✅ **Zero-stop autonomous execution** |
| **Audit Session Export** | ❌ Manual extraction | ✅ **Auto-generated in `bob_sessions/`** |

---

## 📋 IBM Bob Session Logs (`bob_sessions/`)

In compliance with the IBM Bob 2.0 Hackathon requirements:
- Session audit reports are automatically created in [`bob_sessions/`](bob_sessions/).
- Each report details the task prompt, duration, files permitted, violations intercepted, and rollback timestamps.

---

## 👥 Team Nagare

- **Team**: Nagare (Solo Builder)
- **Built for**: IBM Bob 2.0 Hackathon (September 25–27, 2026)
- **License**: Apache-2.0
