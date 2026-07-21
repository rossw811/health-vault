---
description: Pull EVERY Oura metric available (daily summary, sleep, readiness, activity, workouts, heart rate, stress, SpO2, sessions/meditation, trends) via the oura MCP server into Daily note frontmatter, auto-populate active_protocols from Protocols/ status so /oura-analyze has tags to compare, then regenerate the local dashboard. --backfill pulls full history once; default daily run only fills today/gaps. Designed to run unattended on a schedule.
category: vault
---

Execute `/oura-sync [--backfill]`:

## 0. Backfill mode (`--backfill`) — run once, or whenever there's a real gap
Pull the **entire history** the Oura account has data for, not just today:
1. Check `oura_trends` (or the equivalent range-capable tool) for the earliest date with real data — Oura typically has data from whenever the ring was first worn.
2. For every date from that earliest date through yesterday, check whether `Daily/YYYY-MM-DD.md` already has real (non-`TBD`) biometric values. Skip dates that are already fully populated — this makes backfill safe to re-run without redundant API calls.
3. For every remaining date, pull the same full metric set as step 1 below and create/update that date's Daily note. If the MCP tools only accept a single date per call (no range parameter), loop day by day rather than assuming a range works — check the actual tool signature first.
4. This can be a lot of calls for a long history — say up front how many dates need backfilling before starting, same "no silent caps" principle as everywhere else in this vault.

### Checkpointing (required for any multi-day backfill, especially when split across parallel workers)
A long backfill can die mid-run (rate limit, spend limit, crash) — don't let that lose all progress. Follow the same resumable-state convention as `Research/YouTube/.state/*.json`:
- If the backfill is split into date-range chunks (e.g. across parallel subagents), each chunk gets its own state file at `Daily/.state/oura-backfill-<chunk-label>.json` — never share one state file across concurrent writers, that's a race condition.
- After **every single date** finishes (successfully or with an error), immediately append/update that date's entry in the chunk's state file — don't batch updates until the end, since the whole point is surviving a mid-run death:
  ```json
  {
    "range_start": "YYYY-MM-DD",
    "range_end": "YYYY-MM-DD",
    "processed_dates": [
      {"date": "YYYY-MM-DD", "status": "ok"},
      {"date": "YYYY-MM-DD", "status": "no_data", "note": "before ring was worn"},
      {"date": "YYYY-MM-DD", "status": "error", "note": "which tool call failed and why"}
    ],
    "last_updated": "YYYY-MM-DD"
  }
  ```
- On any resume, read the chunk's state file first — every date already listed (any status) is done; only process dates missing from `processed_dates`. This is cheaper and more precise than re-deriving progress from `Daily/*.md` existence/TBD-scanning, though that remains a valid fallback if a state file is ever lost.
- `status: "error"` entries are still "processed" for resume purposes (don't retry them silently forever) but should be called out in the final summary so a human can decide whether to investigate or re-run just those dates.

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

### Known bug: `oura_sleep` (periods), `oura_activity`, `oura_workouts`, `oura_sessions` return empty for single-day queries
`@daveremy/oura-mcp` (see `scripts/run-oura-mcp.mjs`) always queries Oura's v2 API with `start_date == end_date == <day>`. Oura's `daily_sleep`, `daily_readiness`, `daily_stress`, and `daily_spo2` endpoints tolerate that fine (contributor *scores* come through correctly), but the `sleep` (raw periods — total/REM/deep/light hours, latency, efficiency, average_hrv, lowest_heart_rate), `daily_activity` (score, steps, calories, activity/inactivity minutes), `workout`, and `session` endpoints silently return an **empty result** unless `end_date` is strictly after `start_date` — confirmed directly against the raw API, including on dates known to have real records. This is not a missing-data situation; it looks like missing data (`TBD`/`[]`) but the data exists and is one day-boundary away from being returned correctly.
- For `--backfill` or any multi-day pull, don't rely on the MCP tool for these four fields' data. Query the real Oura API directly (`https://api.ouraring.com/v2/usercollection/<endpoint>`, `Authorization: Bearer $OURA_TOKEN` from `.env`) with `end_date` one day past the range you actually want, filter each returned record by its own `day` field, and map: `sleep.average_hrv` → `average_hrv`; `sleep.total_sleep_duration/3600` → `sleep_total_hours`; `sleep.efficiency` → `sleep_efficiency`; `sleep.latency/60` → `sleep_latency_min`; `sleep.rem_sleep_duration/3600` → `sleep_rem_hours`; `sleep.deep_sleep_duration/3600` → `sleep_deep_hours`; `sleep.light_sleep_duration/3600` → `sleep_light_hours`; `sleep.lowest_heart_rate` → `resting_hr` (this is the authoritative source for `resting_hr` — prefer it over deriving from the raw `oura_heart_rate` continuous stream); `daily_activity.score` → `activity_score`; `.steps` → `steps`; `.active_calories` → `calories_active`; `(low_activity_time+medium_activity_time+high_activity_time)/60` → `activity_total_min`; `sedentary_time/60` → `inactivity_min`; `workout`/`session` records (grouped by `day`) → the `workouts`/`sessions` lists.
- `scripts/oura_backfill_fix.py` is the reference implementation (one range call per endpoint, not per-day) — reuse or adapt it rather than re-deriving this from scratch each time. For a **single day's sync** (the daily scheduled run), the same fix applies: query with `end_date = today + 1 day`, not `end_date = today`.
- This is a bug in the third-party `@daveremy/oura-mcp` package, not something fixable by editing vault files — re-check whether a newer package version has fixed it before assuming this workaround is needed forever.

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

## 2.5. Auto-populate active_protocols from Protocols/ status
This is the actual mechanism that makes tag-based analysis (`/oura-analyze`) possible at all — until this runs, `active_protocols` stays permanently empty and there's nothing for that analysis to compare. Scan every `Protocols/*.md` for frontmatter `status: active` (optionally with `start_date`/`end_date`):

- **For today's sync (no `--backfill`)**: set `active_protocols` to exactly the note titles of every Protocol currently `status: active` where today falls inside `start_date`/`end_date` if those are set (no bounds given = assume active). This REPLACES the field each run — it's meant to reflect "what's active right now," not accumulate. If you (or the user) manually added an ad-hoc entry that doesn't correspond to any Protocol note, keep it (union, don't silently drop manual entries) — only the auto-detected part gets refreshed.
- **For `--backfill` dates**: only set `active_protocols` for a historical date if a Protocol note has explicit `start_date`/`end_date` bounds covering that date — without explicit dates, there's no honest way to know retroactively what was active, so leave it as `[]`/`TBD` for that day rather than guessing. Note in the summary how many backfilled days got a real protocol tag vs. how many couldn't be determined.
- If zero `Protocols/*.md` notes currently have `status: active`, say so plainly in the summary rather than silently leaving the field empty with no explanation — this is expected until a real protocol gets tagged that way, not a bug.

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
