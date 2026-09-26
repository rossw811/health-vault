"""Zero-Claude-cost discovery half of the standing journal-watch monitor.

Two complementary arms, per Ross's 2026-09-10 scoping (see ideas.md for the
full design discussion):

1. Known-journal arm: queries PubMed E-utilities per journal already listed in
   .claude/commands/references/trusted-journals.md - stays current with
   sources this vault already trusts.
2. Niche-discovery arm: one broad query, unrestricted by journal, scoped by
   MeSH category (Food/Beverages/Dietary Supplements/Nutritive
   Value/Plant Preparations/Nutraceuticals) rather than a pre-guessed keyword
   list - per Ross's explicit correction ("could be as random as coconut oil
   or nattokinase or orange juice") a fixed topic list would structurally
   miss exactly the kind of niche finding this arm exists to catch.

This script does ONLY discovery: find new PMIDs since the last check, fetch
their TITLES (via esummary - cheap, no abstract fetch), dedupe against
already-vault-cited PMIDs and previously-seen candidates, and write a
candidate list for the (separate, Claude-costing) /journal-watch-process
command to triage. No LLM calls happen here - matches this vault's existing
zero-cost-collection / Claude-costing-processing split
(collect_raw_transcripts.py vs /process-raw-transcripts).

Usage:
    python scripts/journal_watch.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
import urllib.parse
from datetime import date, datetime, timedelta
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parent.parent
TRUSTED_JOURNALS_FILE = VAULT_ROOT / ".claude" / "commands" / "references" / "trusted-journals.md"
STATE_FILE = VAULT_ROOT / "Research" / "Web" / ".state" / "journal-watch-state.json"
CANDIDATES_DIR = VAULT_ROOT / "Research" / "Web" / "Journal-Watch-Candidates"

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
# NCBI allows 3 req/s without an API key - stay well under that across ~65+ journal queries.
REQUEST_DELAY_SECONDS = 0.4

# Excluded at the query level (free) - not new primary findings, not worth a
# relevance-gate pass at all.
PUBTYPE_EXCLUSIONS = (
    'NOT (Comment[PT] OR Editorial[PT] OR News[PT] OR "retracted publication"[PT] '
    'OR "Published Erratum"[PT] OR "Letter"[PT])'
)

# Shared broad-relevance scope. Real finding 2026-09-10, first live run: without
# ANY topic scope, arm 1 (known-journal watch) pulled 3,349 candidates in one
# 14-day window - dominated by genuinely broad/high-volume journals (PLOS ONE
# 497, Journal of Ethnopharmacology 416, Scientific Reports 246, Environmental
# Science & Technology 124, JAMA 122) publishing across all of science, not
# just this vault's topics. A hardcoded "mega-journal" list (the original
# design) would have needed constant manual upkeep and still missed
# Ethnopharmacology, which isn't a mega-journal by reputation but turned out to
# publish at mega-journal volume. Real fix: apply this same broad relevance
# scope to EVERY arm-1 journal query (AND'd with the journal name), not just a
# guessed subset - narrow specialty journals barely lose anything (they were
# already on-topic), broad journals get correctly filtered down to what's
# actually relevant to this vault. Arm 2 uses the same scope unrestricted by
# journal. Deliberately broad (per Ross's "anything related to health, incl
# food and drink and whatever else") rather than a narrow keyword list - MeSH
# category terms do the categorization work instead of guessing compound names.
RELEVANCE_MESH_TERMS = [
    "Food[MeSH]",
    "Beverages[MeSH]",
    '"Dietary Supplements"[MeSH]',
    '"Nutritive Value"[MeSH]',
    '"Plant Preparations"[MeSH]',
    "Nutraceuticals[MeSH]",
    '"Functional Food"[MeSH]',
    '"Endocrine System Diseases"[MeSH]',
    "Hormones[MeSH]",
    '"Exercise"[MeSH]',
    '"Resistance Training"[MeSH]',
    '"Mental Health"[MeSH]',
    '"Mental Disorders"[MeSH]',
    '"Cardiovascular Diseases"[MeSH]',
    "Sleep[MeSH]",
    '"Nutritional and Metabolic Diseases"[MeSH]',
    '"Longevity"[MeSH]',
    '"Peptides"[MeSH]',
]
# Real design correction 2026-09-10, second live test: aliasing this to the
# broadened RELEVANCE_MESH_TERMS above blew arm 2's true 14-day count up to
# 22,881 (endocrine/exercise/mental-health/cardiovascular/sleep/longevity
# categories are each independently huge). That defeats arm 2's actual purpose
# - Ross's ask was specifically "food and drink and whatever else... coconut
# oil, nattokinase, orange juice", i.e. the food/beverage/supplement/compound
# space specifically, not a second copy of arm 1's whole domain. Kept
# deliberately narrower and separate: arm 1 (known journals) needs the broad
# scope to filter mega-journal noise across every domain this vault covers;
# arm 2 (unrestricted-by-journal discovery) stays scoped to where genuinely
# niche/uncatalogued findings actually live - specific foods, beverages,
# supplements, and compounds - which is also what keeps its volume sane
# without a journal restriction to narrow it any other way.
NICHE_MESH_TERMS = [
    "Food[MeSH]",
    "Beverages[MeSH]",
    '"Dietary Supplements"[MeSH]',
    '"Nutritive Value"[MeSH]',
    '"Plant Preparations"[MeSH]',
    "Nutraceuticals[MeSH]",
    '"Functional Food"[MeSH]',
]


def http_get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "health-vault-journal-watch/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


MAX_PAGINATED_RESULTS = 5000  # safety cap - see the loud warning below if a query exceeds this


def esearch(term: str, mindate: str, page_size: int = 500) -> list[str]:
    """Returns PMIDs published since mindate (YYYY/MM/DD), newest first.

    Real bug found and fixed 2026-09-10: a bare single-call retmax=500 was
    silently dropping results whenever a query's true count exceeded 500 -
    confirmed on the niche arm's first real test, where a 14-day window
    returned a true count of 4,749 but only 500 were ever written to the
    candidate file, with nothing indicating the other ~4,249 existed at all.
    Paginates via retstart instead, and loudly warns (never silently drops)
    if a query's true count exceeds MAX_PAGINATED_RESULTS - a query that
    large means the term itself is too broad and needs narrowing, not
    something to page through indefinitely."""
    base_params = {
        "db": "pubmed",
        "term": f'({term}) AND ("{mindate}"[PDAT] : "3000"[PDAT]) {PUBTYPE_EXCLUSIONS}',
        "sort": "pub+date",
        "retmode": "json",
    }
    # First call: retmax=0 just to read the true count cheaply.
    count_url = f"{EUTILS_BASE}/esearch.fcgi?" + urllib.parse.urlencode({**base_params, "retmax": "0"})
    try:
        count_data = json.loads(http_get(count_url))
        true_count = int(count_data.get("esearchresult", {}).get("count", 0))
    except Exception as e:
        print(f"  esearch count-check failed for term={term[:60]!r}: {e}", file=sys.stderr)
        return []

    if true_count == 0:
        return []
    if true_count > MAX_PAGINATED_RESULTS:
        print(f"  WARNING: term={term[:60]!r} has {true_count} results since {mindate} - "
              f"exceeds MAX_PAGINATED_RESULTS ({MAX_PAGINATED_RESULTS}). Fetching only the "
              f"newest {MAX_PAGINATED_RESULTS} - this query is too broad for its current "
              f"date window and needs narrowing (tighter MeSH scope or shorter catch-up "
              f"window) rather than being paginated through indefinitely.", file=sys.stderr)
        true_count = MAX_PAGINATED_RESULTS

    pmids: list[str] = []
    retstart = 0
    while retstart < true_count:
        params = {**base_params, "retmax": str(page_size), "retstart": str(retstart)}
        url = f"{EUTILS_BASE}/esearch.fcgi?" + urllib.parse.urlencode(params)
        try:
            data = json.loads(http_get(url))
            page_ids = data.get("esearchresult", {}).get("idlist", [])
            if not page_ids:
                break
            pmids.extend(page_ids)
            retstart += page_size
            time.sleep(REQUEST_DELAY_SECONDS)
        except Exception as e:
            print(f"  esearch page failed for term={term[:60]!r} at retstart={retstart}: {e}", file=sys.stderr)
            break
    return pmids


def esummary_titles(pmids: list[str]) -> dict[str, dict]:
    """Batch-fetch title/journal/pubdate for a list of PMIDs via esummary
    (far cheaper than efetch's full abstract text - Stage 1 only needs
    enough to let a human/title-triage pass judge relevance)."""
    if not pmids:
        return {}
    out: dict[str, dict] = {}
    # esummary accepts many IDs per call - batch in chunks of 200 to stay safe.
    for i in range(0, len(pmids), 200):
        chunk = pmids[i:i + 200]
        params = {"db": "pubmed", "id": ",".join(chunk), "retmode": "json"}
        url = f"{EUTILS_BASE}/esummary.fcgi?" + urllib.parse.urlencode(params)
        try:
            raw = http_get(url)
            data = json.loads(raw)
            result = data.get("result", {})
            for pmid in chunk:
                rec = result.get(pmid)
                if not rec:
                    continue
                out[pmid] = {
                    "title": rec.get("title", "").strip(),
                    "journal": rec.get("fulljournalname") or rec.get("source", ""),
                    "pubdate": rec.get("pubdate", ""),
                    "doi": next((idobj.get("value") for idobj in rec.get("articleids", [])
                                 if idobj.get("idtype") == "doi"), ""),
                }
        except Exception as e:
            print(f"  esummary failed for chunk starting {chunk[0]}: {e}", file=sys.stderr)
        time.sleep(REQUEST_DELAY_SECONDS)
    return out


def load_journal_list() -> list[str]:
    """Parse journal names out of every markdown table row in
    trusted-journals.md (`| Journal Name | ... |` rows) - reads the living
    document directly rather than hardcoding a copy that would go stale."""
    text = TRUSTED_JOURNALS_FILE.read_text(encoding="utf-8")
    names = []
    for line in text.splitlines():
        m = re.match(r"^\|\s*([^|]+?)\s*\|", line)
        if not m:
            continue
        candidate = m.group(1).strip()
        # Skip table headers/separators and the two known non-journal header rows.
        if not candidate or candidate.lower() in ("journal", "---", "why it's a strong candidate for this vault"):
            continue
        if set(candidate) <= {"-", " "}:
            continue
        # Several table entries pack multiple real journal names into one cell
        # ("PLOS ONE / PLoS ONE", "GeroScience / Nature Aging / Aging Cell") -
        # PubMed's [Journal] filter needs one exact name per query, so split on
        # " / " into separate candidates rather than querying the literal
        # slash-joined string (which would never match anything).
        for part in candidate.split(" / "):
            part = part.strip()
            # Strip a trailing parenthetical abbreviation/alt-name, e.g.
            # "Diabetes (journal)" -> "Diabetes", "JAMA (main)" -> "JAMA" -
            # PubMed's [Journal] field wants the primary indexed name; losing
            # the abbreviation as a separate query is an acceptable coverage
            # gap here since the niche/MeSH arm is the real safety net for
            # anything this misses.
            part = re.sub(r"\s*\([^)]*\)\s*$", "", part).strip()
            if part:
                names.append(part)
    # Dedupe case-insensitively while preserving order and the first-seen
    # casing. Real bug found 2026-09-10: the source table has a "PLOS ONE /
    # PLoS ONE" cell (same journal, two capitalizations from different
    # citations over time) that a case-sensitive dedupe let through as two
    # separate journals - both queries then returned the identical 497 papers,
    # double-writing every one of them into the candidates file.
    seen = set()
    out = []
    for n in names:
        key = n.lower()
        if key not in seen:
            seen.add(key)
            out.append(n)
    return out


def load_vault_cited_pmids() -> set[str]:
    """Live grep of every PMID already cited anywhere in Concepts/Optimization/
    Protocols/Synthesis - always current, no separate cache to go stale."""
    import subprocess
    pmids = set()
    for folder in ("Concepts", "Optimization", "Protocols", "Synthesis"):
        folder_path = VAULT_ROOT / folder
        if not folder_path.exists():
            continue
        try:
            result = subprocess.run(
                ["grep", "-rohE", r"PMID[: ]?[0-9]{6,9}", str(folder_path)],
                capture_output=True, text=True, timeout=30,
            )
            for line in result.stdout.splitlines():
                m = re.search(r"[0-9]{6,9}", line)
                if m:
                    pmids.add(m.group(0))
        except Exception as e:
            print(f"  vault-PMID grep failed for {folder}: {e}", file=sys.stderr)
    return pmids


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"journal_arm": {}, "niche_arm": {"last_checked": None}, "seen_pmids": []}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print what would run, make no network calls or writes.")
    parser.add_argument("--journal-limit", type=int, default=None, help="Only check the first N journals (testing).")
    args = parser.parse_args()

    state = load_state()
    seen_pmids = set(state.get("seen_pmids", []))
    vault_cited = load_vault_cited_pmids()
    print(f"Vault already cites {len(vault_cited)} unique PMIDs (live grep).")

    journals = load_journal_list()
    if args.journal_limit:
        journals = journals[: args.journal_limit]
    print(f"Loaded {len(journals)} journals from trusted-journals.md.")

    if args.dry_run:
        print("--dry-run: would query", len(journals), "journals + 1 niche-MeSH arm. No network calls made.")
        return 0

    default_since = (date.today() - timedelta(days=14)).strftime("%Y/%m/%d")
    all_candidates = []

    # --- Arm 1: known journals, now AND'd with the same relevance scope arm 2
    # uses (see RELEVANCE_MESH_TERMS docstring above for why this was added
    # after the first real run showed broad journals dominating volume
    # unfiltered) ---
    relevance_scope = "(" + " OR ".join(RELEVANCE_MESH_TERMS) + ")"
    for jname in journals:
        j_state = state["journal_arm"].get(jname, {})
        since = j_state.get("last_checked", default_since)
        term = f'"{jname}"[Journal] AND {relevance_scope}'
        pmids = esearch(term, since)
        new_pmids = [p for p in pmids if p not in seen_pmids and p not in vault_cited]
        if new_pmids:
            titles = esummary_titles(new_pmids)
            for pmid, meta in titles.items():
                all_candidates.append({"pmid": pmid, "arm": "journal", "source_journal": jname, **meta})
                seen_pmids.add(pmid)  # dedupe within this same run too, not just against history
        state["journal_arm"][jname] = {"last_checked": date.today().strftime("%Y/%m/%d")}
        time.sleep(REQUEST_DELAY_SECONDS)

    print(f"Arm 1 (known journals): {sum(1 for c in all_candidates if c['arm'] == 'journal')} new candidates across {len(journals)} journals.")

    # --- Arm 2: niche/broad discovery ---
    niche_since = state["niche_arm"].get("last_checked") or default_since
    niche_term = "(" + " OR ".join(NICHE_MESH_TERMS) + ")"
    niche_pmids = esearch(niche_term, niche_since)
    niche_new = [p for p in niche_pmids if p not in seen_pmids and p not in vault_cited]
    if niche_new:
        titles = esummary_titles(niche_new)
        for pmid, meta in titles.items():
            all_candidates.append({"pmid": pmid, "arm": "niche", "source_journal": meta.get("journal", ""), **meta})
    state["niche_arm"]["last_checked"] = date.today().strftime("%Y/%m/%d")

    print(f"Arm 2 (niche/broad MeSH): {len(niche_new)} new candidates (of {len(niche_pmids)} total found this window).")

    # Update seen set and persist.
    for c in all_candidates:
        seen_pmids.add(c["pmid"])
    state["seen_pmids"] = sorted(seen_pmids)
    save_state(state)

    if all_candidates:
        CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
        out_path = CANDIDATES_DIR / f"{date.today().isoformat()}.json"
        # Real bug found and fixed 2026-09-10: a bare overwrite here silently
        # destroyed a same-day run's earlier candidates when the script ran
        # twice in one day (a manual test run, then the newly-enabled timer's
        # immediate first fire) - the second run's smaller candidate set
        # replaced the first run's larger one instead of merging, and nothing
        # in the output flagged that anything had been lost. Merge with
        # whatever's already in today's file instead, deduped by PMID.
        existing = []
        if out_path.exists():
            try:
                existing = json.loads(out_path.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"  WARNING: today's candidates file exists but failed to parse ({e}) - "
                      f"not merging, writing fresh to avoid losing this run's results.", file=sys.stderr)
        existing_pmids_in_file = {c["pmid"] for c in existing}
        merged = existing + [c for c in all_candidates if c["pmid"] not in existing_pmids_in_file]
        out_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        print(f"Wrote {len(merged)} total candidates to {out_path} "
              f"({len(all_candidates)} found this run, {len(existing)} already present today, merged not overwritten)")
    else:
        print("No new candidates this run.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
