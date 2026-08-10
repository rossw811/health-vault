---
description: Pull literally every Oura data point available — every endpoint the API exposes (daily summary, sleep incl. raw periods/time-series, readiness, activity incl. full contributor breakdown, workouts, continuous heart rate, stress, SpO2, sessions/meditation, resilience, cardiovascular age, vO2max, sleep-time recommendations, logged tags, trends) via scripts/oura_full_sync.py (direct Oura API — the oura MCP server is structurally incomplete, see step 1) into Daily/.oura-raw/ raw JSON + Daily note frontmatter, auto-populate active_protocols from Protocols/ status so /oura-analyze has tags to compare, then regenerate the local dashboard. --backfill pulls full history once; default daily run only fills today/gaps. Designed to run unattended on a schedule.
category: vault
---

Execute `/oura-sync [--backfill]`:

## 0. Backfill mode (`--backfill`) — run once, or whenever there's a real gap

**Now a single script invocation, not a per-date Claude-driven loop:**
```bash
python scripts/oura_full_sync.py --backfill
```
This pulls the entire history from the ring's `set_up_at` date (from `ring_configuration`, fetched automatically) through yesterday, in one process — it paginates every endpoint internally via `next_token`, indexes every record by its own `day` field, and upserts every `Daily/*.md` note plus its `Daily/.oura-raw/<date>.json` in a single pass. It's naturally idempotent and safe to re-run: a field is only rewritten if the new value actually differs from what's already there, so a repeat run does no harmful work. The per-date checkpoint-file machinery this section used to describe (for a multi-agent, tool-call-per-date backfill) is no longer needed for that reason — the script itself doesn't die mid-range the way a long chain of individual MCP tool calls could, and if it does crash, just re-run the same command; already-correct fields are left alone.

If a full historical backfill ever needs to run split across parallel workers for genuinely large date ranges, fall back to invoking the script once per date-range chunk (`--start`/`--end`) — each chunk writes to disjoint `Daily/*.md`/`Daily/.oura-raw/*.json` files, so no shared state file or locking is needed the way the old Research/YouTube-style checkpoint convention required.

