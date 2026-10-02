"""Cheap pre-screen for local Part 2b (scripts/finish_drafts_local.py), added
2026-10-01 (Ross-approved plan item 1, with priority ordering = item 2).

Why: full local finishing costs ~30 min to 2 h per item on the RTX 4080 at
quality-first settings, and an off-topic item costs the same as a good one
(the 2026-10-01 gate spent ~50 min on a pet-behaviour episode before
rejecting it). This script decides, for ~30 s per item, what is worth the
expensive pass and in what order:

  - already finished / known duplicate      -> skip (deterministic)
  - relevance + content type                -> gemma, no thinking: 2 votes,
                                               a 3rd only if they disagree
  - priority channel                        -> processed first

Conservative by design. An item is marked `skipped-irrelevant` in
.processed_ids.json ONLY when every signal agrees: all model votes say
off-topic AND (Part 2a's own draft also said off-topic OR it matches a
known low-value pattern). Anything less certain stays in the queue, just
ordered last, so no real content is dropped on a cheap judgment. Every
decision is written to Research/*/Raw/.local_2b_triage.json with its votes.

Usage:
    python scripts/triage_for_2b.py youtube [--limit N]
    python scripts/triage_for_2b.py podcast [--limit N]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import finish_drafts_local as f2b  # noqa: E402
from generate_draft_notes import PRIORITY_CHANNELS, TARGETS, extract_video_id, parse_header_fields, \
    read_json, split_header_body, write_json_atomic  # noqa: E402

TRIAGE_SCHEMA = {"type": "object", "properties": {
    "relevant": {"type": "boolean"},
    "content_type": {"type": "string", "enum": ["monologue", "solo_qa", "conversation"]}},
    "required": ["relevant", "content_type"]}

TRIAGE_PROMPT = """You are screening a transcript for a research vault covering physical health, athletic performance/training, nutrition, supplements, sleep, and mental health.
1. "relevant": true if the content is substantively about any of those topics for humans (not just a passing mention, a vlog, a lift log, entertainment, or animal care).
2. "content_type": "monologue" (one speaker presenting/teaching), "solo_qa" (one main expert answering questions), or "conversation" (two or more people genuinely discussing - interview, co-hosted show, panel).
Title: {title}
Channel: {channel}
<<<
{sample}
>>>"""


def is_priority(channel: str) -> bool:
    c = channel.lower().replace(" ", "")
    return any(p.lower().replace(" ", "") in c for p in PRIORITY_CHANNELS)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", choices=["youtube", "podcast"])
    ap.add_argument("--limit", type=int, default=0, help="max items this run (0 = all)")
    ap.add_argument("--eval", help="comma-separated ids: print triage decisions only, write nothing")
    args = ap.parse_args()

    raw_dir = TARGETS[args.target]["raw_dir"]
    processed_path, drafted_path = raw_dir / ".processed_ids.json", raw_dir / ".drafted_ids.json"
    triage_path = raw_dir / ".local_2b_triage.json"
    files = {extract_video_id(p.name): p for p in raw_dir.glob("*_full.txt") if extract_video_id(p.name)}
    processed, drafted, triage = read_json(processed_path), read_json(drafted_path), read_json(triage_path)
    guids_done = set(processed)

    todo = [i for i in drafted if i in files and i not in processed and i not in triage]
    # Priority channels first, so they get screened - and therefore finished - first.
    chan = {i: parse_header_fields(files[i].read_text(encoding="utf-8", errors="replace")[:1500]).get("channel", "")
            for i in todo}
    todo.sort(key=lambda i: not is_priority(chan[i]))
    if args.eval:
        todo = [i for i in args.eval.split(",") if i in files]
    if args.limit:
        todo = todo[: args.limit]
    f2b.log(f"=== triage {args.target}: {len(todo)} item(s) to screen")
    if todo and not f2b.gpu_preflight():
        f2b.log("ABORT triage: model not on GPU")
        return 2

    stats = Counter()
    for n, vid in enumerate(todo, 1):
        raw = files[vid].read_text(encoding="utf-8", errors="replace")
        header = parse_header_fields(raw)
        if not args.eval and header.get("episode_guid") and header["episode_guid"] in guids_done:
            stats["already_done_by_guid"] += 1
            triage[vid] = {"decision": "already-done", "at": date.today().isoformat()}
            write_json_atomic(triage_path, triage)
            continue
        _, body = split_header_body(raw)
        title, channel = header.get("title", files[vid].stem), header.get("channel", "")
        n_ = len(body)
        sample = body[:2500] + "\n...\n" + body[n_ // 2:n_ // 2 + 2000] + "\n...\n" + body[-1500:]
        prompt = TRIAGE_PROMPT.format(title=title, channel=channel, sample=sample)
        votes = []
        for k in range(3):
            if k == 2 and votes[0]["relevant"] == votes[1]["relevant"]:
                break
            try:
                votes.append(f2b.chat(prompt, TRIAGE_SCHEMA, temperature=0.7 if k else 0.2, num_predict=200))
            except Exception as e:
                f2b.log(f"[{n}/{len(todo)}] {vid}: triage call failed {e}")
                break
        if len(votes) < 2:
            continue
        rel_yes = sum(v["relevant"] for v in votes)
        relevant = rel_yes * 2 > len(votes)
        ctype = Counter(v["content_type"] for v in votes).most_common(1)[0][0]

        d = drafted.get(vid) if isinstance(drafted.get(vid), dict) else {}
        draft = read_json(raw_dir / d["draft_file"]) if d.get("draft_file") else {}
        draft_says_off = draft.get("relevant") is False
        low_value = bool(draft.get("known_low_value_pattern"))
        all_agree_off = rel_yes == 0 and (draft_says_off or low_value)

        entry = {"relevant": relevant, "votes_yes": rel_yes, "votes": len(votes), "content_type": ctype,
                 "priority": is_priority(channel), "draft_relevant": draft.get("relevant"),
                 "low_value_pattern": low_value, "at": date.today().isoformat()}
        if args.eval:
            entry["decision"] = ("skipped-irrelevant" if all_agree_off else "doubtful-last" if not relevant
                                 else "route-claude" if ctype == "conversation" else "local")
            f2b.log(f"EVAL {vid}: {entry} | {title[:70]}")
            continue
        if all_agree_off:
            entry["decision"] = "skipped-irrelevant"
            proc = read_json(processed_path)
            proc[vid] = {"status": "skipped-irrelevant", "finished_by": "local-triage",
                         "reason": f"all signals off-topic (votes 0/{len(votes)}, draft_relevant={draft.get('relevant')}, low_value={low_value})"}
            if header.get("episode_guid"):
                proc[vid]["episode_guid"] = header["episode_guid"]
            write_json_atomic(processed_path, proc)
        elif not relevant:
            entry["decision"] = "doubtful-last"
        elif ctype == "conversation" and not f2b.ROUTE_CONVERSATIONS_LOCAL:
            entry["decision"] = "route-claude"
        else:
            entry["decision"] = "local-priority" if entry["priority"] else "local"
        triage[vid] = entry
        write_json_atomic(triage_path, triage)
        stats[entry["decision"]] += 1
        if n % 25 == 0:
            f2b.log(f"triage {args.target}: {n}/{len(todo)} {dict(stats)}")
    f2b.log(f"=== triage {args.target} done: {dict(stats)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
