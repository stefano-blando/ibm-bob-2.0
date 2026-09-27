import sys
import argparse
from pathlib import Path
from nagare.models import Policy
from nagare.runner import NagareRunner

IDLE_AGENT = [sys.executable, "-c", "import time\nwhile True: time.sleep(3600)"]

def main():
    parser = argparse.ArgumentParser(
        prog="nagare",
        description="Nagare Governor: Lane-Assist for Autonomous AI Coding Agents"
    )
    parser.add_argument(
        "command",
        choices=["run", "watch", "ui", "mcp", "benchmark", "hook", "install-hooks", "uninstall-hooks", "scope"],
        help="Command to execute",
    )
    parser.add_argument("prompt", nargs="?", default="", help="Task prompt for the agent")
    parser.add_argument("--repo", default=".", help="Path to repository root (default: current directory)")
    parser.add_argument("--dry-run", action="store_true", help="Govern the current working tree once without launching the agent")
    parser.add_argument("--policy", choices=["guard", "lane", "strict", "balanced"], default="guard",
                        help="guard (default): block protected files, report drift outside the task scope; lane: also revert out-of-scope code; strict: revert everything outside scope")
    parser.add_argument("--no-hooks", action="store_true", help="Disable Bob native hooks (filesystem layer only)")
    parser.add_argument("--max-turns", type=int, default=None, help="Forwarded to `bob run --max-turns`")
    parser.add_argument("--max-cost", type=float, default=None, help="Forwarded to `bob run --max-cost`")
    parser.add_argument("--disable-mcp", action="store_true", help="Forwarded to `bob run --disable-mcp` (A/B runs without the MCP advisor)")
    parser.add_argument("--agent-cmd", default=None,
                        help="Govern another agent instead of Bob, e.g. \"claude -p {prompt}\" ({prompt} is substituted; filesystem layer only)")
    parser.add_argument("--no-briefing", action="store_true", help="Ablation: skip the SessionStart scope briefing (hooks still deny)")
    parser.add_argument("--port", type=int, default=8765, help="Port for the web UI (default: 8765)")
    parser.add_argument("--host", default="127.0.0.1", help="Host for the web UI (default: 127.0.0.1)")

    args = parser.parse_args()
    repo_path = Path(args.repo).resolve()

    if args.command == "hook":
        # Invoked by Bob with the event JSON on stdin; never fails closed.
        from nagare.hooks import run_hook
        code, out = run_hook(sys.stdin.read(), repo_path)
        if out:
            sys.stdout.write(out)
        sys.exit(code)

    if not (repo_path / ".git").exists():
        print(f"Error: {repo_path} is not a valid Git repository.", file=sys.stderr)
        sys.exit(1)

    policy = Policy.parse(args.policy)

    if args.command == "run":
        if not args.prompt:
            print("Error: Task prompt is required for 'run' command.", file=sys.stderr)
            sys.exit(1)
        agent_cmd = None
        if args.agent_cmd:
            import shlex
            agent_cmd = [tok.replace("{prompt}", args.prompt) for tok in shlex.split(args.agent_cmd)]
        runner = NagareRunner(
            repo_root=repo_path, dry_run=args.dry_run, agent_cmd=agent_cmd, policy=policy, use_hooks=not args.no_hooks,
            max_turns=args.max_turns, max_cost=args.max_cost,
            extra_bob_args=["--disable-mcp"] if args.disable_mcp else None,
            briefing=not args.no_briefing,
        )
        snapshot = runner.run_governed(task_prompt=args.prompt)
        print(f"\n[Nagare] Execution finished with status: {snapshot.status}")
        print(f"[Nagare] Prevented before write (hook/MCP): {snapshot.total_denied} | rolled back: {snapshot.total_rollbacks} "
              f"| quarantined: {snapshot.total_quarantined} | warned: {snapshot.total_warned}")
    elif args.command == "watch":
        print(f"[Nagare] Governing {repo_path} (Ctrl-C to stop)...")
        runner = NagareRunner(repo_root=repo_path, agent_cmd=IDLE_AGENT, policy=policy)
        snapshot = runner.run_governed(task_prompt=args.prompt or "Passive repo monitoring")
        print(f"[Nagare] Monitoring stopped. Interventions: {snapshot.total_interventions}")
    elif args.command == "scope":
        from nagare.scope import ScopeSynthesizer
        contract = ScopeSynthesizer(repo_path).synthesize_scope(args.prompt or "Current Task", policy=policy)
        print("Permitted:")
        for p in sorted(contract.permitted_paths):
            print(f"  ✓ {p.as_posix()}")
        print("Protected:")
        for p in sorted(contract.restricted_paths):
            print(f"  ✕ {p.as_posix()}")
    elif args.command == "install-hooks":
        from nagare.hooks import install_hooks
        print(f"[Nagare] Hooks installed in {install_hooks(repo_path)}")
    elif args.command == "uninstall-hooks":
        from nagare.hooks import uninstall_hooks
        uninstall_hooks(repo_path)
        print("[Nagare] Hooks removed; .bob/settings.json restored.")
    elif args.command == "ui":
        import uvicorn
        from nagare.server import create_app
        print(f"\n🌊 Launching Nagare Flight Recorder Web UI at http://{args.host}:{args.port}...")
        app = create_app(repo_root=repo_path)
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    elif args.command == "mcp":
        from nagare.mcp_server import NagareMCPServer
        server = NagareMCPServer(repo_root=repo_path)
        server.run_stdio()
    elif args.command == "benchmark":
        from nagare.benchmark import run_micro_rollback_benchmark
        print(f"\n🌊 Running Nagare Micro-Rollback Benchmark on {repo_path} (50 iterations)...")
        res = run_micro_rollback_benchmark(repo_root=repo_path, iterations=50)
        print(f"  Avg Latency:    {res.avg_latency_ms:.2f} ms")
        print(f"  Median Latency: {res.median_latency_ms:.2f} ms")
        print(f"  P99 Latency:    {res.p99_latency_ms:.2f} ms")
        print(f"  Safety Rate:    {res.success_rate_percent:.1f}% ({res.corruptions_blocked}/{res.iterations})")

if __name__ == "__main__":
    main()
