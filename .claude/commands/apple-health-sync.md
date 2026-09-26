---
description: Import Apple Watch workout heart-rate/calorie data and VO2max from a Health Auto Export JSON file into Daily/*.md frontmatter, scoped narrowly (workouts + vo2_max only, not a duplicate of Oura's coverage). Built 2026-09-03, not yet run against a real export - see the script's own docstring before using.
category: biometrics
---

Execute `/apple-health-sync --export <path>`:

## 0. Prerequisite check — do this before anything else
This has **not been run against real data yet**. Before using it:
1. Confirm Health Auto Export is installed on Ross's phone and has HealthKit read permission.
2. Get at least one real JSON export (Automations → Export → "Save to File" is the simplest one-off path).
3. Run the script against that real file first and actually look at the output — the schema was built from Health Auto Export's own documentation, not from a real export, so treat the first real run as a verification pass, not a routine sync.

## 1. Run the script
```
C:\Python313-arm64\python.exe scripts/apple_health_full_sync.py --export "<path to export.json or a folder of them>"
```
Add `--backfill` for a real historical bulk import (semantic flag only — same logic, just signals "gaps are expected" given Ross's documented day-to-day wear gap).

## 2. What it does (and deliberately doesn't)
Extracts only two things: **workouts** (type, duration, heart rate min/avg/max, active calories — written as `applewatch_workout_*` frontmatter fields) and the **vo2_max** metric (`applewatch_vo2max`). Everything else Health Auto Export can export (steps, sleep, blood pressure, ECG, etc.) is deliberately unparsed — Oura already covers sleep/HRV/readiness deeply, and re-importing that from Apple Health would be redundant infrastructure, not new signal. See the script's docstring for the full reasoning (`ideas.md`'s 2026-09-03 entry has the same scoping decision).

Real prefix discipline: every field is `applewatch_`-prefixed so it can never collide with an `oura_`-sourced field on the same note.

## 3. Report back
The script prints its own coverage summary (days with data vs. the real span, gap days called out explicitly — expected given Ross's wear history, not an error) and which `Daily/` notes were actually updated. Relay that directly. If a day has Apple Watch data but no existing `Daily/<date>.md` note, the script skips it and says so on stderr rather than creating a note just to hold watch data — mention if that happened, since it means some historical workout data isn't being captured yet.

## 4. Full raw payload
Every day's raw workout + vo2max JSON lands in `Daily/.apple-health-raw/<date>.json`, deduplicated on re-run (merges by workout `id` and by `(date, qty)` for vo2max samples — re-running against an overlapping export is safe, confirmed by a real test 2026-09-03 that caught and fixed a naive-append duplication bug before this shipped).
