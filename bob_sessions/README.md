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
- Still to add before submission: Bob's own exported task history (`.md`) and Bobcoin consumption screenshots.
