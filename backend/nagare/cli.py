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
        choices=["run", "watch", "ui", "mcp", "benchmark", "hook", "install-hooks", "uninstall-hooks", "scope", "status"],
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
        from rich.console import Console
        from rich.tree import Tree
        from rich.panel import Panel
        from rich.table import Table
        from nagare.scope import ScopeSynthesizer

        console = Console()
        synth = ScopeSynthesizer(repo_path)
        contract = synth.synthesize_scope(args.prompt or "Current Task", policy=policy)

        tree = Tree(f"[bold cyan]📁 {repo_path.name}[/bold cyan] [dim](AST Import Manifold & Write Contract)[/dim]")
        lane = tree.add(f"[bold green]✓ Permitted Lane ({len(contract.permitted_paths)} files)[/bold green] [dim]-- Target & 1-Hop AST Imports[/dim]")
        for p in sorted(contract.permitted_paths):
            node = lane.add(f"[green]✓ {p.as_posix()}[/green]")
            if p in synth.graph:
                deps = [d.as_posix() for d in synth.graph.successors(p) if d != p]
                for d in deps[:4]:
                    node.add(f"[dim green]↳ imports [cyan]{d}[/cyan][/dim green]")

        shield = tree.add(f"[bold red]🛡 Protected Core ({len(contract.restricted_paths)} files)[/bold red] [dim]-- Blocked at Hook Boundary & Restored at FS[/dim]")
        for p in sorted(contract.restricted_paths):
            reason = "database schema" if p.suffix == ".sql" or "schema" in p.name else ("config / secret" if "config" in p.name or "env" in p.name else "protected asset")
            shield.add(f"[red]✕ {p.as_posix()}[/red] [dim yellow]({reason})[/dim yellow]")

        summary = Table.grid(padding=(0, 2))
        summary.add_column("Key", style="bold white")
        summary.add_column("Val", style="cyan")
        summary.add_row("Task Intent:", f"[yellow]{args.prompt or 'Current Task'}[/yellow]")
        summary.add_row("Policy:", f"[bold]{policy.value}[/bold]")
        summary.add_row("Dual Boundary:", "Layer 1: PreToolUse Hooks (deny) · Layer 2: inotify (revert)")

        console.print()
        console.print(Panel(summary, title="🌊 [bold]Nagare Write Contract[/bold]", border_style="cyan"))
        console.print(Panel(tree, border_style="dim", subtitle=f"[dim]{len(contract.permitted_paths)} permitted · {len(contract.restricted_paths)} protected[/dim]"))
        console.print()

    elif args.command == "status":
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        import subprocess
        from nagare.paths import CONTRACT_FILE

        console = Console()
        table = Table(title="🌊 Nagare Git Safety & Governance Ledger", border_style="blue", show_header=True)
        table.add_column("System / Component", style="bold white")
        table.add_column("Status / Safety Guarantee", style="cyan")

        try:
            head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=repo_path, capture_output=True, text=True).stdout.strip()
            branch = subprocess.run(["git", "branch", "--show-current"], cwd=repo_path, capture_output=True, text=True).stdout.strip()
            table.add_row("Git Repository", f"[green]{branch}[/green] @ [bold yellow]{head}[/bold yellow]")
        except Exception:
            table.add_row("Git Repository", "[dim]Unknown[/dim]")

        try:
            res = subprocess.run(["git", "status", "--porcelain=v1"], cwd=repo_path, capture_output=True, text=True)
            dirty_lines = [l for l in res.stdout.strip().splitlines() if l and not l.startswith("?? .nagare")]
            if len(dirty_lines) == 0:
                table.add_row("Working Tree", "[green]Clean (Session baseline ready)[/green]")
            else:
                table.add_row("Working Tree", f"[yellow]{len(dirty_lines)} dirty files (Session Baseline protected)[/yellow]")
        except Exception:
            pass

        contract_file = repo_path / CONTRACT_FILE
        if contract_file.exists():
            table.add_row("Active Contract", f"[bold green]ACTIVE[/bold green] ({contract_file.name})")
        else:
            table.add_row("Active Contract", "[dim]Idle (No active agent session)[/dim]")

        settings_file = repo_path / ".bob" / "settings.json"
        if settings_file.exists() and "nagare hook" in settings_file.read_text():
            table.add_row("IBM Bob Hooks", "[bold green]INSTALLED[/bold green] (.bob/settings.json)")
        else:
            table.add_row("IBM Bob Hooks", "[dim]Managed automatically per session[/dim]")

        quarantine = repo_path / ".nagare" / "quarantine"
        q_files = [f for f in quarantine.rglob("*") if f.is_file()] if quarantine.exists() else []
        table.add_row("Quarantine Ledger", f"[yellow]{len(q_files)} rogue files isolated[/yellow] (.nagare/quarantine/)")

        console.print()
        console.print(table)
        console.print()
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
