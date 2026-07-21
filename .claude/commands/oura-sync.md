---
description: Pull EVERY Oura metric available (daily summary, sleep, readiness, activity, workouts, heart rate, stress, SpO2, sessions/meditation, trends) via the oura MCP server into Daily note frontmatter, then regenerate the local dashboard. --backfill pulls full history once; default daily run only fills today/gaps. Designed to run unattended on a schedule.
category: vault
---

Execute `/oura-sync [--backfill]`:

## 0. Backfill mode (`--backfill`) — run once, or whenever there's a real gap
Pull the **entire history** the Oura account has data for, not just today:
1. Check `oura_trends` (or the equivalent range-capable tool) for the earliest date with real data — Oura typically has data from whenever the ring was first worn.
2. For every date from that earliest date through yesterday, check whether `Daily/YYYY-MM-DD.md` already has real (non-`TBD`) biometric values. Skip dates that are already fully populated — this makes backfill safe to re-run without redundant API calls.
3. For every remaining date, pull the same full metric set as step 1 below and create/update that date's Daily note. If the MCP tools only accept a single date per call (no range parameter), loop day by day rather than assuming a range works — check the actual tool signature first.
4. This can be a lot of calls for a long history — say up front how many dates need backfilling before starting, same "no silent caps" principle as everywhere else in this vault.

Without `--backfill`, only pull **today** (default) — that's what the daily scheduled run does. Backfill is either run manually once for history, or re-run later if a real gap opened up (e.g. the scheduled task didn't fire for a few days).

## 1. Pull EVERY available Oura metric, not just the headline ones
Use every tool the `oura` MCP server exposes (see `.mcp.json`) for the target date(s) — this is a deliberate "pull all of it" pass, not a curated subset:
- `oura_daily_summary` — the day's rollup
- `oura_readiness` — readiness score + its component contributors (HRV balance, resting HR, body temperature deviation, recovery index, sleep balance)
- `oura_sleep` — sleep score + components (total sleep, efficiency, latency, REM/deep/light breakdown, restfulness, timing)
- `oura_heart_rate` — resting HR, average HRV, overnight HR trend
- `oura_activity` — activity score, steps, calories, total activity time, inactivity time
- `oura_workouts` — any logged workout sessions today (type, duration, intensity)
- `oura_stress` — daily stress/recovery balance if available on the account's Oura tier
- `oura_spo2` — blood oxygen if available
- `oura_sessions` — meditation/breathing/rest sessions if logged
- `oura_trends` — recent multi-day trend context (useful for the "consistent with protocol" check in step 3)

If a given tool/metric isn't available for this account/day (e.g. no SpO2 sensor data, no workout logged), record it as genuinely absent — don't skip silently, note which categories had no data. If the MCP server errors outright (token missing/invalid, API down), report the specific error and stop — do not fabricate placeholder values for anything.

## 2. Update the Daily note (today, or each backfilled date)
Resolve `Daily/YYYY-MM-DD.md` for the target date (create from scratch with the schema below if it doesn't exist yet; if it exists, update only the biometric fields, never overwrite the protocol checklist or any content already there):

```yaml
---
date: <YYYY-MM-DD>
type: daily-log
readiness_score:
readiness_hrv_balance:
readiness_resting_hr:
readiness_body_temp_deviation:
readiness_recovery_index:
readiness_sleep_balance:
sleep_score:
sleep_total_hours:
sleep_efficiency:
sleep_latency_min:
sleep_rem_hours:
sleep_deep_hours:
sleep_light_hours:
average_hrv:
resting_hr:
activity_score:
steps:
calories_active:
activity_total_min:
inactivity_min:
workouts: []          # list of {type, duration_min, intensity} if any logged
stress_summary:        # if available on this account's tier
spo2_avg:              # if available
sessions: []           # meditation/breathing/rest sessions logged today
active_protocols: []   # only set on creation; never overwritten on update
training_load_hrs: 0   # only set on creation; never overwritten on update
tags: [biometrics, health-tracking]
---
```

Fields with no data for today: write `TBD`, don't omit the field and don't guess a value.

## 3. Cross-reference against active protocols and recent trends
If `active_protocols` is non-empty, use `oura_trends` plus today's numbers to note whether today's readiness/HRV/sleep looks consistent with or diverges from what's expected under those protocols — a one-line observation, not a full analysis (that's what `/storm-panel`/`/concept-audit` are for).

## 4. Regenerate the dashboard
Run:
```bash
python "scripts/generate_dashboard.py"
```
This reads recent `Daily/` frontmatter and rewrites `Dashboard/index.html`. Report if it fails, but a dashboard-generation failure should not be treated as an Oura-sync failure — the frontmatter update in step 2 is the primary job.

## 5. Summary
Every category pulled and what came back (including which were genuinely unavailable), whether the daily note(s) were created or updated, any protocol-consistency note, and confirmation the dashboard regenerated (or its error). For `--backfill`: how many dates were found already-populated and skipped vs. newly filled.

**Anti-fabrication:** if any Oura metric is unavailable for today (e.g. ring not worn, sync delay, sensor/tier doesn't support it), record it as missing/`TBD` rather than inventing a plausible-looking number.
