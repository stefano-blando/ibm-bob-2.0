#!/usr/bin/env python3
"""Nagare Governor benchmark runner.

Measures, on throwaway git clones (never the working checkout):
- End-to-end exposure window: write hits disk -> inotify -> policy -> bytes restored
- Layer-1 prevention cost: Bob PreToolUse hook process latency
- Restore operation alone (synchronous micro-rollback)
Writes benchmarks/BENCHMARK_REPORT.md and benchmarks/benchmark_results.json.
"""

import json
from pathlib import Path
from rich.console import Console
from rich.table import Table
from nagare.benchmark import (
    scratch_clone, run_micro_rollback_benchmark, run_end_to_end_benchmark,
    run_hook_latency_benchmark, generate_benchmark_markdown_report,
)

SCENARIOS = [
    # (label, repo, protected file)
    ("Demo app · schema.sql", Path(__file__).resolve().parent.parent, Path("demo_app/database/schema.sql")),
    ("FastAPI RealWorld · alembic.ini", Path("/tmp/industrial_benchmark_repo"), Path("alembic.ini")),
    ("FastAPI RealWorld · core/config.py", Path("/tmp/industrial_benchmark_repo"), Path("app/core/config.py")),
    ("React/Redux RealWorld · src/store.js", Path("/tmp/ts_benchmark_repo"), Path("src/store.js")),
]


def main():
    console = Console()
    out_dir = Path(__file__).resolve().parent
    results = []

    for label, repo, target in SCENARIOS:
        if not (repo / ".git").exists():
            console.print(f"[dim]skip {label}: {repo} not cloned[/dim]")
            continue
        with scratch_clone(repo) as clone:
            console.print(f"[yellow]{label}[/yellow]")
            results.append(run_end_to_end_benchmark(clone, target, iterations=30, scenario_name=label))
            results.append(run_micro_rollback_benchmark(clone, target, iterations=50, scenario_name=label))
            if not any(r.kind == "hook" for r in results):
                results.append(run_hook_latency_benchmark(clone, target, iterations=20, scenario_name=label))

    table = Table(title="Nagare benchmark", expand=True)
    for col in ("Scenario", "Kind", "Runs", "Median", "P99", "Max", "OK"):
        table.add_column(col)
    for r in results:
        table.add_row(r.scenario_name, r.kind, str(r.iterations), f"{r.median_latency_ms:.2f} ms",
                      f"{r.p99_latency_ms:.2f} ms", f"{r.max_latency_ms:.2f} ms", f"{r.corruptions_blocked}/{r.iterations}")
    console.print(table)

    (out_dir / "benchmark_results.json").write_text(json.dumps([r.to_dict() for r in results], indent=2))
    report = generate_benchmark_markdown_report(results, out_dir / "BENCHMARK_REPORT.md")
    console.print(f"[green]Report:[/green] {report}")


if __name__ == "__main__":
    main()
