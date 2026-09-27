#!/usr/bin/env python3
"""Replay real commits to measure whether Nagare's scope contract would block legitimate work.

For each sampled commit C (non-merge, human-authored, 1..MAX_FILES changed files):
  - check out C's parent,
  - synthesize the scope contract from C's commit message (subject + body) as the task prompt,
  - ask the contract's policy what it would do with every file C actually changed.

A commit "passes" when no file it changed would be reverted/quarantined/denied: Nagare would have
let a human (or an agent doing the same work) finish the task. We also record how much of the
repository the contract opens up (smaller = tighter lane) and file-level recall.

Commit messages are a pessimistic proxy for task prompts (they rarely name files), so absolute
numbers understate real-prompt performance; comparisons between variants are the point.

Usage:
  python experiments/scope_eval.py --repos-dir <dir> --out experiments/results/scope_eval.json
"""

import argparse
import json
import random
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Dict, List, Optional

from nagare.models import ScopeContract, ViolationAction, Policy
from nagare.scope import ScopeSynthesizer
from nagare.paths import should_ignore

MAX_FILES = 10
SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
BOT_RE = re.compile(r"bot\b|dependabot|renovate|pre-commit-ci|github-actions", re.I)
SKIP_SUBJECT_RE = re.compile(r"^(bump|build\(deps|chore\(deps|\[pre-commit|merge|release|version|update .*requirements)", re.I)


@dataclass
class CommitSample:
    sha: str
    parent: str
    message: str
    changes: List[tuple]  # (status, path)


@dataclass
class VariantResult:
    variant: str
    passed: bool
    blocked_files: List[str]
    gold_source_files: int
    gold_source_permitted: int
    permitted_count: int
    graph_nodes: int
    sensitive_blocked: int


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout


def sample_commits(repo: Path, n: int, seed: int, subdir: Optional[str]) -> List[CommitSample]:
    fmt = "%x1e%H%x1f%P%x1f%an%x1f%B%x1f"
    args = ["log", "--no-merges", f"--format={fmt}", "--name-status", "--no-renames"]
    if subdir:
        args += ["--", subdir]
    raw = git(repo, *args)
    samples = []
    for rec in raw.split("\x1e")[1:]:
        parts = rec.split("\x1f")
        if len(parts) < 5:
            continue
        sha, parents, author, message, names = parts[0], parts[1].split(), parts[2], parts[3].strip(), parts[4]
        if len(parents) != 1 or BOT_RE.search(author) or SKIP_SUBJECT_RE.search(message):
            continue
        changes = []
        for line in names.strip().splitlines():
            bits = line.split("\t")
            if len(bits) == 2 and bits[0] in ("M", "A"):
                changes.append((bits[0], bits[1]))
        changes = [(s, p) for s, p in changes if not should_ignore(Path(p))]
        if subdir:
            changes = [(s, p) for s, p in changes if p.startswith(subdir.rstrip("/") + "/")]
        if not changes or len(changes) > MAX_FILES:
            continue
        if not any(Path(p).suffix in SOURCE_SUFFIXES for _, p in changes):
            continue
        if len(message.split()) < 3:
            continue
        samples.append(CommitSample(sha, parents[0], message, changes))
    rng = random.Random(seed)
    rng.shuffle(samples)
    return samples[:n]


def evaluate_contract(contract: ScopeContract, sample: CommitSample, prefix: str, graph_nodes: int, name: str) -> VariantResult:
    blocked, sensitive_blocked, gold_src, gold_src_ok = [], 0, 0, 0
    for status, path in sample.changes:
        rel = Path(path[len(prefix):] if prefix and path.startswith(prefix) else path)
        decision = contract.decide(rel, is_new=(status == "A"))
        if decision in (ViolationAction.ROLLED_BACK, ViolationAction.DENIED):
            blocked.append(rel.as_posix())
            if contract.is_sensitive(rel):
                sensitive_blocked += 1
        if status == "M" and rel.suffix in SOURCE_SUFFIXES:
            gold_src += 1
            gold_src_ok += int(decision not in (ViolationAction.ROLLED_BACK, ViolationAction.DENIED))
    return VariantResult(
        variant=name, passed=not blocked, blocked_files=blocked,
        gold_source_files=gold_src, gold_source_permitted=gold_src_ok,
        permitted_count=len(contract.permitted_paths), graph_nodes=graph_nodes,
        sensitive_blocked=sensitive_blocked,
    )


# A variant maps (synthesizer with graph already built, prompt) -> contract.
Variant = Callable[[ScopeSynthesizer, str], ScopeContract]


