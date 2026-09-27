# 🌐 Nagare Governor — Universal Multi-Agent Ecosystem Guide

> **One Lane-Assist Engine for Every AI Coding Agent.**  
> Built for IBM Bob 2.0 and fully compatible with the Model Context Protocol (MCP) standard.

---

## 🧭 The Vision: Universal Autonomous Guardrails

Nagare's deepest integration is with **IBM Bob 2.0** (native SessionStart/PreToolUse/PostToolUse hooks + MCP). Its filesystem layer—**inotify monitoring, session-baseline restore, and task-derived scope contracts**—is agent-agnostic, so any agent can be governed at the filesystem level.

By adhering to the open **Model Context Protocol (MCP)** standard and providing a flexible CLI wrapper, Nagare can govern **any AI coding agent** on the market today.

```
                         +-----------------------------------+
                         |         NAGARE GOVERNOR           |
                         |   - Bob hooks (deny pre-write)    |
                         |   - inotify restore (~9ms median) |
                         |   - Task-scoped write contract    |
                         +-----------------+-----------------+
                                           |
         +------------------+--------------+---------------+------------------+
         |                  |                              |                  |
         v                  v                              v                  v
+------------------+ +--------------------+ +--------------------+ +--------------------+
|   IBM Bob 2.0    | |    Claude Code     | |   Cursor / Windsurf| |  OpenAI Codex /    |
| (CLI & bob mcp)  | | (Anthropic CLI)    | | (IDE Agent Mode)   | |  Hermes / Goose    |
+------------------+ +--------------------+ +--------------------+ +--------------------+
```

---

## 🔌 1. IBM Bob 2.0 Integration

### Native CLI Supervision
Run Bob in unsupervised auto-mode supervised by Nagare's real-time HUD:
```bash
nagare run "Implement feature in auth.py" --repo .
```

### Global Model Context Protocol (MCP)
Register Nagare as a persistent MCP boundary checker across all workspaces:
```bash
bob mcp add -s global nagare /path/to/.venv/bin/python3 -- /path/to/backend/nagare/mcp_server.py
```
Tools exposed to Bob:
- `nagare_get_scope`: Proactively inspects active permitted and restricted file manifolds.
- `nagare_check_permission(file_path)`: Verifies if a file is safe to modify before attempting writes.

---

## 🟣 2. Anthropic Claude Code Integration

Claude Code natively supports the Model Context Protocol:

### Add Nagare MCP Server to Claude Code
```bash
claude mcp add nagare python3 -m nagare.mcp_server
```

### Supervised Execution
Run Claude Code with Nagare's supervisor wrapping the process:
```bash
nagare run "Refactor payment service" --agent-cmd "claude -p {prompt} --dangerously-skip-permissions"
```
Even with `--dangerously-skip-permissions` enabled, Nagare's filesystem layer restores out-of-scope writes to the session baseline (≈9 ms median in our benchmark). For non-Bob agents only the filesystem layer and MCP apply; the pre-write hook layer is Bob-specific.

---

## ⚡ 3. Cursor & Windsurf IDE Integration

For IDE-based autonomous agent modes, configure the MCP server in your local settings:

### Configuration File (`~/.cursor/mcp.json` or `.codeium/windsurf/mcp_config.json`)
```json
{
  "mcpServers": {
    "nagare-governor": {
      "command": "python3",
      "args": ["-m", "nagare.mcp_server"],
      "env": {
        "PYTHONPATH": "/path/to/nagare/backend"
      }
    }
  }
}
```

---

## 🪿 4. Goose, Hermes & Open-Source Agent Frameworks

For open-source agents (Goose, Hermes Agent, SWE-agent):

### Goose CLI Configuration
```yaml
# ~/.config/goose/config.yaml
extensions:
  nagare:
    enabled: true
    type: stdio
    cmd: python3
    args: ["-m", "nagare.mcp_server"]
```

---

## 📋 MCP Tools Reference

Nagare exposes two standardized MCP tools adhering to the `2024-11-05` JSON-RPC specification:

### 1. `nagare_get_scope`
- **Description**: Returns the scope contract the governor is currently enforcing, including all permitted files (1-hop AST reachable) and strictly protected infrastructure files.
- **Parameters**: `intent` (optional string).
- **Example Response**:
  ```text
  === NAGARE GOVERNOR SCOPE CONTRACT ===
  Permitted Files (2):
    ✓ demo_app/api/routes/auth.py
    ✓ demo_app/services/user_service.py

  Restricted Files (3):
    ✕ demo_app/database/schema.sql
    ✕ demo_app/core/config.py
    ✕ .env*
  ```

### 2. `nagare_check_permission`
- **Description**: Verifies whether a specific file can be modified under active policy.
- **Parameters**: `file_path` (required string).
- **Responses**:
  - `✅ PERMISSION GRANTED`: Safe to modify within the current task manifold.
  - `⛔ PERMISSION DENIED`: Modification strictly prohibited. Writes will be blocked (Bob hook) or reverted (filesystem layer).

---

## 🚀 Post-Hackathon Open Source Roadmap

1. **PyPI Distribution**:
   ```bash
   pip install nagare-governor
   ```
2. **VS Code & JetBrains Extensions**:
   - Visual Lane-Assist HUD in the status bar.
   - Interactive visual graph view inside the IDE side panel.
3. **eBPF-Level Process Isolation**:
   - Extend beyond filesystem `inotify` to kernel-level socket and syscall interception using eBPF, preventing unauthorized outbound network calls or raw database drops.
4. **Multi-Repository Monorepo Support**:
   - Advanced scoping across Turborepo, Nx, and Cargo workspaces with cross-package boundary enforcement.
