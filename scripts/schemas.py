"""Pandera schemas for this vault's data pipelines.

Formalizes the kind of ad-hoc QC check that was hand-written once (a duration-
vs-transcript-length sanity check during the 2026-07-25 corruption incident)
into reusable, reportable validation - run this instead of writing a new
one-off script each time a "is this data actually sane" question comes up.

Validation failures are reported, not silently dropped - a script that calls
these should print/log what failed and why, not just filter bad rows away
without a trace.
"""

from __future__ import annotations

import pandera.pandas as pa
from pandera.pandas import Check, Column, DataFrameSchema

# Canonical Oura/biometric schema - matches the device-agnostic field list
# from the health-vault-toolkit plugin design (2026-07-22). Every field is
# nullable (Oura fields vary in per-day availability by design - see
# CLAUDE.md's Oura section), but where a value IS present, it must be sane.
oura_daily_schema = DataFrameSchema(
    {
        "readiness_score": Column(float, Check.in_range(0, 100), nullable=True),
        "readiness_hrv_balance": Column(float, Check.in_range(0, 150), nullable=True),
        "readiness_resting_hr": Column(float, Check.in_range(0, 150), nullable=True),
        "readiness_body_temp_deviation": Column(float, Check.in_range(-5, 5), nullable=True),
        "readiness_temp_trend_deviation": Column(float, Check.in_range(-5, 5), nullable=True),
        "readiness_recovery_index": Column(float, Check.in_range(0, 150), nullable=True),
        "readiness_sleep_balance": Column(float, Check.in_range(0, 150), nullable=True),
        "readiness_activity_balance": Column(float, Check.in_range(0, 150), nullable=True),
        "readiness_previous_day_activity": Column(float, Check.in_range(0, 150), nullable=True),
        "readiness_previous_night": Column(float, Check.in_range(0, 150), nullable=True),
        "sleep_score": Column(float, Check.in_range(0, 100), nullable=True),
        "sleep_total_hours": Column(float, Check.in_range(0, 24), nullable=True),
        "sleep_efficiency": Column(float, Check.in_range(0, 100), nullable=True),
        "sleep_latency_min": Column(float, Check.in_range(0, 300), nullable=True),
        "sleep_rem_hours": Column(float, Check.in_range(0, 12), nullable=True),
        "sleep_deep_hours": Column(float, Check.in_range(0, 12), nullable=True),
        "sleep_light_hours": Column(float, Check.in_range(0, 12), nullable=True),
        "sleep_time_in_bed_hours": Column(float, Check.in_range(0, 24), nullable=True),
        "sleep_avg_breath": Column(float, Check.in_range(5, 40), nullable=True),
        # Bound widened 2026-07-26: real backfilled data legitimately reaches
        # ~600 (this counts restless 30-sec epochs across the whole sleep
        # period, not discrete "wake-up" events - the original 500 cap was
        # miscalibrated, not a sign of bad data).
        "sleep_restless_periods": Column(float, Check.in_range(0, 800), nullable=True),
        "average_hrv": Column(float, Check.in_range(0, 300), nullable=True),
        "resting_hr": Column(float, Check.in_range(20, 220), nullable=True),
        "activity_score": Column(float, Check.in_range(0, 100), nullable=True),
        "steps": Column(float, Check.in_range(0, 100000), nullable=True),
        "calories_active": Column(float, Check.in_range(0, 10000), nullable=True),
        "activity_total_min": Column(float, Check.in_range(0, 1440), nullable=True),
        "inactivity_min": Column(float, Check.in_range(0, 1440), nullable=True),
        "spo2_avg": Column(float, Check.in_range(50, 100), nullable=True),
        "training_load_hrs": Column(float, Check.in_range(0, 24), nullable=True),
        # Added 2026-07-26 alongside scripts/oura_full_sync.py's full-field-coverage
        # pull - fields the @daveremy/oura-mcp wrapper never surfaced at all
        # (resilience, cardiovascular age, sleep_regularity, full activity
        # contributor breakdown), not just the four endpoints the same-day
        # query bug affected.
        "readiness_sleep_regularity": Column(float, Check.in_range(0, 150), nullable=True),
        "resilience_sleep_recovery": Column(float, Check.in_range(0, 100), nullable=True),
        "resilience_daytime_recovery": Column(float, Check.in_range(0, 100), nullable=True),
        "resilience_stress": Column(float, Check.in_range(0, 100), nullable=True),
        "cardio_vascular_age": Column(float, Check.in_range(0, 120), nullable=True),
        "cardio_pulse_wave_velocity": Column(float, Check.in_range(0, 20), nullable=True),
        "vo2_max": Column(float, Check.in_range(10, 90), nullable=True),
        "activity_contrib_meet_daily_targets": Column(float, Check.in_range(0, 100), nullable=True),
        "activity_contrib_move_every_hour": Column(float, Check.in_range(0, 100), nullable=True),
        "activity_contrib_recovery_time": Column(float, Check.in_range(0, 100), nullable=True),
        "activity_contrib_stay_active": Column(float, Check.in_range(0, 100), nullable=True),
        "activity_contrib_training_frequency": Column(float, Check.in_range(0, 100), nullable=True),
        "activity_contrib_training_volume": Column(float, Check.in_range(0, 100), nullable=True),
        "activity_equivalent_walking_distance_m": Column(float, Check.in_range(0, 50000), nullable=True),
        "activity_non_wear_min": Column(float, Check.in_range(0, 1440), nullable=True),
        "activity_resting_min": Column(float, Check.in_range(0, 1440), nullable=True),
        "activity_target_calories": Column(float, Check.in_range(0, 10000), nullable=True),
        "activity_total_calories": Column(float, Check.in_range(0, 10000), nullable=True),
        "activity_target_meters": Column(float, Check.in_range(0, 100000), nullable=True),
        # Legitimately negative once the day's target is exceeded (Oura
        # reports "meters past target" as a negative meters-to-target), not
        # a sign of bad data - confirmed against real backfilled values.
        "activity_meters_to_target": Column(float, Check.in_range(-100000, 100000), nullable=True),
    },
    coerce=True,
    strict=False,  # allow extra device-specific columns (e.g. oura_*, whoop_*) to pass through untouched
)


