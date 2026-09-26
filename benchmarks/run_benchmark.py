#!/usr/bin/env python3
"""Nagare Governor Empirical Benchmark Runner

Runs automated multi-scenario stress tests measuring:
- Micro-rollback latency (mean, median, p99)
- Corruptions intercepted vs allowed (100% safety rate)
- Generates benchmarks/BENCHMARK_REPORT.md
"""

from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from nagare.benchmark import run_micro_rollback_benchmark, generate_benchmark_markdown_report

def main():
    console = Console()
    repo_root = Path(__file__).resolve().parent.parent
    industrial_repo = Path("/tmp/industrial_benchmark_repo")
    out_report = repo_root / "benchmarks" / "BENCHMARK_REPORT.md"

    console.print(Panel(
        "[bold cyan]🌊 Nagare Governor — Empirical Benchmark Suite[/bold cyan]\n"
        "[dim]Measuring sub-15ms micro-rollback invariant & scope safety on enterprise codebases[/dim]",
        border_style="magenta"
    ))

    results = []

    # Scenario 1: demo_app schema.sql
    console.print("[yellow]Running Scenario 1:[/yellow] Demo App SQL Schema Guard (50 iterations)...")
    res1 = run_micro_rollback_benchmark(
        repo_root=repo_root,
        target_file=Path("demo_app/database/schema.sql"),
        iterations=50,
        scenario_name="Demo App (SQL Schema Mutation)"
    )
    results.append(res1)
    console.print(f"  [green]✓[/green] Avg Latency: [bold]{res1.avg_latency_ms:.2f} ms[/bold] (P99: {res1.p99_latency_ms:.2f} ms) — Blocked: {res1.corruptions_blocked}/50")

    # Scenario 2: Industrial Repo Migration
    if industrial_repo.exists():
        console.print("[yellow]Running Scenario 2:[/yellow] Industrial FastAPI RealWorld (alembic.ini Guard) (50 iterations)...")
        res2 = run_micro_rollback_benchmark(
            repo_root=industrial_repo,
            target_file=Path("alembic.ini"),
            iterations=50,
            scenario_name="Industrial 80+ Files (Alembic Guard)"
        )
        results.append(res2)
        console.print(f"  [green]✓[/green] Avg Latency: [bold]{res2.avg_latency_ms:.2f} ms[/bold] (P99: {res2.p99_latency_ms:.2f} ms) — Blocked: {res2.corruptions_blocked}/50")

        # Scenario 3: Industrial Repo Core Config
        console.print("[yellow]Running Scenario 3:[/yellow] Industrial FastAPI RealWorld (app/core/config.py Guard) (50 iterations)...")
        res3 = run_micro_rollback_benchmark(
            repo_root=industrial_repo,
            target_file=Path("app/core/config.py"),
            iterations=50,
            scenario_name="Industrial 80+ Files (Secrets/Config Guard)"
        )
        results.append(res3)
        console.print(f"  [green]✓[/green] Avg Latency: [bold]{res3.avg_latency_ms:.2f} ms[/bold] (P99: {res3.p99_latency_ms:.2f} ms) — Blocked: {res3.corruptions_blocked}/50")

    ts_repo = Path("/tmp/ts_benchmark_repo")
    if ts_repo.exists():
        console.print("[yellow]Running Scenario 4:[/yellow] Industrial React/Redux Full-Stack (src/store.js Guard) (50 iterations)...")
        res4 = run_micro_rollback_benchmark(
            repo_root=ts_repo,
            target_file=Path("src/store.js"),
            iterations=50,
            scenario_name="Industrial React/Redux (Central Store Guard)"
        )
        results.append(res4)
        console.print(f"  [green]✓[/green] Avg Latency: [bold]{res4.avg_latency_ms:.2f} ms[/bold] (P99: {res4.p99_latency_ms:.2f} ms) — Blocked: {res4.corruptions_blocked}/50")

    # Render summary table
    table = Table(title="[bold green]Empirical Benchmark Results Summary[/bold green]", expand=True)
    table.add_column("Scenario", style="cyan")
    table.add_column("Runs", justify="right")
    table.add_column("Avg Latency", justify="right", style="bold green")
    table.add_column("Median Latency", justify="right")
    table.add_column("P99 Latency", justify="right", style="bold yellow")
    table.add_column("Blocked", justify="right", style="bold magenta")
    table.add_column("Safety Rate", justify="right", style="bold green")

    for r in results:
        table.add_row(
            r.scenario_name,
            str(r.iterations),
            f"{r.avg_latency_ms:.2f} ms",
            f"{r.median_latency_ms:.2f} ms",
            f"{r.p99_latency_ms:.2f} ms",
            f"{r.corruptions_blocked}/{r.iterations}",
            f"{r.success_rate_percent:.1f}%"
        )

    console.print()
    console.print(table)

    # Export report
    report_file = generate_benchmark_markdown_report(results, out_report)
    console.print(f"\n[green]✓ Benchmark report generated at:[/green] {report_file}")

if __name__ == "__main__":
    main()
