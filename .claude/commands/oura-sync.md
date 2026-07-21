---
description: Pull today's Oura readiness/sleep/HRV/resting-HR/activity via the oura MCP server into today's Daily note frontmatter, then regenerate the local dashboard. Designed to run unattended on a schedule.
category: vault
---

Execute `/oura-sync`:

## 1. Pull live Oura data
Use the `oura` MCP server's tools (see `.mcp.json`) for today's date: readiness score, sleep score, average HRV, resting heart rate, and any logged activity/training load. If the MCP server errors (token missing/invalid, API down), report the specific error and stop — do not fabricate placeholder values.

## 2. Update today's Daily note
Resolve today's `Daily/YYYY-MM-DD.md` (create from scratch with the schema below if it doesn't exist yet, matching `CLAUDE.md`'s documented format; if it exists, update only the biometric fields, never overwrite the protocol checklist or any content already there):

```yaml
---
date: <YYYY-MM-DD>
type: daily-log
readiness_score: <from Oura>
sleep_score: <from Oura>
average_hrv: <from Oura>
resting_hr: <from Oura>
active_protocols: []   # only set on creation; never overwritten on update
training_load_hrs: 0   # only set on creation; never overwritten on update
tags: [biometrics, health-tracking]
---
```

## 3. Cross-reference against active protocols
If `active_protocols` is non-empty, briefly note in the daily note whether today's readiness/HRV looks consistent with or diverges from what's expected under those protocols — a one-line observation, not a full analysis (that's what `/storm-panel`/`/concept-audit` are for).

## 4. Regenerate the dashboard
Run:
```bash
python "scripts/generate_dashboard.py"
```
This reads recent `Daily/` frontmatter and rewrites `Dashboard/index.html`. Report if it fails, but a dashboard-generation failure should not be treated as an Oura-sync failure — the frontmatter update in step 2 is the primary job.

## 5. Summary
Today's pulled values, whether the daily note was created or updated, any protocol-consistency note, and confirmation the dashboard regenerated (or its error).

**Anti-fabrication:** if any Oura metric is unavailable for today (e.g. ring not worn, sync delay), record it as missing/`TBD` rather than inventing a plausible-looking number.
