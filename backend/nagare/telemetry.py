import datetime
from pathlib import Path
from typing import Optional
from rich.table import Table
from rich.panel import Panel
from rich.console import Console
from nagare.models import TelemetrySnapshot, ScopeContract

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
        table.add_row("Policy / Layers", f"{snapshot.policy} · {'Bob hooks + inotify' if snapshot.hooks_enabled else 'inotify only'}")
        table.add_row("Elapsed Time", f"{snapshot.elapsed_seconds:.1f}s")
        table.add_row(
            "Files Modified (in lane)",
            ", ".join(str(p) for p in sorted(snapshot.files_modified)) or "[dim]None yet[/dim]"
        )
        table.add_row(
            "Prevented (hook / MCP)",
            f"[bold red]{snapshot.total_denied}[/bold red]" if snapshot.total_denied else "[green]0[/green]"
        )
        table.add_row(
            "Repaired (layer 2)",
            f"[bold red]{snapshot.total_rollbacks} rolled back · {snapshot.total_quarantined} quarantined[/bold red]"
            if (snapshot.total_rollbacks or snapshot.total_quarantined) else "[green]0[/green]"
        )
        table.add_row("Developer files protected", f"{snapshot.preserved_user_files} pre-existing changes untouched")
        if snapshot.violations:
            last = snapshot.violations[-1]
            table.add_row("Last intervention", f"{last.action.value} {last.file_path} (x{last.repeat_count})")

        return Panel(
            table,
            title="[bold magenta]🌊 Team Nagare — IBM Bob 2.0 Governor[/bold magenta]",
            subtitle="[dim]Lane-Assist for Autonomous AI Coding Agents[/dim]"
        )

    def export_session_report(self, snapshot: TelemetrySnapshot, contract: Optional[ScopeContract] = None) -> Path:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"nagare_session_{timestamp_str}.md"
        out_path = self.sessions_dir / filename

        def fmt(v) -> str:
            repeat = f" ×{v.repeat_count}" if v.repeat_count > 1 else ""
            layer = {"hook": "Bob hook (before write)", "mcp": "MCP advisory (before write)"}.get(v.layer, "filesystem (after write)")
            return f"- **{v.action.value}**{repeat} `{v.file_path}` via {layer} at `{v.timestamp:.1f}` — *{v.steering_prompt.splitlines()[0]}*"

        violations_md = "\n".join(fmt(v) for v in snapshot.violations) or \
            "*Zero violations detected. Execution stayed 100% within permitted scope.*"
        modified_md = "\n".join(f"- `{p}`" for p in sorted(snapshot.files_modified)) or "*None*"
        cost = f"{snapshot.bobcoins_cost:.2f}" if snapshot.bobcoins_cost is not None else "n/a (not reported by agent stream)"

        contract_md = ""
        if contract is not None:
            permitted = "\n".join(f"- `{p.as_posix()}`" for p in sorted(contract.permitted_paths)) or "*None*"
            protected = "\n".join(f"- `{p.as_posix()}`" for p in sorted(contract.restricted_paths)) or "*None*"
            contract_md = f"""
## Scope Contract ({contract.policy.value})
**Permitted**
{permitted}

**Protected**
{protected}
"""

        report = f"""# Nagare Governor Session Report (IBM Bob 2.0)

- **Date**: {datetime.datetime.now().isoformat()}
- **Task Intent**: {snapshot.task_intent}
- **Status**: {snapshot.status}
- **Elapsed Duration**: {snapshot.elapsed_seconds:.2f} seconds
- **Enforcement layers**: {'Bob native hooks (prevent) + inotify/git (repair)' if snapshot.hooks_enabled else 'inotify/git (repair)'}
- **Agent cost**: {cost}

## Summary
| Prevented before write | Rolled back | Quarantined | Warned | Pre-existing developer changes preserved |
|---|---|---|---|---|
| {snapshot.total_denied} | {snapshot.total_rollbacks} | {snapshot.total_quarantined} | {snapshot.total_warned} | {snapshot.preserved_user_files} |
{contract_md}
## Files Modified In Lane
{modified_md}

## Interventions
{violations_md}
"""
        out_path.write_text(report, encoding="utf-8")
        return out_path
