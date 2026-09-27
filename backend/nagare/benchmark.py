import json
import sys
import time
import shutil
import tempfile
import threading
import statistics
import datetime
import platform
import subprocess
from contextlib import contextmanager
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Any, Iterator
from nagare.models import ScopeContract
from nagare.steerer import MicroSteerer
from nagare.observer import FileSystemObserver
from nagare.paths import CONTRACT_FILE

@dataclass
class BenchmarkResult:
    scenario_name: str
    iterations: int
    avg_latency_ms: float
    median_latency_ms: float
    min_latency_ms: float
    max_latency_ms: float
    p99_latency_ms: float
    corruptions_blocked: int
    corruptions_allowed: int
    success_rate_percent: float
    kind: str = "rollback"  # rollback | end_to_end | hook

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario": self.scenario_name,
            "kind": self.kind,
            "iterations": self.iterations,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "median_latency_ms": round(self.median_latency_ms, 2),
            "min_latency_ms": round(self.min_latency_ms, 2),
            "max_latency_ms": round(self.max_latency_ms, 2),
            "p99_latency_ms": round(self.p99_latency_ms, 2),
            "blocked": self.corruptions_blocked,
            "allowed": self.corruptions_allowed,
            "success_rate": f"{self.success_rate_percent:.1f}%",
        }


def _summarize(name: str, kind: str, latencies_ms: List[float], blocked: int) -> BenchmarkResult:
    ordered = sorted(latencies_ms)
    n = len(ordered)
    return BenchmarkResult(
        scenario_name=name,
        iterations=n,
        avg_latency_ms=statistics.mean(ordered),
        median_latency_ms=statistics.median(ordered),
        min_latency_ms=ordered[0],
        max_latency_ms=ordered[-1],
        p99_latency_ms=ordered[min(int(n * 0.99), n - 1)],
        corruptions_blocked=blocked,
        corruptions_allowed=n - blocked,
        success_rate_percent=(blocked / n) * 100.0 if n else 100.0,
        kind=kind,
    )


@contextmanager
def scratch_clone(repo_root: Path) -> Iterator[Path]:
    """Benchmarks mutate files: run them on a throwaway clone, never on the user's checkout."""
    tmp = Path(tempfile.mkdtemp(prefix="nagare_bench_"))
    try:
        subprocess.run(["git", "clone", "-q", "--local", str(Path(repo_root).resolve()), str(tmp / "repo")],
                       check=True, capture_output=True)
        yield tmp / "repo"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_micro_rollback_benchmark(
    repo_root: Path,
    target_file: Path = Path("protected.py"),
    iterations: int = 25,
    scenario_name: str = "Micro-Rollback Latency"
) -> BenchmarkResult:
    """Time of the restore operation alone (steerer called synchronously after a write)."""
    repo = Path(repo_root).resolve()
    contract = ScopeContract(
        permitted_paths={Path("allowed.py")},
        restricted_paths={target_file}
    )
    steerer = MicroSteerer(repo_root=repo, contract=contract, debounce_seconds=0.0)
    full_path = repo / target_file
    original_content = full_path.read_text(encoding="utf-8") if full_path.exists() else "ORIGINAL = True\n"
    if not full_path.exists():
        full_path.write_text(original_content, encoding="utf-8")

    latencies_ms: List[float] = []
    blocked = 0

    for i in range(iterations):
        full_path.write_text(f"CORRUPTED_MUTATION_{i} = True\n", encoding="utf-8")
        t0 = time.perf_counter()
        steerer.revert_and_steer(target_file)
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)
        if full_path.read_text(encoding="utf-8") == original_content:
            blocked += 1
        time.sleep(0.01)

    return _summarize(scenario_name, "rollback", latencies_ms, blocked)


def run_end_to_end_benchmark(
    repo_root: Path,
    target_file: Path,
    iterations: int = 30,
    scenario_name: str = "End-to-end (write → detected → restored)",
    leak_timeout_s: float = 2.0,
) -> BenchmarkResult:
    """Wall time from an unsupervised write hitting disk until the bytes on disk are restored.

    Includes kernel inotify delivery, watchdog dispatch, policy decision and restore — the number
    that matters for "how long can a corrupted file exist".
    """
    repo = Path(repo_root).resolve()
    full_path = repo / target_file
    original = full_path.read_bytes()
    contract = ScopeContract(permitted_paths={Path("allowed.py")}, restricted_paths={Path(target_file)})
    steerer = MicroSteerer(repo, contract, debounce_seconds=0.0)
    lock = threading.RLock()

    def on_change(rel: Path, _restricted: bool):
        with lock:
            steerer.handle_change(rel)

    observer = FileSystemObserver(repo, contract, on_change)
    observer.start()
    time.sleep(0.3)
    latencies_ms: List[float] = []
    blocked = 0
    try:
        for i in range(iterations):
            t0 = time.perf_counter()
            full_path.write_bytes(f"CORRUPTED_{i}\n".encode())
            restored = False
            while time.perf_counter() - t0 < leak_timeout_s:
                try:
                    if full_path.read_bytes() == original:
                        restored = True
                        break
                except OSError:
                    pass
                time.sleep(0.0002)
            latencies_ms.append((time.perf_counter() - t0) * 1000.0)
            blocked += int(restored)
            if not restored:
                full_path.write_bytes(original)
            time.sleep(0.15)
    finally:
        observer.stop()
    return _summarize(scenario_name, "end_to_end", latencies_ms, blocked)


