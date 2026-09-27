#!/usr/bin/env python3
"""Deterministic Nagare demo (no LLM, no Bobcoins): a scripted "rogue agent" that bypasses
tool-level guards via the shell, on a throwaway copy of demo_app.

Shows, in one run:
  - in-scope edits and new tests are kept,
  - Bob-shaped write_file calls to schema.sql, and CREATE TABLE smuggled into auth.py,
    are denied by the real PreToolUse hook handler,
  - `sed -i` on schema.sql (a shell write no tool-level rule can see) is restored,
  - a write to core/config.py is restored,
  - an out-of-scope new file is quarantined (not deleted),
  - the developer's own uncommitted work-in-progress is never touched.

Usage: python scripts/demo_scripted.py
"""

import sys

from nagare.demo import run_demo


def main() -> int:
    result = run_demo(delay=0.3, keep="--keep" in sys.argv,
                      on_repo_ready=lambda repo: print(f"Governing a throwaway copy at {repo}\n"))
    print("\nVerification")
    for label, ok in result.checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    snap = result.snapshot
    print(f"\nDenied before write: {snap.total_denied} · Rolled back: {snap.total_rollbacks} · "
          f"Quarantined: {snap.total_quarantined} · Developer changes preserved: {snap.preserved_user_files}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