def default_variants() -> Dict[str, Variant]:
    def v(seed: str, expand: str, cochange: bool, policy: Policy = Policy.LANE) -> Variant:
        def run(syn: ScopeSynthesizer, prompt: str) -> ScopeContract:
            return syn.synthesize_scope(prompt, rebuild=False, seed=seed, expand=expand, cochange=cochange, policy=policy)
        return run

    return {
        # Scope construction ablation (policy fixed to LANE: out-of-scope existing code is reverted)
        "lane | mention+out1": v("mention", "out1", False),        # v0.3 algorithm, fixed module resolution
        "lane | mention+both1": v("mention", "both1", False),
        "lane | bm25+none": v("bm25", "none", False),
        "lane | bm25+out1": v("bm25", "out1", False),
        "lane | bm25+both1": v("bm25", "both1", False),
        "lane | bm25+both2": v("bm25", "both2", False),
        "lane | bm25+cochange": v("bm25", "none", True),
        "lane | bm25+both1+cochange": v("bm25", "both1", True),
        # Policy tiers on the default scope
        "guard | bm25+both1+cochange": v("bm25", "both1", True, Policy.GUARD),
        "strict | bm25+both1+cochange": v("bm25", "both1", True, Policy.STRICT),
    }


def sensitive_only(syn: ScopeSynthesizer, prompt: str) -> ScopeContract:
    """Reference policy: everything is permitted except known-sensitive files."""
    contract = syn.synthesize_scope(prompt, rebuild=False, cochange=False)
    contract.permitted_paths = {n for n in syn.graph.nodes if not contract.is_sensitive(n)}
    return contract


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repos-dir", type=Path, required=True)
    ap.add_argument("--repos", nargs="+", default=None, help="repo[:subdir] entries")
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    variants = default_variants()
    variants["sensitive-only (reference)"] = sensitive_only
    results = {"meta": {"n": args.n, "seed": args.seed, "max_files": MAX_FILES, "started": time.time()}, "repos": {}}

    for entry in args.repos:
        name, _, subdir = entry.partition(":")
        repo = args.repos_dir / name
        work = args.repos_dir / f".work_{name}"
        if not work.exists():
            subprocess.run(["git", "clone", "-q", "--local", str(repo), str(work)], check=True)
        samples = sample_commits(repo, args.n, args.seed, subdir or None)
        head = git(repo, "rev-parse", "HEAD").strip()
        print(f"[{name}] {len(samples)} commits sampled (HEAD {head[:8]})", flush=True)
        rows = []
        for i, s in enumerate(samples):
            subprocess.run(["git", "checkout", "-q", "--force", "--detach", s.parent], cwd=work, check=True)
            subprocess.run(["git", "clean", "-qfdx"], cwd=work, check=True)
            root = work / subdir if subdir else work
            prefix = (subdir.rstrip("/") + "/") if subdir else ""
            syn = ScopeSynthesizer(root)
            if hasattr(syn, "set_history_cutoff"):
                syn.set_history_cutoff(s.parent)
            syn.build_dependency_graph()
            nodes = syn.graph.number_of_nodes()
            row = {"sha": s.sha, "message": s.message.splitlines()[0][:120], "changes": s.changes, "variants": {}}
            for vname, fn in variants.items():
                try:
                    contract = fn(syn, s.message)
                    row["variants"][vname] = asdict(evaluate_contract(contract, s, prefix, nodes, vname))
                except Exception as exc:  # keep the sweep going; record the failure
                    row["variants"][vname] = {"error": repr(exc)}
            rows.append(row)
            if (i + 1) % 25 == 0:
                print(f"  {i + 1}/{len(samples)}", flush=True)
        results["repos"][name] = {"head": head, "subdir": subdir, "commits": rows}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=1))
    summarize(results)
    return 0


def summarize(results: dict) -> None:
    print(f"\n{'repo':32} {'variant':32} {'pass%':>6} {'recall%':>8} {'open%':>6} {'sens%':>6}")
    for repo, data in results["repos"].items():
        rows = data["commits"]
        vnames = list(rows[0]["variants"].keys()) if rows else []
        for v in vnames:
            ok = [r["variants"][v] for r in rows if "error" not in r["variants"][v]]
            if not ok:
                continue
            pass_rate = 100 * sum(x["passed"] for x in ok) / len(ok)
            gold = sum(x["gold_source_files"] for x in ok)
            recall = 100 * sum(x["gold_source_permitted"] for x in ok) / gold if gold else float("nan")
            open_frac = 100 * sum(x["permitted_count"] / max(x["graph_nodes"], 1) for x in ok) / len(ok)
            sens = 100 * sum(x["sensitive_blocked"] > 0 for x in ok) / len(ok)
            print(f"{repo:32} {v:32} {pass_rate:6.1f} {recall:8.1f} {open_frac:6.1f} {sens:6.1f}")


if __name__ == "__main__":
    sys.exit(main())
