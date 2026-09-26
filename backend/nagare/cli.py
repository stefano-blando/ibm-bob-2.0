import sys
import argparse
from pathlib import Path
from nagare.runner import NagareRunner

def main():
    parser = argparse.ArgumentParser(
        prog="nagare",
        description="Nagare Governor: Lane-Assist for Autonomous AI Coding Agents"
    )
    parser.add_argument("command", choices=["run", "watch", "ui"], help="Command to execute")
    parser.add_argument("prompt", nargs="?", default="", help="Task prompt for the agent")
    parser.add_argument("--repo", default=".", help="Path to repository root (default: current directory)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without launching the agent process")
    parser.add_argument("--port", type=int, default=8765, help="Port for the web UI (default: 8765)")
    parser.add_argument("--host", default="127.0.0.1", help="Host for the web UI (default: 127.0.0.1)")

    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    if not (repo_path / ".git").exists():
        print(f"Error: {repo_path} is not a valid Git repository.", file=sys.stderr)
        sys.exit(1)

    runner = NagareRunner(repo_root=repo_path, dry_run=args.dry_run)

    if args.command == "run":
        if not args.prompt:
            print("Error: Task prompt is required for 'run' command.", file=sys.stderr)
            sys.exit(1)
        snapshot = runner.run_governed(task_prompt=args.prompt)
        print(f"\n[Nagare] Execution finished with status: {snapshot.status}")
        print(f"[Nagare] Violations intercepted and rolled back: {len(snapshot.violations)}")
    elif args.command == "watch":
        print(f"[Nagare] Starting passive monitor on {repo_path}...")
        snapshot = runner.run_governed(task_prompt=args.prompt or "Passive repo monitoring")
        print(f"[Nagare] Monitoring stopped.")
    elif args.command == "ui":
        import uvicorn
        from nagare.server import create_app
        print(f"\n🌊 Launching Nagare Flight Recorder Web UI at http://{args.host}:{args.port}...")
        app = create_app(repo_root=repo_path)
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")

if __name__ == "__main__":
    main()
