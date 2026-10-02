#!/bin/bash
# Gemini-for-Part-2b quality test (CachyOS), added 2026-10-02. Test only: runs in
# --gate mode, so it writes to Research/.local-2b-gate/*.gemini.* and touches no
# checkpoint, processed-ids or vault note. Compare the output against the
# Claude-finished notes for the same items before using Gemini in production.
#
# Prereq: GEMINI_API_KEY in ~/Health/.env (or the environment).
# Usage:  scripts/test_gemini_2b.sh [gemini-model-name]     (default gemini-3.8-flash)
#
# What it does:
#   1. lists available models and sends one tiny JSON call (setup check)
#   2. runs the full verified pipeline with Gemini doing extraction/compose and
#      the local qwen3.8 doing cross-verification (a second model family), on:
#        - 3 conversations Claude already finished (the content type local
#          notes are weakest on and that is currently routed to Claude):
#          52-sets study (known double-negative trap), bodybuilder interview
#          (mental-health content), borderline travel chat
#        - 1 monologue and 1 long podcast for comparison
set -euo pipefail
cd "$HOME/Health"
M="${1:-gemini-3.8-flash}"
export OLLAMA_HOST=http://127.0.0.1:11435 THINK_PROFILE=fast
PY=.venv/bin/python
echo "== setup check"; $PY scripts/llm_backends.py ping "gemini:$M"
echo "== YouTube test items"
$PY scripts/finish_drafts_local.py youtube --model "gemini:$M" \
    --gate l8c9BPtwXMs,WN1lUBV7ux8,e1_pbhPuuCg,hObAAPCW07U --gate-suffix ".gemini"
echo "== podcast test item"
$PY scripts/finish_drafts_local.py podcast --model "gemini:$M" --gate 10edca980fa6fd12 --gate-suffix ".gemini"
echo "== done - notes in Research/.local-2b-gate/*.gemini.md; usage in Logs/gemini-usage.jsonl"