# Raw-transcript metadata schema (scripts/collect_raw_transcripts.py output).
# Real motivation: this is the exact kind of check that would have caught the
# 2026-07-25 corruption (a video with a long stated duration but a suspiciously
# short saved transcript) as a formal, reusable rule instead of a one-off script.
raw_transcript_metadata_schema = DataFrameSchema(
    {
        "video_id": Column(str, Check.str_length(min_value=1)),
        "title": Column(str, nullable=True),
        "channel": Column(str, nullable=True),
        "duration_seconds": Column(float, Check.ge(0), nullable=True),
        "char_count": Column(int, Check.ge(0)),
        "word_count": Column(int, Check.ge(0)),
        "transcript_method": Column(str, Check.isin(["official captions", "local whisper", "unknown"])),
    },
    checks=[
        # The actual rule that would have caught the corruption incident: a
        # transcript that's suspiciously short relative to its stated duration
        # (allowing very short/music-only videos to legitimately have few words).
        Check(
            lambda df: (df["duration_seconds"].fillna(0) < 30)
            | (df["word_count"] >= df["duration_seconds"].fillna(0) * 0.3),
            error="transcript word_count is suspiciously low relative to duration_seconds "
                  "(likely an error message saved as if it were a real transcript)",
        )
    ],
    coerce=True,
    strict=False,
)


def validate_or_report(schema: DataFrameSchema, df, label: str) -> tuple[bool, list[str]]:
    """Validate df against schema; return (is_valid, list_of_failure_messages).
    Never raises - callers decide what to do with failures (log, drop rows, etc.),
    consistent with this vault's anti-silent-failure discipline."""
    try:
        schema.validate(df, lazy=True)
        return True, []
    except pa.errors.SchemaErrors as exc:
        failures = exc.failure_cases
        seen = set()
        messages = []
        for row in failures.to_dict("records"):
            check_name = row.get("check")
            index = row.get("index")
            column = row.get("column")
            # Dedupe by (check, row) only - a per-column check (e.g. two different
            # in_range bounds on two different columns) naturally has a distinct
            # check_name per column already, so this doesn't merge real distinct
            # findings; it only collapses a single dataframe-wide check's repeated
            # per-column report (same check_name, same row, different column) into one.
            key = (check_name, index)
            if key in seen:
                continue
            seen.add(key)
            messages.append(
                f"{label}: row {index} - {check_name} failed"
                + (f" on column {column}" if column else " (dataframe-wide check)")
                + f" (value: {row.get('failure_case')})"
            )
        return False, messages