**Without `--backfill`, pull yesterday through today** (`python scripts/oura_full_sync.py --start <yesterday> --end <today>`) — changed 2026-08-08, was previously today-only. Two real, independently-confirmed incidents (`buglog.md`, 2026-08-04 and 2026-08-05) showed why today-only isn't enough: (1) readiness/sleep/HRV endpoints intermittently return `null` on same-day queries even when the ring was worn — this self-corrects on a later re-run, but only if something re-pulls that date; (2) `daily_activity` can be fetched mid-day while the day's total is still accumulating, silently writing a low-but-plausible-looking number (e.g. `steps: 8`) instead of an honest `TBD` — this doesn't fix itself without a later re-pull either. Re-pulling yesterday alongside today, every single day, catches both failure modes automatically (the script is idempotent — see backfill's note above — so re-writing an already-correct yesterday costs nothing). Backfill is either run manually once for history, or re-run later (`--start`/`--end`) if a real multi-day gap opened up (e.g. the scheduled task didn't fire for several days).

## 1. Pull literally everything Oura has — no curated subset, no gaps

**The `oura` MCP server is not the sync mechanism — `scripts/oura_full_sync.py` is.** Confirmed live 2026-07-26: `@daveremy/oura-mcp` (a) always queries `start_date == end_date == <day>`, which Oura silently returns empty/null for on the `sleep` (periods), `daily_activity`, `workout`, and `session` endpoints (live-verified: `oura_activity` returned `null` and `oura_sleep`'s `periods` returned `[]` on every date tested, including dates with real data confirmed via the direct API), and (b) has no tool at all for `daily_resilience`, `daily_cardiovascular_age`, `vO2_max`, `rest_mode_period`, `ring_configuration`, `tag`, `enhanced_tag`, `sleep_time`, or `personal_info` — roughly 40% of Oura's real v2 endpoints are simply absent from the wrapper. Both are structural limits of the third-party package, not something a cleverer MCP call works around.

Run:
```bash
python scripts/oura_full_sync.py --start A --end B         # explicit range - default daily run uses yesterday..today, see step 0
python scripts/oura_full_sync.py --date YYYY-MM-DD          # single day, if a range genuinely isn't wanted
python scripts/oura_full_sync.py --backfill                # full history, ring set-up date through yesterday
```
This talks to `https://api.ouraring.com/v2/usercollection/*` directly (same pattern `scripts/oura_backfill_fix.py` first validated), with correct `end_date = range_end + 1` semantics on every endpoint. **Retry-with-backoff added 2026-08-08**: transient network failures (e.g. `RemoteDisconnected`) and 5xx server errors now retry automatically (4 attempts, 2/5/15/30s backoff) instead of discarding the whole run's already-fetched data on one blip; a persistent failure on any single endpoint no longer crashes the entire fetch — other endpoints' data still gets written. It writes two things per day, every run:
1. **`Daily/.oura-raw/<date>.json`** — the complete, unmodified raw payload for every endpoint that has data that day, including the large time-series arrays (heart-rate/HRV/MET streams, movement and sleep-phase strings) that don't belong in frontmatter. This is the actual "no gaps" guarantee — treat it as the source of truth if a curated frontmatter field is ever in question.
2. **`Daily/<date>.md` frontmatter** — every scalar summary field with real data for that day (see the schema in step 2 — it now includes readiness's `sleep_regularity` contributor, full resilience/cardiovascular-age/sleep-time/vO2max data, and the complete activity contributor + totals breakdown, none of which the MCP wrapper could ever surface).

The `oura` MCP tools remain useful for **ad-hoc interactive questions** during a session ("what's my readiness today") since they're faster than shelling out to Python — just don't rely on them for the sync itself, and don't trust `oura_activity`/`oura_sleep`'s `periods`/`oura_workouts`/`oura_sessions` for anything beyond a quick same-day sanity check, since those four are the ones confirmed broken.

If the script reports an endpoint fetch failure (see its stderr warnings), that's a real Oura API error (token invalid, endpoint down) — report it, don't fabricate placeholder values. Fields with genuinely no data for a day stay `TBD`/`[]`, same anti-fabrication rule as always.

## 2. Update the Daily note (today, or each backfilled date)
Resolve `Daily/YYYY-MM-DD.md` for the target date (create from scratch with the schema below if it doesn't exist yet; if it exists, update only the biometric fields, never overwrite the protocol checklist or any content already there):

`scripts/oura_full_sync.py` creates/updates notes against this schema (see `FULL_FRONTMATTER_TEMPLATE` in that script for the authoritative version — don't let this doc drift from it):

```yaml
---
date: <YYYY-MM-DD>
type: daily-log
readiness_score:
readiness_hrv_balance:
readiness_resting_hr:
readiness_body_temp_deviation:
readiness_temp_trend_deviation:
readiness_recovery_index:
readiness_sleep_balance:
readiness_activity_balance:
readiness_previous_day_activity:
readiness_previous_night:
readiness_sleep_regularity:      # 9th readiness contributor — missing from every prior version of this schema until 2026-07-26
sleep_score:
sleep_contrib_deep:              # the 7 daily_sleep sub-score contributors — previously only the top-line score was captured
sleep_contrib_efficiency:
sleep_contrib_latency:
sleep_contrib_rem:
sleep_contrib_restfulness:
sleep_contrib_timing:
sleep_contrib_total:
sleep_total_hours:
sleep_efficiency:
sleep_latency_min:
sleep_rem_hours:
sleep_deep_hours:
sleep_light_hours:
sleep_time_in_bed_hours:
sleep_bedtime_start:
sleep_bedtime_end:
sleep_avg_breath:
sleep_restless_periods:
sleep_type:                      # long_sleep | nap
sleep_algorithm_version:
sleep_awake_time_min:
sleep_extra_periods_logged: 0    # count of same-day naps beyond the primary long_sleep period (full detail in Daily/.oura-raw/)
sleep_time_recommendation:       # from the sleep_time endpoint (bedtime-optimization guidance)
sleep_time_optimal_bedtime:
sleep_time_status:
average_hrv:
resting_hr:
activity_score:
steps:
calories_active:
activity_total_min:
inactivity_min:
activity_contrib_meet_daily_targets:   # the 6 daily_activity sub-score contributors — not previously captured at all
activity_contrib_move_every_hour:
activity_contrib_recovery_time:
activity_contrib_stay_active:
activity_contrib_training_frequency:
activity_contrib_training_volume:
activity_equivalent_walking_distance_m:
activity_non_wear_min:
activity_resting_min:
activity_high_met_min:
activity_medium_met_min:
activity_low_met_min:
activity_target_calories:
activity_total_calories:
activity_target_meters:
activity_meters_to_target:
activity_inactivity_alerts:
resilience_level:                # daily_resilience — an endpoint the MCP wrapper never exposed at all
resilience_sleep_recovery:
resilience_daytime_recovery:
resilience_stress:
cardio_vascular_age:             # daily_cardiovascular_age — same, never exposed via MCP
cardio_pulse_wave_velocity:
vo2_max:                         # vO2_max endpoint; TBD until Oura has computed one
workouts: []           # list of {type, distance_m, calories, intensity, label, source} per logged workout
stress_summary:        # if available on this account's tier
spo2_avg:              # if available
sessions: []           # list of {type, avg_heart_rate, avg_hrv, mood, motion_count} per meditation/breathing/rest session
oura_tags_logged: []   # user-logged Oura app tags (e.g. "airplane") for this day — distinct from the vault's own `tags:` field below
active_protocols: []   # only set on creation; never overwritten on update
training_load_hrs: 0   # only set on creation; never overwritten on update
tags: [biometrics, health-tracking]
---
```

Fields with no data for today: write `TBD`, don't omit the field and don't guess a value. Time-series data (continuous heart rate, per-sleep HRV/heart-rate/movement arrays, the activity MET stream, sleep-phase strings) is deliberately **not** in this frontmatter — it lives in full in `Daily/.oura-raw/<date>.json`, since a single day's heart-rate stream alone can run to several thousand data points.

## 2.5. Auto-populate active_protocols from Protocols/ status
This is the actual mechanism that makes tag-based analysis (`/oura-analyze`) possible at all — until this runs, `active_protocols` stays permanently empty and there's nothing for that analysis to compare. Scan every `Protocols/*.md` for frontmatter `status: active` (optionally with `start_date`/`end_date`):

- **For today's sync (no `--backfill`)**: set `active_protocols` to exactly the note titles of every Protocol currently `status: active` where today falls inside `start_date`/`end_date` if those are set (no bounds given = assume active). This REPLACES the field each run — it's meant to reflect "what's active right now," not accumulate. If you (or the user) manually added an ad-hoc entry that doesn't correspond to any Protocol note, keep it (union, don't silently drop manual entries) — only the auto-detected part gets refreshed.
- **For `--backfill` dates**: only set `active_protocols` for a historical date if a Protocol note has explicit `start_date`/`end_date` bounds covering that date — without explicit dates, there's no honest way to know retroactively what was active, so leave it as `[]`/`TBD` for that day rather than guessing. Note in the summary how many backfilled days got a real protocol tag vs. how many couldn't be determined.
- If zero `Protocols/*.md` notes currently have `status: active`, say so plainly in the summary rather than silently leaving the field empty with no explanation — this is expected until a real protocol gets tagged that way, not a bug.

**Compound-adherence tags, added 2026-08-04**: for compounds with no `Protocols/*.md` note of their own but where nightly/daily adherence is the actual thing worth comparing against biometrics (e.g. DSIP — see [[Optimization/Sleep]] and [[Optimization/Compound-Biomarker Measurement Plan]]), the manual-entry mechanism above is the intended path: if Ross reports taking a compound that day/night, add its name as a plain string to `active_protocols` (e.g. `"DSIP"`) alongside whatever auto-detected protocol tags are present. This is a manual entry per the rule above — it survives the auto-refresh, and `/oura-analyze`'s existing tag-vs-biometric comparison can test it directly (taken-nights vs. not-taken-nights) without any new field or script change. If Ross doesn't mention taking it, leave the tag off that day — absence of the tag means "not confirmed taken," not "confirmed not taken."

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
