#!/usr/bin/env python3
"""Pull literally everything the Oura API exposes - every endpoint, every raw
field, no curation - and store it alongside an expanded (but still curated,
for readability) Daily/*.md frontmatter summary.

Why this exists instead of relying on the `oura` MCP server
(`@daveremy/oura-mcp`, see scripts/run-oura-mcp.mjs): that wrapper (1) always
queries start_date == end_date == <day>, which Oura's sleep/daily_activity/
workout/session endpoints silently return empty for (see
scripts/oura_backfill_fix.py's docstring for the original diagnosis), and
(2) exposes only 10 of the ~17 real usercollection endpoints - it has no tool
at all for daily_resilience, daily_cardiovascular_age, vO2_max,
rest_mode_period, ring_configuration, tag, enhanced_tag, sleep_time, or
personal_info. Both are structural limits of the third-party package, not
something a smarter MCP call can work around - so this script talks to
https://api.ouraring.com/v2/usercollection directly, the same approach
oura_backfill_fix.py already validated for the four originally-buggy
endpoints.

Two outputs per run:
1. Daily/.oura-raw/<date>.json - the complete raw payload for that day,
   every endpoint, every field, including the time-series arrays (heart
   rate, HRV, MET, movement, sleep-phase strings) that are too large to put
   in frontmatter. This is the actual "no gaps" guarantee - it's Oura's own
   JSON, unmodified.
2. Daily/<date>.md frontmatter - expanded with every summary-level scalar
   field that was previously missing (resilience, cardiovascular age, the
   sleep_regularity readiness contributor, full activity contributor
   breakdown, sleep_time recommendation, vO2max, logged tags), for the
   fields genuinely usable in analysis/dashboarding. Time-series data is
   deliberately NOT duplicated into frontmatter - see Daily/.oura-raw/ for
   that.

Account-level (not per-day) data - personal_info, ring_configuration - is
written once to Daily/.oura-raw/_account.json, refreshed every run since it
rarely changes but costs nothing extra to re-fetch.
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date as date_cls
from datetime import datetime, timedelta, timezone
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parent.parent
DAILY_DIR = VAULT_ROOT / "Daily"
RAW_DIR = DAILY_DIR / ".oura-raw"
ENV_PATH = VAULT_ROOT / ".env"
BASE = "https://api.ouraring.com/v2/usercollection"

# Endpoints keyed by a "day" field, one record per day (safe to index_by_day).
DAY_KEYED_ENDPOINTS = [
    "daily_activity",
    "daily_readiness",
    "daily_sleep",
    "daily_spo2",
    "daily_stress",
    "daily_resilience",
    "daily_cardiovascular_age",
    "sleep_time",
    "vO2_max",
    "tag",
]
# Endpoints with multiple records per day (group_by_day).
MULTI_PER_DAY_ENDPOINTS = ["sleep", "workout", "session"]


def load_token():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("OURA_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("OURA_TOKEN not found in .env")


TOKEN = load_token()


def api_get(url):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def api_get_range(endpoint, start, end):
    """Fetch a full date range, following next_token pagination.
    end must be strictly after start for the range to actually contain
    `end`'s own day - callers should pass end = last_wanted_day + 1."""
    out = []
    next_token = None
    while True:
        url = f"{BASE}/{endpoint}?start_date={start}&end_date={end}"
        if next_token:
            url += f"&next_token={next_token}"
        payload = api_get(url)
        out.extend(payload.get("data", []))
        next_token = payload.get("next_token")
        if not next_token:
            break
    return out


def api_get_heartrate(start_dt, end_dt):
    out = []
    next_token = None
    start_q = urllib.parse.quote(start_dt, safe="")
    end_q = urllib.parse.quote(end_dt, safe="")
    while True:
        url = f"{BASE}/heartrate?start_datetime={start_q}&end_datetime={end_q}"
        if next_token:
            url += f"&next_token={next_token}"
        payload = api_get(url)
        out.extend(payload.get("data", []))
        next_token = payload.get("next_token")
        if not next_token:
            break
    return out


