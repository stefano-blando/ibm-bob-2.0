#!/usr/bin/env python3
"""Export IBM Bob Shell task history (~/.bob/db/bob.db, opened read-only) to Markdown.

Headless `bob run` sessions do not appear in the Bob IDE's History panel, and
`bob --list-tasks` fails in Bob Shell 2.0.5 ("--prompt non valido"), so this reads the
same local task store Bob Shell writes. Output: bob_sessions/bob_shell_tasks/INDEX.md plus
one file per task. The system prompt is omitted, long tool payloads are truncated, and
local paths are redacted.

Usage: python scripts/export_bob_tasks.py [--db ~/.bob/db/bob.db] [--out bob_sessions/bob_shell_tasks]
"""

import argparse
import datetime as dt
import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRUNCATE = 1500
REDACTIONS = [
    (re.compile(r"/tmp/claude-\d+/[^\s\"'`)]*?/scratchpad(/exp)?"), "/tmp/nagare-work"),
    (re.compile(r"/home/[A-Za-z0-9_.-]+/"), "~/"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}"), "<email>"),
]


def redact(text: str) -> str:
    for pattern, repl in REDACTIONS:
        text = pattern.sub(repl, text)
    return text


def clip(text: str, limit: int = TRUNCATE) -> str:
    text = redact(text)
    return text if len(text) <= limit else text[:limit] + f"\n… [truncated, {len(text) - limit} more characters]"


def utc(ms: int) -> str:
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def fence(text: str) -> str:
    return "````text\n" + text.replace("````", "``​``") + "\n````"


def export(db: Path, out: Path) -> None:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    out.mkdir(parents=True, exist_ok=True)
    tasks = con.execute("select id, title, status, costs, env, created_at, updated_at from tasks order by created_at").fetchall()
    index, total = [], 0.0
    for n, (tid, title, status, costs, env, created, updated) in enumerate(tasks, 1):
        cost = json.loads(costs) if costs else {}
        envd = json.loads(env) if env else {}
        total += cost.get("cost", 0.0)
        name = f"{n:02d}_{tid[:8]}.md"
        msgs = con.execute("select role, data from messages where task_id=? order by created_at", (tid,)).fetchall()
        lines = [
            f"# Bob task {n:02d} · {redact((title or '').strip())[:120]}",
            "",
            "| Field | Value |", "|---|---|",
            f"| Task id | `{tid}` |",
            f"| Created | {utc(created)} |",
            f"| Updated | {utc(updated)} |",
            f"| Status (Bob Shell) | {status} |",
            f"| Bobcoins | {cost.get('cost', 0):.6f} |",
            f"| Context tokens | {cost.get('contextTokens', '')} |",
            f"| Model | {(envd.get('model') or {}).get('id', '')} |",
            f"| Mode | {envd.get('modeId', '')} |",
            f"| Workspace | `{redact(envd.get('workspace', ''))}` |",
            f"| Messages | {len(msgs)} |",
            "",
        ]
        for role, data in msgs:
            d = json.loads(data)
            content = d.get("content") or ""
            if isinstance(content, list):
                content = "\n".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
            if role == "system":
                lines += [f"*System prompt omitted ({len(content)} characters).*", ""]
            elif role == "user":
                lines += ["## User", "", fence(clip(content, 6000)), ""]
            elif role == "assistant":
                spend = (d.get("_meta") or {}).get("spend") or {}
                lines += [f"### Bob · {spend.get('cost', 0):.4f} Bobcoins"]
                if content.strip():
                    lines += ["", clip(content, 4000)]
                for call in d.get("toolCalls") or []:
                    lines += ["", f"**Tool call `{call.get('name')}`**", "", fence(clip(json.dumps(call.get("arguments"), indent=1, ensure_ascii=False)))]
                lines += [""]
            elif role == "tool":
                usage = d.get("toolUsage") or {}
                sig = usage.get("signature") or {}
                err = " (error)" if sig.get("isError") else ""
                lines += [f"**Tool result `{sig.get('name', '')}`{err}**", "", fence(clip(str(content))), ""]
        (out / name).write_text("\n".join(lines), encoding="utf-8")
        index.append(f"| {n:02d} | {utc(created)[:16]} | [{redact((title or '').strip())[:70].replace('|', '/')}]({name}) | {status} | {cost.get('cost', 0):.4f} |")

    done = sum(1 for t in tasks if t[2] != "error")
    head = [
        "# IBM Bob Shell task history",
        "",
        f"Exported from Bob Shell's local task store (`~/.bob/db/bob.db`, read-only) with "
        f"`scripts/export_bob_tasks.py`. {len(tasks)} tasks, **{total:.2f} Bobcoins** in total "
        f"(the Bobalytics dashboard for the same account shows 28.78 Bobcoins; see `../bobalytics/`).",
        "",
        f"Status as recorded by Bob Shell: {done} completed, {len(tasks) - done} `error`; the {done} matches "
        f"Bobalytics' \"Tasks completed\" for the same period. The Bob Shell status is not the evaluation outcome: each run's tests and scope "
        "are judged separately in `../../experiments/results/`.",
        "",
        "Per task: prompt, Bob's messages and tool calls, tool results (truncated to 1,500 characters), "
        "per-step Bobcoins. System prompt omitted; local paths and e-mail addresses redacted.",
        "",
        "| # | Created (UTC) | Task | Status | Bobcoins |", "|---|---|---|---|---:|",
    ]
    (out / "INDEX.md").write_text("\n".join(head + index) + "\n", encoding="utf-8")
    print(f"exported {len(tasks)} tasks, {total:.2f} Bobcoins -> {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=Path.home() / ".bob" / "db" / "bob.db")
    ap.add_argument("--out", type=Path, default=ROOT / "bob_sessions" / "bob_shell_tasks")
    a = ap.parse_args()
    export(a.db.expanduser(), a.out)
