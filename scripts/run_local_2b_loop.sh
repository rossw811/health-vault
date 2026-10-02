#!/bin/bash
# Continuous Part 2 production loop (CachyOS), started 2026-10-01.
# The single GPU consumer: each cycle drafts a small Part 2a batch (while
# undrafted items remain), triages newly drafted items (cheap, ~30 s each,
# priority channels first), then finishes a batch of triaged items with the
# full verified local pipeline (conversations stay with Claude's
# /finish-draft-notes). Part 2a's own timers are disabled while this runs -
# two jobs sharing one GPU kept swapping models and raced the GPU check.
# Zero Claude cost. Local notes are labelled trust_tier: local-verified;
# 1-in-10 plus every flagged note lands in Research/.local-2b-audit-queue.json.
set -u
cd "$HOME/Health" || exit 1
exec 9>"$HOME/Health/Logs/.local-2b-loop.lock"
flock -n 9 || { echo "local 2b loop already running"; exit 0; }
export OLLAMA_HOST=http://127.0.0.1:11435
PY=.venv/bin/python
DRAFT_BATCH=${DRAFT_BATCH:-10}
TRIAGE_LIMIT=${TRIAGE_LIMIT:-40}
BATCH=${BATCH:-6}
while true; do
  for t in youtube podcast; do
    $PY scripts/generate_draft_notes.py "$t" --batch-size "$DRAFT_BATCH"
    $PY scripts/triage_for_2b.py "$t" --limit "$TRIAGE_LIMIT"
    $PY scripts/finish_drafts_local.py "$t" --batch-size "$BATCH"
  done
  sleep 30
done