def index_by_day(records):
    out = {}
    for r in records:
        out.setdefault(r["day"], r)
    return out


def group_by_day(records, day_field="day"):
    out = {}
    for r in records:
        out.setdefault(r[day_field], []).append(r)
    return out


def fetch_account_info():
    personal_info = api_get(f"{BASE}/personal_info")
    try:
        ring_configs = api_get(f"{BASE}/ring_configuration").get("data", [])
    except urllib.error.HTTPError:
        ring_configs = []
    return {"personal_info": personal_info, "ring_configuration": ring_configs}


def fetch_all(start, end_exclusive):
    """Fetch every endpoint for [start, end_exclusive). Returns a dict of
    endpoint -> raw records list (or dict for personal_info)."""
    data = {}
    for ep in DAY_KEYED_ENDPOINTS:
        try:
            data[ep] = api_get_range(ep, start, end_exclusive)
        except urllib.error.HTTPError as e:
            print(f"  WARNING: {ep} fetch failed ({e.code}) - treating as no data", file=sys.stderr)
            data[ep] = []
    for ep in MULTI_PER_DAY_ENDPOINTS:
        try:
            data[ep] = api_get_range(ep, start, end_exclusive)
        except urllib.error.HTTPError as e:
            print(f"  WARNING: {ep} fetch failed ({e.code}) - treating as no data", file=sys.stderr)
            data[ep] = []
    try:
        data["rest_mode_period"] = api_get_range("rest_mode_period", start, end_exclusive)
    except urllib.error.HTTPError:
        data["rest_mode_period"] = []
    try:
        data["enhanced_tag"] = api_get_range("enhanced_tag", start, end_exclusive)
    except urllib.error.HTTPError:
        data["enhanced_tag"] = []

    # Continuous heart rate stream - bucket each sample by its own timestamp's day.
    start_dt = f"{start}T00:00:00+00:00"
    end_dt = f"{end_exclusive}T00:00:00+00:00"
    try:
        hr_samples = api_get_heartrate(start_dt, end_dt)
    except urllib.error.HTTPError as e:
        print(f"  WARNING: heartrate fetch failed ({e.code})", file=sys.stderr)
        hr_samples = []
    hr_by_day = {}
    for s in hr_samples:
        ts = s.get("timestamp")
        if not ts:
            continue
        day = ts[:10]
        hr_by_day.setdefault(day, []).append(s)
    data["heart_rate_samples_by_day"] = hr_by_day

    return data