def run_hook_latency_benchmark(repo_root: Path, target_file: Path, iterations: int = 20,
                               scenario_name: str = "Bob PreToolUse hook (deny before write)") -> BenchmarkResult:
    """Cold-start cost of the hook process Bob spawns before each file-writing tool call."""
    repo = Path(repo_root).resolve()
    contract = ScopeContract(permitted_paths={Path("allowed.py")}, restricted_paths={Path(target_file)})
    contract.save(repo / CONTRACT_FILE)
    payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "write_file",
                          "tool_input": {"path": Path(target_file).as_posix(), "content": "x"}, "cwd": str(repo)})
    original = (repo / target_file).read_bytes()
    latencies_ms: List[float] = []
    blocked = 0
    try:
        for _ in range(iterations):
            t0 = time.perf_counter()
            res = subprocess.run([sys.executable, "-m", "nagare.hooks", "--repo", str(repo)],
                                 input=payload, capture_output=True, text=True)
            latencies_ms.append((time.perf_counter() - t0) * 1000.0)
            try:
                denied = json.loads(res.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
            except (ValueError, KeyError):
                denied = False
            blocked += int(denied and (repo / target_file).read_bytes() == original)
    finally:
        (repo / CONTRACT_FILE).unlink(missing_ok=True)
    return _summarize(scenario_name, "hook", latencies_ms, blocked)


def generate_benchmark_markdown_report(results: List[BenchmarkResult], out_file: Path) -> Path:
    out_path = Path(out_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    now_str = datetime.datetime.now().isoformat(timespec="seconds")
    env = f"{platform.system()} {platform.machine()}, Python {platform.python_version()}"

    def rows(kind: str) -> str:
        return "\n".join(
            f"| **{r.scenario_name}** | {r.iterations} | {r.median_latency_ms:.2f} ms | {r.avg_latency_ms:.2f} ms | "
            f"{r.p99_latency_ms:.2f} ms | {r.max_latency_ms:.2f} ms | {r.corruptions_blocked}/{r.iterations} |"
            for r in results if r.kind == kind
        ) or "| *not run* | | | | | | |"

    header = "| Scenario | Runs | Median | Mean | P99 | Max | Restored / Denied |\n|---|---|---|---|---|---|---|"
    e2e = [r for r in results if r.kind == "end_to_end"]
    worst_e2e = max((r.max_latency_ms for r in e2e), default=None)
    leaks = sum(r.corruptions_allowed for r in e2e)

    findings = []
    if e2e:
        findings.append(
            f"- **Exposure window**: an unsupervised write to a protected file exists on disk for a median of "
            f"{statistics.median([r.median_latency_ms for r in e2e]):.1f} ms before Nagare restores it "
            f"(worst observed {worst_e2e:.0f} ms); {leaks} of {sum(r.iterations for r in e2e)} writes were not restored within 2 s."
        )
    hooks = [r for r in results if r.kind == "hook"]
    if hooks:
        findings.append(
            f"- **Prevention cost**: the Bob PreToolUse hook answers in a median of {hooks[0].median_latency_ms:.0f} ms "
            f"(cold Python start included); denied writes never touch disk."
        )
    findings.append(
        "- **Scope of the claim**: \"restored\" means the protected file's bytes equal the session baseline after "
        "a deliberate corrupting write. These are micro-benchmarks on one machine, single run per scenario."
    )

    content = f"""# Nagare Governor Benchmark Report

> **Generated:** {now_str} · **Environment:** {env} · Scenarios run on throwaway git clones.

## 1. End-to-end exposure window (write → inotify → policy → restored)
{header}
{rows("end_to_end")}

## 2. Layer 1 — Bob PreToolUse hook latency (deny before the write happens)
{header}
{rows("hook")}

## 3. Restore operation alone (synchronous micro-rollback)
{header}
{rows("rollback")}

## Findings
{chr(10).join(findings)}
"""
    out_path.write_text(content, encoding="utf-8")
    return out_path
