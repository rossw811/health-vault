#!/usr/bin/env python3
"""Import Apple Watch / Apple Health data (via the Health Auto Export iOS
app's JSON export) into Daily/*.md frontmatter, scoped deliberately narrow -
NOT a duplicate of what oura_full_sync.py already covers.

*** NOT YET RUN AGAINST REAL DATA - built 2026-09-03, flagged for later. ***
Real prerequisite before this is useful: Health Auto Export needs to be
installed on Ross's phone, granted HealthKit read permission, and used to
produce at least one real JSON export (Automations -> Export -> "Save to
File" is the simplest path for a one-off backfill; a scheduled REST API
automation is the live-sync path once this script is confirmed working
against a real export). This script was written and reviewed for schema
correctness against Health Auto Export's own documented JSON format
(https://help.healthyapps.dev/en/health-auto-export/export-format, checked
directly 2026-09-03 - metrics: {name, units, data:[{date, qty|Min/Avg/Max,
source}]}; workouts: {id, name, start, end, duration, activeEnergyBurned,
heartRate:{min,avg,max}, heartRateData:[...]}), but has NOT been exercised
against a real export file. Test against one real export before trusting
its output.

Why this is scoped narrow, not "sync everything Apple Health has":
Oura already covers sleep/HRV/readiness/stress/SpO2/resilience/VO2max
deeply (see oura_full_sync.py) - re-importing the same domains from Apple
Health would be redundant infrastructure, not new signal. The genuinely
non-overlapping value, per the 2026-09-03 scoping decision (see ideas.md):
workout-specific heart rate accuracy (a ring has known accuracy limits
during weighted/gripping exercise; a wrist-worn watch doesn't), and a
second, independent VO2max estimate to cross-check Oura's own. This script
therefore only extracts:
  - workouts[] -> name/type, start, end, duration, heart rate (min/avg/max),
    active energy burned - written with an `applewatch_` prefix so it never
    collides with any `oura_`-sourced field.
  - the `vo2_max` metric, if present, as `applewatch_vo2max` - a second
    number to sit alongside Oura's own vO2max, not to replace it.
Everything else Health Auto Export can export (steps, sleep phases, blood
pressure, ECG, state of mind, cycle tracking, etc.) is deliberately left
unparsed this pass - extend `WORKOUT_FIELDS`/`parse_export` if a real need
for one of those surfaces later, don't just turn this into an
everything-importer by default.

Real, known gap in the underlying data, not a script bug: Ross didn't wear
the watch day-to-day for a real stretch, and more recently has mostly worn
it only overnight (as a sleep/alarm device) rather than during workouts -
so a real historical export will likely show three eras (heavy day-to-day
use with real workout data -> a gap with nothing -> sleep-only, still no
workout data) rather than one continuous stream. This script reports that
honestly (see the coverage summary at the end of a run) instead of treating
a gap as an error or silently back-filling nothing without saying so.

Two outputs per run, same shape as oura_full_sync.py:
1. Daily/.apple-health-raw/<date>.json - the raw workout + vo2max payload
   for that day, unmodified, for anything this pass didn't parse into
   frontmatter.
2. Daily/<date>.md frontmatter - only the `applewatch_*` fields below,
   idempotent (a field is only rewritten if the new value actually
   differs), matching oura_full_sync.py's own merge discipline.

Usage:
    python scripts/apple_health_full_sync.py --export path/to/export.json
    python scripts/apple_health_full_sync.py --export path/to/export-folder/ --backfill
        (--backfill is semantic only here - same parsing logic either way,
        just signals "this is a real historical bulk import, expect gaps"
        rather than "this is today's incremental update")
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parent.parent
DAILY_DIR = VAULT_ROOT / "Daily"
RAW_DIR = DAILY_DIR / ".apple-health-raw"

# Health Auto Export's documented date format: "yyyy-MM-dd HH:mm:ss Z"
DATE_FORMATS = ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d")


def parse_date(s: str) -> datetime | None:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def day_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def load_export_files(export_path: Path) -> list[Path]:
    if export_path.is_dir():
        files = sorted(export_path.glob("*.json"))
        if not files:
            print(f"No .json files found in {export_path}", file=sys.stderr)
        return files
    return [export_path]


def parse_export(path: Path) -> dict:
    """Returns {day_str: {"workouts": [...], "vo2max": float|None, "raw": {...}}}."""
    with path.open(encoding="utf-8") as f:
        payload = json.load(f)

    data = payload.get("data", payload)  # tolerate a bare {"metrics":...} export too
    by_day: dict[str, dict] = defaultdict(lambda: {"workouts": [], "vo2max": None, "raw": {"workouts": [], "vo2max_samples": []}})

    for workout in data.get("workouts", []):
        start = parse_date(workout.get("start", ""))
        if start is None:
            print(f"  skipping workout with unparseable start date: {workout.get('start')!r}", file=sys.stderr)
            continue
        d = day_str(start)
        hr = workout.get("heartRate") or {}
        active_energy = workout.get("activeEnergyBurned") or workout.get("activeEnergy")
        record = {
            "type": workout.get("name"),
            "start": workout.get("start"),
            "end": workout.get("end"),
            "duration_min": round(workout["duration"] / 60, 1) if workout.get("duration") else None,
            "hr_min": hr.get("min") or hr.get("Min"),
            "hr_avg": hr.get("avg") or hr.get("Avg"),
            "hr_max": hr.get("max") or hr.get("Max"),
            "active_kcal": active_energy.get("qty") if isinstance(active_energy, dict) else active_energy,
        }
        by_day[d]["workouts"].append(record)
        by_day[d]["raw"]["workouts"].append(workout)

    for metric in data.get("metrics", []):
        if metric.get("name") != "vo2_max":
            continue
        for point in metric.get("data", []):
            dt = parse_date(point.get("date", ""))
            if dt is None:
                continue
            d = day_str(dt)
            qty = point.get("qty")
            if qty is not None:
                by_day[d]["vo2max"] = qty
                by_day[d]["raw"]["vo2max_samples"].append(point)

    return dict(by_day)


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def upsert_daily_note(d: str, day_data: dict) -> list[str]:
    workouts = day_data["workouts"]
    updates: dict[str, object] = {}
    if workouts:
        # Multiple workouts in one day: use the one with the most complete
        # HR data for the scalar frontmatter fields (real signal, not just
        # "first") - full list still preserved in the raw archive either way.
        primary = max(workouts, key=lambda w: w["hr_avg"] is not None)
        updates["applewatch_workout_type"] = primary["type"]
        updates["applewatch_workout_duration_min"] = primary["duration_min"]
        updates["applewatch_workout_hr_avg"] = primary["hr_avg"]
        updates["applewatch_workout_hr_max"] = primary["hr_max"]
        updates["applewatch_workout_active_kcal"] = primary["active_kcal"]
        if len(workouts) > 1:
            updates["applewatch_workout_count"] = len(workouts)
    if day_data["vo2max"] is not None:
        updates["applewatch_vo2max"] = day_data["vo2max"]

    if not updates:
        return []

    path = DAILY_DIR / f"{d}.md"
    if not path.exists():
        # Don't invent a Daily note just to hold Apple Watch data for a day
        # Oura/the vault has no other record of - that's a real signal
        # (watch-only day) worth knowing, not silently discarding.
        print(f"  {d}: has applewatch data but no Daily/{d}.md exists - skipped (not creating a note for watch-only days)", file=sys.stderr)
        return []

    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        return []

    fm_block = m.group(1)
    changed = []
    for field, value in updates.items():
        if value is None:
            continue
        pattern = re.compile(rf"^({re.escape(field)}:\s*).*$", re.MULTILINE)
        if pattern.search(fm_block):
            new_fm_block, n = pattern.subn(lambda mm: f"{mm.group(1)}{value}", fm_block, count=1)
            if new_fm_block != fm_block:
                fm_block = new_fm_block
                changed.append(field)
        else:
            fm_block = fm_block + f"\n{field}: {value}"
            changed.append(field)

    if changed:
        path.write_text(f"---\n{fm_block}\n---\n" + text[m.end():], encoding="utf-8")
    return changed


def write_raw(d: str, day_data: dict) -> None:
    """Idempotent merge, not append-only - re-running against the same or an
    overlapping export must not duplicate entries (real bug caught in
    testing 2026-09-03: a naive .extend() doubled both lists on a re-run)."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / f"{d}.json"
    existing = {}
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}

    workouts = {w.get("id") or json.dumps(w, sort_keys=True): w
                for w in existing.get("workouts", []) + day_data["raw"]["workouts"]}
    vo2_samples = {(s.get("date"), s.get("qty")): s
                   for s in existing.get("vo2max_samples", []) + day_data["raw"]["vo2max_samples"]}

    existing["workouts"] = list(workouts.values())
    existing["vo2max_samples"] = list(vo2_samples.values())
    out_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--export", required=True, help="Path to a Health Auto Export JSON file, or a folder of them")
    parser.add_argument("--backfill", action="store_true", help="Semantic flag only - marks this as a historical bulk import (gaps expected), same parsing logic as a normal run")
    args = parser.parse_args()

    export_path = Path(args.export)
    if not export_path.exists():
        print(f"Not found: {export_path}", file=sys.stderr)
        return 1

    files = load_export_files(export_path)
    if not files:
        return 1

    all_days: dict[str, dict] = {}
    for f in files:
        print(f"Parsing {f.name}...")
        parsed = parse_export(f)
        for d, day_data in parsed.items():
            if d not in all_days:
                all_days[d] = day_data
            else:
                all_days[d]["workouts"].extend(day_data["workouts"])
                all_days[d]["raw"]["workouts"].extend(day_data["raw"]["workouts"])
                if day_data["vo2max"] is not None:
                    all_days[d]["vo2max"] = day_data["vo2max"]
                all_days[d]["raw"]["vo2max_samples"].extend(day_data["raw"]["vo2max_samples"])

    if not all_days:
        print("No workout or vo2_max data found in the export(s) given.")
        return 0

    sorted_days = sorted(all_days.keys())
    print(f"\nFound applewatch data for {len(sorted_days)} day(s): {sorted_days[0]} to {sorted_days[-1]}")

    # Real coverage report, not just a silent import - this is the "handle
    # the known wear-gap honestly" requirement from the 2026-09-03 scoping.
    first_dt = datetime.strptime(sorted_days[0], "%Y-%m-%d")
    last_dt = datetime.strptime(sorted_days[-1], "%Y-%m-%d")
    span_days = (last_dt - first_dt).days + 1
    gap_days = span_days - len(sorted_days)
    if gap_days > 0:
        print(f"Coverage: {len(sorted_days)}/{span_days} days in that span actually have applewatch data ({gap_days} gap days) - expected, given the known day-to-day wear gap. Not an error.")

    updated_count = 0
    for d in sorted_days:
        write_raw(d, all_days[d])
        changed = upsert_daily_note(d, all_days[d])
        if changed:
            updated_count += 1
            print(f"  {d}: updated {', '.join(changed)}")

    print(f"\nDone. {updated_count}/{len(sorted_days)} days had a matching Daily/ note updated.")
    print(f"Raw payloads written to {RAW_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
