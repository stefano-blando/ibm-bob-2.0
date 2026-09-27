# Bob Task Sessions (Judging Deliverables)

This folder contains exported task session reports and consumption summaries from **IBM Bob**, as required by the hackathon submission guidelines.

## Requirements for Submission
1. **Export Task History**:
   - In Bob IDE: `Views and More Actions` > `History` > Select project workspace > Select task > Click **Export task history** icon (`.md` file).
   - In Bob Shell: Session logs/reports.
2. **Consumption Summary**:
   - Screenshot of the task session consumption summary (showing Bobcoins usage).
3. **Security Caution**:
   - Ensure all API keys, tokens, and personal credentials are removed before committing files to this folder.

## Contents of this folder
- `live_ab_20260927/` — live IBM Bob A/B runs (same prompt, governed vs ungoverned) with diffs, transcripts and Bob's cost lines. **Start here.**
- `nagare_session_*.md` — Nagare session reports. Files dated 2026-09-26 and the early hours of 2026-09-27 were produced by v0.1/v0.2, which rolled back to HEAD and could revert the developer's own files (e.g. `backend/nagare/runner.py`, `.bob`); they are kept for the record. The 221800 run used a prompt that *asked* for the schema edit, and its 116 schema interceptions include a ~6/s write/rollback loop.
- `bobalytics/` — Bob usage export from the Bob profile (Bobalytics, 2026-08-29 → 2026-09-27): 2 active days, 33 tasks completed (5 on 26 Sep, 28 on 27 Sep), **28.78 Bobcoins** used (`user_Activity_pattern.csv`, `user_Days_active.csv`, dashboard screenshot `bobalytics_metrics_2026-09-27.png`). The CSV "Spend" column sums to 28.77 (rounded per day).
- `bob_shell_tasks/` — full Bob Shell task history (53 tasks, 28.78 Bobcoins, matching Bobalytics) exported from Bob Shell's local task store with `scripts/export_bob_tasks.py`: one Markdown file per task with prompt, Bob's messages, tool calls and per-step Bobcoins. Start at `bob_shell_tasks/INDEX.md`.