def write_raw_json(day_str, data, sleep_by_day, activity_by_day, resilience_by_day,
                    readiness_by_day, cardio_by_day, sleep_time_by_day, vo2_by_day,
                    tag_by_day, workouts_by_day, sessions_by_day, sleep_periods_by_day,
                    enhanced_tags_by_start_day, rest_mode_by_day, hr_by_day):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "date": day_str,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "daily_activity": activity_by_day.get(day_str),
        "daily_readiness": readiness_by_day.get(day_str),
        "daily_sleep": sleep_by_day.get(day_str),
        "daily_resilience": resilience_by_day.get(day_str),
        "daily_cardiovascular_age": cardio_by_day.get(day_str),
        "sleep_time": sleep_time_by_day.get(day_str),
        "vO2_max": vo2_by_day.get(day_str),
        "tag": tag_by_day.get(day_str),
        "sleep_periods": sleep_periods_by_day.get(day_str, []),
        "workouts": workouts_by_day.get(day_str, []),
        "sessions": sessions_by_day.get(day_str, []),
        "enhanced_tags_starting": enhanced_tags_by_start_day.get(day_str, []),
        "rest_mode_periods": rest_mode_by_day.get(day_str, []),
        "heart_rate_samples": hr_by_day.get(day_str, []),
    }
    (RAW_DIR / f"{day_str}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def fmt_list(items, field_map):
    out = []
    for it in items:
        parts = {k: it.get(src) for k, src in field_map.items()}
        out.append(parts)
    return json.dumps(out)


def build_frontmatter_updates(day_str, activity_by_day, readiness_by_day, sleep_by_day,
                               resilience_by_day, cardio_by_day, sleep_time_by_day,
                               vo2_by_day, workouts_by_day, sessions_by_day,
                               enhanced_tags_by_start_day, sleep_periods_by_day):
    """Return {field_name: value} for every scalar field with real data today.
    Only includes fields worth surfacing in frontmatter - time series stay
    in the raw JSON store (see write_raw_json)."""
    updates = {}

    readiness = readiness_by_day.get(day_str)
    if readiness:
        c = readiness.get("contributors", {}) or {}
        updates.update({
            "readiness_score": readiness.get("score"),
            "readiness_hrv_balance": c.get("hrv_balance"),
            "readiness_resting_hr": c.get("resting_heart_rate"),
            "readiness_body_temp_deviation": readiness.get("temperature_deviation"),
            "readiness_temp_trend_deviation": readiness.get("temperature_trend_deviation"),
            "readiness_recovery_index": c.get("recovery_index"),
            "readiness_sleep_balance": c.get("sleep_balance"),
            "readiness_activity_balance": c.get("activity_balance"),
            "readiness_previous_day_activity": c.get("previous_day_activity"),
            "readiness_previous_night": c.get("previous_night"),
            "readiness_sleep_regularity": c.get("sleep_regularity"),
        })

    sleep_daily = sleep_by_day.get(day_str)
    if sleep_daily:
        c = sleep_daily.get("contributors", {}) or {}
        updates.update({
            "sleep_score": sleep_daily.get("score"),
            "sleep_contrib_deep": c.get("deep_sleep"),
            "sleep_contrib_efficiency": c.get("efficiency"),
            "sleep_contrib_latency": c.get("latency"),
            "sleep_contrib_rem": c.get("rem_sleep"),
            "sleep_contrib_restfulness": c.get("restfulness"),
            "sleep_contrib_timing": c.get("timing"),
            "sleep_contrib_total": c.get("total_sleep"),
        })

    # Primary sleep period for the day (prefer long_sleep over naps if multiple).
    periods = sleep_periods_by_day.get(day_str, [])
    primary = next((p for p in periods if p.get("type") == "long_sleep"), periods[0] if periods else None)
    if primary:
        updates.update({
            "sleep_total_hours": round(primary["total_sleep_duration"] / 3600, 2)
            if primary.get("total_sleep_duration") else None,
            "sleep_efficiency": primary.get("efficiency"),
            "sleep_latency_min": round(primary["latency"] / 60, 1) if primary.get("latency") is not None else None,
            "sleep_rem_hours": round(primary["rem_sleep_duration"] / 3600, 2)
            if primary.get("rem_sleep_duration") else None,
            "sleep_deep_hours": round(primary["deep_sleep_duration"] / 3600, 2)
            if primary.get("deep_sleep_duration") else None,
            "sleep_light_hours": round(primary["light_sleep_duration"] / 3600, 2)
            if primary.get("light_sleep_duration") else None,
            "sleep_time_in_bed_hours": round(primary["time_in_bed"] / 3600, 2)
            if primary.get("time_in_bed") else None,
            "sleep_bedtime_start": primary.get("bedtime_start"),
            "sleep_bedtime_end": primary.get("bedtime_end"),
            "sleep_avg_breath": primary.get("average_breath"),
            "sleep_restless_periods": primary.get("restless_periods"),
            "average_hrv": primary.get("average_hrv"),
            "resting_hr": primary.get("lowest_heart_rate"),
            "sleep_type": primary.get("type"),
            "sleep_algorithm_version": primary.get("sleep_algorithm_version"),
            "sleep_awake_time_min": round(primary["awake_time"] / 60, 1) if primary.get("awake_time") else None,
        })
        if len(periods) > 1:
            updates["sleep_extra_periods_logged"] = len(periods) - 1

    activity = activity_by_day.get(day_str)
    if activity:
        c = activity.get("contributors", {}) or {}
        total_active_min = round(
            (activity.get("low_activity_time", 0) or 0)
            + (activity.get("medium_activity_time", 0) or 0)
            + (activity.get("high_activity_time", 0) or 0),
            0,
        ) / 60
        updates.update({
            "activity_score": activity.get("score"),
            "steps": activity.get("steps"),
            "calories_active": activity.get("active_calories"),
            "activity_total_min": round(total_active_min, 1),
            "inactivity_min": round((activity.get("sedentary_time", 0) or 0) / 60, 1),
            "activity_contrib_meet_daily_targets": c.get("meet_daily_targets"),
            "activity_contrib_move_every_hour": c.get("move_every_hour"),
            "activity_contrib_recovery_time": c.get("recovery_time"),
            "activity_contrib_stay_active": c.get("stay_active"),
            "activity_contrib_training_frequency": c.get("training_frequency"),
            "activity_contrib_training_volume": c.get("training_volume"),
            "activity_equivalent_walking_distance_m": activity.get("equivalent_walking_distance"),
            "activity_non_wear_min": round((activity.get("non_wear_time", 0) or 0) / 60, 1),
            "activity_resting_min": round((activity.get("resting_time", 0) or 0) / 60, 1),
            "activity_high_met_min": round((activity.get("high_activity_time", 0) or 0) / 60, 1),
            "activity_medium_met_min": round((activity.get("medium_activity_time", 0) or 0) / 60, 1),
            "activity_low_met_min": round((activity.get("low_activity_time", 0) or 0) / 60, 1),
            "activity_target_calories": activity.get("target_calories"),
            "activity_total_calories": activity.get("total_calories"),
            "activity_target_meters": activity.get("target_meters"),
            "activity_meters_to_target": activity.get("meters_to_target"),
            "activity_inactivity_alerts": activity.get("inactivity_alerts"),
        })

    resilience = resilience_by_day.get(day_str)
    if resilience:
        c = resilience.get("contributors", {}) or {}
        updates.update({
            "resilience_level": resilience.get("level"),
            "resilience_sleep_recovery": c.get("sleep_recovery"),
            "resilience_daytime_recovery": c.get("daytime_recovery"),
            "resilience_stress": c.get("stress"),
        })

    cardio = cardio_by_day.get(day_str)
    if cardio:
        updates.update({
            "cardio_vascular_age": cardio.get("vascular_age"),
            "cardio_pulse_wave_velocity": cardio.get("pulse_wave_velocity"),
        })

    sleep_time_rec = sleep_time_by_day.get(day_str)
    if sleep_time_rec:
        updates.update({
            "sleep_time_recommendation": sleep_time_rec.get("recommendation"),
            "sleep_time_optimal_bedtime": sleep_time_rec.get("optimal_bedtime"),
            "sleep_time_status": sleep_time_rec.get("status"),
        })

    vo2 = vo2_by_day.get(day_str)
    if vo2 and vo2.get("vo2_max"):
        updates["vo2_max"] = vo2.get("vo2_max")

    workouts = workouts_by_day.get(day_str, [])
    if workouts:
        updates["workouts"] = fmt_list(workouts, {
            "type": "activity", "distance_m": "distance", "calories": "calories",
            "intensity": "intensity", "label": "label", "source": "source",
        })

    sessions = sessions_by_day.get(day_str, [])
    if sessions:
        updates["sessions"] = fmt_list(sessions, {
            "type": "type", "avg_heart_rate": "average_heart_rate",
            "avg_hrv": "average_hrv", "mood": "mood", "motion_count": "motion_count",
        })

    tags_today = enhanced_tags_by_start_day.get(day_str, [])
    if tags_today:
        updates["oura_tags_logged"] = json.dumps([t.get("tag_type_code") for t in tags_today])

    return updates


FULL_FRONTMATTER_TEMPLATE = """---
date: {date}
type: daily-log
readiness_score: TBD
readiness_hrv_balance: TBD
readiness_resting_hr: TBD
readiness_body_temp_deviation: TBD
readiness_temp_trend_deviation: TBD
readiness_recovery_index: TBD
readiness_sleep_balance: TBD
readiness_activity_balance: TBD
readiness_previous_day_activity: TBD
readiness_previous_night: TBD
readiness_sleep_regularity: TBD
sleep_score: TBD
sleep_contrib_deep: TBD
sleep_contrib_efficiency: TBD
sleep_contrib_latency: TBD
sleep_contrib_rem: TBD
sleep_contrib_restfulness: TBD
sleep_contrib_timing: TBD
sleep_contrib_total: TBD
sleep_total_hours: TBD
sleep_efficiency: TBD
sleep_latency_min: TBD
sleep_rem_hours: TBD
sleep_deep_hours: TBD
sleep_light_hours: TBD
sleep_time_in_bed_hours: TBD
sleep_bedtime_start: TBD
sleep_bedtime_end: TBD
sleep_avg_breath: TBD
sleep_restless_periods: TBD
sleep_type: TBD
sleep_algorithm_version: TBD
sleep_awake_time_min: TBD
sleep_extra_periods_logged: 0
sleep_time_recommendation: TBD
sleep_time_optimal_bedtime: TBD
sleep_time_status: TBD
average_hrv: TBD
resting_hr: TBD
activity_score: TBD
steps: TBD
calories_active: TBD
activity_total_min: TBD
inactivity_min: TBD
activity_contrib_meet_daily_targets: TBD
activity_contrib_move_every_hour: TBD
activity_contrib_recovery_time: TBD
activity_contrib_stay_active: TBD
activity_contrib_training_frequency: TBD
activity_contrib_training_volume: TBD
activity_equivalent_walking_distance_m: TBD
activity_non_wear_min: TBD
activity_resting_min: TBD
activity_high_met_min: TBD
activity_medium_met_min: TBD
activity_low_met_min: TBD
activity_target_calories: TBD
activity_total_calories: TBD
activity_target_meters: TBD
activity_meters_to_target: TBD
activity_inactivity_alerts: TBD
resilience_level: TBD
resilience_sleep_recovery: TBD
resilience_daytime_recovery: TBD
resilience_stress: TBD
cardio_vascular_age: TBD
cardio_pulse_wave_velocity: TBD
vo2_max: TBD
workouts: []
stress_summary: TBD
spo2_avg: TBD
sessions: []
oura_tags_logged: []
active_protocols: []
training_load_hrs: 0
tags: [biometrics, health-tracking]
---

# {date}
"""


def upsert_daily_note(day_str, updates, stress_by_day, spo2_by_day):
    path = DAILY_DIR / f"{day_str}.md"
    stress = stress_by_day.get(day_str)
    if stress:
        updates["stress_summary"] = stress.get("day_summary")
    spo2 = spo2_by_day.get(day_str)
    if spo2:
        pct = (spo2.get("spo2_percentage") or {}).get("average")
        if pct is not None:
            updates["spo2_avg"] = pct

    if not path.exists():
        DAILY_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(FULL_FRONTMATTER_TEMPLATE.format(date=day_str), encoding="utf-8")

    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return []

    changed = []
    fm_block = m.group(1)
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
            # New field not in this note's existing frontmatter (older note
            # predating this schema expansion) - append it.
            fm_block = fm_block + f"\n{field}: {value}"
            changed.append(field)

    if changed:
        new_text = f"---\n{fm_block}\n---\n" + text[m.end():]
        path.write_text(new_text, encoding="utf-8")
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="Single day, YYYY-MM-DD")
    parser.add_argument("--start", help="Range start, YYYY-MM-DD")
    parser.add_argument("--end", help="Range end (inclusive), YYYY-MM-DD")
    parser.add_argument("--backfill", action="store_true",
                         help="Full history: from the ring's set_up_at date through yesterday")
    args = parser.parse_args()

    account = fetch_account_info()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "_account.json").write_text(json.dumps(account, indent=2), encoding="utf-8")
    ring_configs = account.get("ring_configuration") or []

    if args.backfill:
        set_up = ring_configs[0].get("set_up_at") if ring_configs else None
        start = set_up[:10] if set_up else "2020-01-01"
        end_incl = (date_cls.today() - timedelta(days=1)).isoformat()
    elif args.date:
        start = end_incl = args.date
    elif args.start and args.end:
        start, end_incl = args.start, args.end
    else:
        start = end_incl = date_cls.today().isoformat()

    end_exclusive = (date_cls.fromisoformat(end_incl) + timedelta(days=1)).isoformat()
    print(f"Fetching Oura data: {start} through {end_incl} (inclusive)")

    data = fetch_all(start, end_exclusive)

    activity_by_day = index_by_day(data["daily_activity"])
    readiness_by_day = index_by_day(data["daily_readiness"])
    sleep_by_day = index_by_day(data["daily_sleep"])
    resilience_by_day = index_by_day(data["daily_resilience"])
    cardio_by_day = index_by_day(data["daily_cardiovascular_age"])
    sleep_time_by_day = index_by_day(data["sleep_time"])
    vo2_by_day = index_by_day(data["vO2_max"])
    tag_by_day = index_by_day(data["tag"])
    stress_by_day = index_by_day(data.get("daily_stress", []))
    spo2_by_day = index_by_day(data.get("daily_spo2", []))

    sleep_periods_by_day = group_by_day(data["sleep"])
    workouts_by_day = group_by_day(data["workout"])
    sessions_by_day = group_by_day(data["session"])
    rest_mode_by_day = group_by_day(data["rest_mode_period"], day_field="start_day") if data["rest_mode_period"] else {}
    enhanced_tags_by_start_day = group_by_day(data["enhanced_tag"], day_field="start_day") if data["enhanced_tag"] else {}
    hr_by_day = data["heart_rate_samples_by_day"]

    d = date_cls.fromisoformat(start)
    end_d = date_cls.fromisoformat(end_incl)
    all_days = []
    while d <= end_d:
        all_days.append(d.isoformat())
        d += timedelta(days=1)

    print(f"Days to process: {len(all_days)}")
    days_with_data = 0
    for day_str in all_days:
        write_raw_json(
            day_str, data, sleep_by_day, activity_by_day, resilience_by_day,
            readiness_by_day, cardio_by_day, sleep_time_by_day, vo2_by_day,
            tag_by_day, workouts_by_day, sessions_by_day, sleep_periods_by_day,
            enhanced_tags_by_start_day, rest_mode_by_day, hr_by_day,
        )
        updates = build_frontmatter_updates(
            day_str, activity_by_day, readiness_by_day, sleep_by_day,
            resilience_by_day, cardio_by_day, sleep_time_by_day, vo2_by_day,
            workouts_by_day, sessions_by_day, enhanced_tags_by_start_day,
            sleep_periods_by_day,
        )
        changed = upsert_daily_note(day_str, updates, stress_by_day, spo2_by_day)
        if changed:
            days_with_data += 1
            print(f"  {day_str}: updated {len(changed)} field(s)")

    print(f"\nDone. {days_with_data}/{len(all_days)} days had at least one field updated.")
    print(f"Raw JSON stored under {RAW_DIR}")


if __name__ == "__main__":
    main()
