#!/usr/bin/env python3
"""One-time correction pass.

@daveremy/oura-mcp always queries start_date == end_date == <day> for every
endpoint. Oura's daily_sleep/daily_readiness/daily_stress/daily_spo2 endpoints
tolerate that (inclusive range), but sleep, daily_activity, workout, and
session require end_date > start_date - a same-day query silently returns
zero results. That bug left average_hrv, all sleep-stage/efficiency/latency
fields, all activity/steps fields, and every workouts/sessions list wrongly
recorded as TBD/empty across the entire vault history.

This script queries the real Oura API directly (one range call per endpoint,
not per-day) and patches only fields that are currently TBD/empty in each
Daily/*.md - everything else in each note (active_protocols, checklists,
prose) is left untouched.
"""
import contextlib
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parent.parent
DAILY_DIR = VAULT_ROOT / "Daily"
ENV_PATH = VAULT_ROOT / ".env"
BASE = "https://api.ouraring.com/v2/usercollection"


def load_token():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("OURA_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("OURA_TOKEN not found in .env")


TOKEN = load_token()


def api_get_range(endpoint, start, end):
    """Fetch a full date range, following next_token pagination."""
    out = []
    next_token = None
    while True:
        url = f"{BASE}/{endpoint}?start_date={start}&end_date={end}"
        if next_token:
            url += f"&next_token={next_token}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read())
        out.extend(payload.get("data", []))
        next_token = payload.get("next_token")
        if not next_token:
            break
    return out


def dur_min(entry):
    s = datetime.fromisoformat(entry["start_datetime"])
    e = datetime.fromisoformat(entry["end_datetime"])
    return round((e - s).total_seconds() / 60, 1)


def fmt_workouts(workouts):
    items = [
        f"{{type: {w.get('activity', 'unknown')}, duration_min: {dur_min(w)}, intensity: {w.get('intensity', 'TBD')}}}"
        for w in workouts
    ]
    return "[" + ", ".join(items) + "]"


def fmt_sessions(sessions):
    items = [
        f"{{type: {s.get('type', 'unknown')}, duration_min: {dur_min(s)}}}"
        for s in sessions
    ]
    return "[" + ", ".join(items) + "]"


def patch_field(text, field, value, force=False):
    """Replace a frontmatter field's value if it's currently TBD/[] (or always, if force)."""
    if force:
        pattern = re.compile(rf"^({re.escape(field)}:\s*).*$", re.MULTILINE)
    else:
        pattern = re.compile(rf"^({re.escape(field)}:\s*)(TBD|\[\])\s*$", re.MULTILINE)
    if not pattern.search(text):
        return text, False
    return pattern.sub(lambda m: f"{m.group(1)}{value}", text, count=1), True


def process_file(path, sleep_by_day, activity_by_day, workouts_by_day, sessions_by_day):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return None
    day_match = re.search(r"^date:\s*(\S+)", m.group(1), re.MULTILINE)
    if not day_match:
        return None
    day_str = day_match.group(1)
    try:
        date.fromisoformat(day_str)
    except ValueError:
        return None

    sleep = sleep_by_day.get(day_str)
    activity = activity_by_day.get(day_str)
    workouts = workouts_by_day.get(day_str, [])
    sessions = sessions_by_day.get(day_str, [])

    changed_fields = []
    new_text = text

    if sleep:
        mapping = {
            "average_hrv": sleep.get("average_hrv"),
            "sleep_total_hours": round(sleep["total_sleep_duration"] / 3600, 2)
            if sleep.get("total_sleep_duration") else None,
            "sleep_efficiency": sleep.get("efficiency"),
            "sleep_latency_min": round(sleep["latency"] / 60, 1)
            if sleep.get("latency") is not None else None,
            "sleep_rem_hours": round(sleep["rem_sleep_duration"] / 3600, 2)
            if sleep.get("rem_sleep_duration") else None,
            "sleep_deep_hours": round(sleep["deep_sleep_duration"] / 3600, 2)
            if sleep.get("deep_sleep_duration") else None,
            "sleep_light_hours": round(sleep["light_sleep_duration"] / 3600, 2)
            if sleep.get("light_sleep_duration") else None,
        }
        for field, value in mapping.items():
            if value is None:
                continue
            new_text, did = patch_field(new_text, field, value)
            if did:
                changed_fields.append(field)

        if sleep.get("lowest_heart_rate") is not None:
            new_text, did = patch_field(new_text, "resting_hr", sleep["lowest_heart_rate"], force=True)
            if did:
                changed_fields.append("resting_hr (standardized to Oura lowest_heart_rate)")

    if activity:
        total_active_min = round(
            (activity.get("low_activity_time", 0) or 0)
            + (activity.get("medium_activity_time", 0) or 0)
            + (activity.get("high_activity_time", 0) or 0),
            0,
        ) / 60
        inactivity_min = round((activity.get("sedentary_time", 0) or 0) / 60, 1)
        mapping = {
            "activity_score": activity.get("score"),
            "steps": activity.get("steps"),
            "calories_active": activity.get("active_calories"),
            "activity_total_min": round(total_active_min, 1),
            "inactivity_min": inactivity_min,
        }
        for field, value in mapping.items():
            if value is None:
                continue
            new_text, did = patch_field(new_text, field, value)
            if did:
                changed_fields.append(field)

    if workouts:
        new_text, did = patch_field(new_text, "workouts", fmt_workouts(workouts))
        if did:
            changed_fields.append(f"workouts ({len(workouts)})")

    if sessions:
        new_text, did = patch_field(new_text, "sessions", fmt_sessions(sessions))
        if did:
            changed_fields.append(f"sessions ({len(sessions)})")

    if changed_fields:
        note = (
            "\n\n**[oura-sync bugfix pass]** Recovered previously-TBD/empty fields "
            f"({', '.join(changed_fields)}) after fixing an `@daveremy/oura-mcp` query "
            "bug: the sleep/daily_activity/workout/session endpoints require "
            "end_date > start_date, but the MCP tool always queried a single day and "
            "silently got nothing back. Data pulled directly from the Oura API "
            "(scripts/oura_backfill_fix.py) with a corrected date range.\n"
        )
        new_text = new_text.rstrip("\n") + "\n" + note
        path.write_text(new_text, encoding="utf-8")

    return day_str, changed_fields


def index_by_day(records):
    out = {}
    for r in records:
        out.setdefault(r["day"], r)
    return out


def group_by_day(records):
    out = {}
    for r in records:
        out.setdefault(r["day"], []).append(r)
    return out


def main():
    files = sorted(DAILY_DIR.glob("*.md"))
    if not files:
        print("No Daily notes found.")
        return

    dates = []
    for path in files:
        m = re.match(r"^---\n(.*?)\n---\n", path.read_text(encoding="utf-8"), re.DOTALL)
        if not m:
            continue
        dm = re.search(r"^date:\s*(\S+)", m.group(1), re.MULTILINE)
        if dm:
            with contextlib.suppress(ValueError):
                dates.append(date.fromisoformat(dm.group(1)))
    if not dates:
        print("No valid dated notes found.")
        return

    start = min(dates).isoformat()
    end = (max(dates) + timedelta(days=1)).isoformat()
    print(f"Fetching full-range data: {start} to {end} (exclusive-safe)")

    try:
        sleep_records = api_get_range("sleep", start, end)
        activity_records = api_get_range("daily_activity", start, end)
        workout_records = api_get_range("workout", start, end)
        session_records = api_get_range("session", start, end)
    except urllib.error.HTTPError as e:
        print(f"Oura API error: {e.code} {e.read().decode(errors='replace')}")
        sys.exit(1)

    print(f"Fetched: {len(sleep_records)} sleep periods, {len(activity_records)} activity days, "
          f"{len(workout_records)} workouts, {len(session_records)} sessions")

    sleep_by_day = index_by_day(sleep_records)
    activity_by_day = index_by_day(activity_records)
    workouts_by_day = group_by_day(workout_records)
    sessions_by_day = group_by_day(session_records)

    results = []
    errors = []
    for path in files:
        try:
            r = process_file(path, sleep_by_day, activity_by_day, workouts_by_day, sessions_by_day)
            if r:
                results.append(r)
        except Exception as e:
            errors.append((path.name, str(e)))

    fixed = [r for r in results if r[1]]
    print(f"\nProcessed {len(results)} daily notes, {len(fixed)} had fields recovered.")
    total_workouts = sum(1 for r in fixed if any("workouts" in f for f in r[1]))
    total_sessions = sum(1 for r in fixed if any("sessions" in f for f in r[1]))
    print(f"Dates with workouts recovered: {total_workouts}")
    print(f"Dates with sessions recovered: {total_sessions}")
    for day_str, fields in fixed:
        print(f"  {day_str}: {', '.join(fields)}")
    if errors:
        print(f"\n{len(errors)} errors:")
        for name, err in errors:
            print(f"  {name}: {err}")


if __name__ == "__main__":
    main()
