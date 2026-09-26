import datetime
from pathlib import Path
from rich.table import Table
from rich.panel import Panel
from rich.console import Console
from nagare.models import TelemetrySnapshot

class NagareTelemetry:
    def __init__(self, sessions_dir: Path):
        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.console = Console()

    def render_hud(self, snapshot: TelemetrySnapshot) -> Panel:
        table = Table(show_header=True, header_style="bold cyan", expand=True)
        table.add_column("Metric", style="dim")
        table.add_column("Value")

        table.add_row("Task Intent", snapshot.task_intent)
        table.add_row(
            "Governor Status",
            f"[bold green]{snapshot.status}[/bold green]" if snapshot.status == "COMPLETED" else f"[bold yellow]{snapshot.status}[/bold yellow]"
        )
        table.add_row("Elapsed Time", f"{snapshot.elapsed_seconds:.1f}s")
        table.add_row(
            "Files Modified",
            ", ".join(str(p) for p in sorted(snapshot.files_modified)) or "[dim]None yet[/dim]"
        )
        table.add_row(
            "Interceptions",
            f"[bold red]{len(snapshot.violations)}[/bold red]" if snapshot.violations else "[green]0 (Clean)[/green]"
        )
        table.add_row("Est. Bobcoins", f"{snapshot.bobcoins_cost:.2f}")

        return Panel(
            table,
            title="[bold magenta]🌊 Team Nagare — IBM Bob 2.0 Governor[/bold magenta]",
            subtitle="[dim]Lane-Assist for Autonomous AI Coding Agents[/dim]"
        )

    def export_session_report(self, snapshot: TelemetrySnapshot) -> Path:
        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"nagare_session_{timestamp_str}.md"
        out_path = self.sessions_dir / filename

        violations_md = "\n".join(
            f"- **{v.action.value}**: `{v.file_path}` at `{v.timestamp:.1f}` — *{v.steering_prompt}*"
            for v in snapshot.violations
        ) or "*Zero violations detected. Execution stayed 100% within permitted scope.*"

        modified_md = "\n".join(f"- `{p}`" for p in sorted(snapshot.files_modified)) or "*None*"

        report = f"""# Nagare Governor Session Report (IBM Bob 2.0)

- **Date**: {datetime.datetime.now().isoformat()}
- **Task Intent**: {snapshot.task_intent}
- **Status**: {snapshot.status}
- **Elapsed Duration**: {snapshot.elapsed_seconds:.2f} seconds
- **Bobcoins Consumed**: {snapshot.bobcoins_cost:.2f}

## Permitted & Modified Files
{modified_md}

## Interceptions & Micro-Rollbacks
{violations_md}

## Verification Certificate
This session was autonomously governed by Nagare Lane-Assist. Out-of-scope regressions were intercepted and rolled back in real time.
"""
        out_path.write_text(report, encoding="utf-8")
        return out_path
