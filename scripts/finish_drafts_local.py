"""Local Part 2b: finish raw transcripts into AI-first notes with zero Claude
cost, using a local Ollama model behind programmatic verification gates.
Added 2026-09-30 (ideas.md item 21).

Why this is not just "Part 2a with a better model": the 2026-08-15 Phase 5
test showed a local model can't be trusted to write notes unsupervised
(qwen2.5:14b: 3/9 density agreement, 50% verbatim quotes). So this script
never lets free-form model output reach a note unchecked. Every factual line
traces to transcript text that Python itself verified:

  1. EXTRACT (per chunk): the model proposes claims, each with a verbatim
     `evidence` snippet, plus candidate quotes and named people.
  2. GROUND (Python, no LLM): evidence must be found in the real source text
     (case/punctuation-insensitive); quotes must be exact whitespace-normalized
     substrings (the same rule generate_draft_notes.py uses); person names must
     literally appear in the transcript. Anything that fails is dropped.
  3. VERIFY (second, independent LLM pass): each surviving claim is shown only
     with a ~1,400-char window of real source text around its evidence and
     judged supported / not; promotional claims are dropped. Quotes get a
     coherence + promo check (catches whisper-garbled substrings).
  4. RELEVANCE: 3-vote self-consistency instead of one guess.
  5. DENSITY: a deterministic rule on verified-claim rate, not the model's
     holistic guess (which disagreed with its own structure map 13/15 times on
     2026-09-27). Thresholds are calibrated against Claude-finished notes.
  6. COMPOSE: the model writes TL;DR / Key Points from the verified claims
     only (it never sees the transcript at this step), every key point must
     cite claim ids, and any number not present in the cited material is
     rejected. Quotes and Researchers sections are assembled by Python
     directly from verified items, so the model cannot add to them.

Output notes are labelled `finished_by: local-<model>` and
`trust_tier: local-verified`, never silently equivalent to a Claude note.
Concept-linking is deliberately NOT done here (NEW-MACHINE-SETUP.md Phase 6
rule 7); the existing periodic Claude concept-absorption pass picks these
notes up. New people are queued in Research/.people_candidates.json rather
than stubbed, since tiering is a judgment call.

Usage:
    python scripts/finish_drafts_local.py youtube --batch-size 20
    python scripts/finish_drafts_local.py podcast --batch-size 20
    python scripts/finish_drafts_local.py youtube --gate ID1,ID2,...   # A/B only:
        writes to Research/.local-2b-gate/, touches no checkpoint files
"""

from __future__ import annotations

import argparse
import difflib
import os
import json
import re
import sys
import time
import unicodedata
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collector_common import strip_filler_text  # noqa: E402
from llm_backends import QuotaExhausted, gemini_chat, is_gemini  # noqa: E402
from generate_draft_notes import (  # noqa: E402
    TARGETS,
    extract_video_id,
    parse_header_fields,
    read_json,
    split_header_body,
    verify_and_filter_quotes,
    write_json_atomic,
)

VAULT_ROOT = Path(__file__).resolve().parent.parent
# OLLAMA_HOST override lets a temporary user-level server be used (e.g. when the
# system service has fallen back to CPU after a boot-time GPU-discovery timeout).
OLLAMA_CHAT = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/") + "/api/chat"
MODEL = "gemma4:26b"
# v3 (2026-10-01): a second model family re-checks every verified claim and
# looks for claims that contradict each other. Rationale: the 2026-10-01 gate
# showed gemma misreading a double negative ("we would have found it - we
# didn't") the same way when writing AND when checking, so self-verification
# can't catch it; an error now has to fool two different models.
VERIFY_MODEL = os.environ.get("VERIFY_MODEL", "qwen3.8:27b")
CROSS_VERIFY = os.environ.get("CROSS_VERIFY", "1") == "1"
WIDE_WINDOW = 2500
# Content-type routing (approved by Ross 2026-10-01): the gate found local
# notes at ~85-90% of Claude on single-speaker teaching but 40-75% on
# multi-person conversations. Conversations are left for Claude's
# /finish-draft-notes unless ROUTE_CONVERSATIONS_LOCAL=1.
ROUTE_CONVERSATIONS_LOCAL = os.environ.get("ROUTE_CONVERSATIONS_LOCAL") == "1"
AUDIT_SAMPLE_EVERY = 10  # Claude spot-audits 1 in N local notes plus every flagged one
AUDIT_QUEUE = VAULT_ROOT / "Research" / ".local-2b-audit-queue.json"
NUM_CTX = 16384
CHUNK_CHARS = 24000
CHUNK_OVERLAP = 800
VERIFY_BATCH = 10
WINDOW = 700
RELEVANCE_VOTES = 3
# Quality over speed (Ross, 2026-09-30): judgment steps (verify, quote check,
# compose, risk screen) run with the model's thinking mode on.
THINK = True
# Speed profile (2026-10-01, Ross approved testing "idea #1"): measured on the
# 4080, gemma4:26b generates ~54 tok/s but qwen3.8:27b only ~8 tok/s (dense,
# doesn't fit in 16 GB), and long thinking dominated every call. "full" = the
# validated v3 settings; "fast" keeps (low) thinking only on the steps that
# decide what is true (verify, cross-verify, contradiction resolution, compose).
THINK_PROFILE = os.environ.get("THINK_PROFILE", "full")
_THINK_PROFILES = {
    "full": {k: True for k in ("coverage", "verify", "cross", "consist", "resolve", "quotes", "compose", "risk")},
    # cross=False: qwen3.8 caught the known double-negative inversion with
    # thinking OFF (48 s) as well as low (783 s); gemma4 failed it at low/off
    # and only passed with full thinking (inversion probe, 2026-10-01).
    "fast": {"coverage": False, "verify": "low", "cross": False, "consist": False, "resolve": "low",
             "quotes": False, "compose": "low", "risk": False},
}


def T(step: str):
    return _THINK_PROFILES[THINK_PROFILE][step]
GATE_DIR = VAULT_ROOT / "Research" / ".local-2b-gate"
PEOPLE_CANDIDATES = VAULT_ROOT / "Research" / ".people_candidates.json"
LOG = VAULT_ROOT / "Logs" / "finish-drafts-local.log"

# Density rule - verified claims per 10K chars of filler-stripped transcript.
# Initial values; recalibrated by the --gate run against Claude's own labels.
# Calibrated 2026-10-01 against Claude's own labels: total verified claims is
# what tracks Claude's judgement, not claims-per-length (short videos score a
# HIGH rate but Claude calls them low/mixed). Fit on 6 labelled videos
# (7->low, 8->mixed, 12->mixed, 30->high, 34->high, 51->high); the rate terms
# only guard very long, thin episodes. Small sample - recheck as audits add labels.
DENSITY_HIGH_RATE, DENSITY_HIGH_MIN = 2.5, 20
DENSITY_LOW_RATE, DENSITY_LOW_MIN = 1.0, 8
DEPTH = {"high": (16, 5), "mixed": (8, 3), "low": (5, 2)}  # (key points, quotes)


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


# ---------------------------------------------------------------- ollama

THINK_EXTRA_TOKENS = 16384  # reasoning budget; too small and the JSON answer gets cut off


def chat(prompt: str, schema: dict, temperature: float = 0.2, num_predict: int = 4096, think: bool | str = False,
         model: str | None = None) -> dict:
    """Thinking calls get a much larger output budget and context, since the
    reasoning tokens count against num_predict - a 6K budget was found
    (2026-09-30) to cut off the JSON answer on longer compose prompts. If a
    thinking call still fails to return valid JSON, the last attempt falls
    back to thinking off rather than losing the item."""
    use_think = think if THINK else False
    m = model or MODEL
    if is_gemini(m):
        # Hosted backend (scripts/llm_backends.py) - does its own retries and
        # quota pacing; QuotaExhausted propagates so the batch stops cleanly.
        return gemini_chat(m, prompt, schema, temperature=temperature, num_predict=num_predict, think=use_think)
    last_err = None
    for attempt in range(3):
        thinking = use_think if attempt < 2 else False
        body = {
            "model": model or MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "format": schema,
            "stream": False,
            "think": thinking,
            # One fixed context size for every call: Ollama reloads the whole
            # model whenever num_ctx changes, and alternating 16K/32K caused 8
            # reloads in 21 calls (~1-2 min each) on 2026-10-01.
            "options": {"num_ctx": NUM_CTX * 2, "temperature": temperature,
                        "num_predict": num_predict + (THINK_EXTRA_TOKENS if thinking else 0)},
        }
        try:
            req = urllib.request.Request(OLLAMA_CHAT, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=1800) as r:
                content = json.loads(r.read())["message"]["content"]
            return json.loads(content)
        except Exception as e:  # malformed/truncated JSON or transient server error
            last_err = e
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"ollama call failed 3x: {last_err}")


def finished_by_label() -> str:
    """'local-gemma4:26b' for local runs; 'gemini-<model>' for hosted runs, so a
    hosted note is never labelled local (trust_tier still marks it unreviewed)."""
    return MODEL.replace("gemini:", "gemini-", 1) if is_gemini(MODEL) else f"local-{MODEL}"


def gpu_preflight() -> bool:
    """Load the main model with a tiny request, then confirm via /api/ps that
    some of it is resident in VRAM. Guards against the silent CPU-only
    fallback seen 2026-09-25 and 2026-09-30."""
    # Retried: another job swapping models on the shared server can leave
    # /api/ps momentarily empty right after our call (false abort 2026-10-01).
    local = next((x for x in (MODEL, VERIFY_MODEL if CROSS_VERIFY else None) if x and not is_gemini(x)), None)
    if local is None:
        return True  # all-hosted run: no local GPU involved
    for attempt in range(6):
        if _gpu_check_once(local):
            return True
        time.sleep(20)
    return False


def _gpu_check_once(local_model: str) -> bool:
    try:
        chat("Reply with JSON {\"ok\": true}.", {"type": "object", "properties": {"ok": {"type": "boolean"}}}, num_predict=20,
             model=local_model)
        base = OLLAMA_CHAT.rsplit("/api/", 1)[0]
        with urllib.request.urlopen(base + "/api/ps", timeout=30) as r:
            models = json.loads(r.read()).get("models", [])
        # Any loaded model with VRAM proves the server itself is on the GPU (a
        # CPU-fallback server shows size_vram 0 for everything). Checking only
        # MODEL raced with other jobs swapping models on the shared server and
        # false-aborted a triage run on 2026-10-01.
        return any(m.get("size_vram", 0) > 0 for m in models)
    except Exception as e:
        log(f"gpu preflight error: {e}")
        return False


# ---------------------------------------------------------------- grounding

def loose_index(text: str) -> tuple[str, list[int]]:
    """Lowercase alnum-and-single-space form of `text` plus a map from each
    loose char back to its original index, so a match found loosely can be
    located in the real text for the verification window."""
    out, idx, prev_space = [], [], True
    for i, ch in enumerate(text):
        c = unicodedata.normalize("NFKD", ch)
        c = "".join(x for x in c if not unicodedata.combining(x)).lower()
        if c and c.isalnum():
            out.append(c[0]); idx.append(i); prev_space = False
        elif not prev_space:
            out.append(" "); idx.append(i); prev_space = True
    return "".join(out), idx


def loose(s: str) -> str:
    return loose_index(s)[0].strip()


def ground(evidence: str, src_loose: str, src_map: list[int]) -> int | None:
    e = loose(evidence)
    if len(e.split()) < 5:
        return None
    pos = src_loose.find(e)
    return src_map[pos] if pos >= 0 else None


# ---------------------------------------------------------------- prompts

CLAIM_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {"type": "array", "items": {"type": "object", "properties": {
            "claim": {"type": "string"}, "evidence": {"type": "string"}},
            "required": ["claim", "evidence"]}},
        "quotes": {"type": "array", "items": {"type": "string"}},
        "people": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "context": {"type": "string"}, "evidence": {"type": "string"}},
            "required": ["name", "context", "evidence"]}},
        "themes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["claims", "quotes", "people", "themes"],
}

EXTRACT_PROMPT = """You are extracting material from part {part} of {parts} of a transcript for a health, fitness and mental-health research vault.
Title: {title}
Channel: {channel}

Return JSON with:
- "claims": every substantive claim, recommendation, mechanism, number, study finding, protocol detail or personal-experience report about health, training, nutrition, supplements/drugs, sleep, or mental health. Skip sponsor reads, ads, merch, greetings, and chit-chat. Each claim gets "claim" (one plain sentence in your own words, keep specific numbers/doses/units) and "evidence" (an EXACT contiguous passage copied character-for-character from the transcript below, 10-40 words, that states it).
- "quotes": up to 4 standout passages copied EXACTLY from the transcript (15-60 words each), coherent on their own, not promotional.
- "people": real named individuals cited as sources of expertise (researchers, doctors, authors, study authors, guests). Not the host, not sponsors. "context" = why they were mentioned; "evidence" = exact transcript passage naming them.
- "themes": 3-6 short topic tags.
Mental health is a first-class topic here, not secondary: always extract what speakers say about mood, anxiety, motivation, burnout, irritability, self-worth/identity tied to performance, and psychological effects of training, dieting or drugs - including personal disclosures.
Be thorough: include study designs (who, how many, how long, what groups), results and their direction, caveats and limitations the speaker gives, and anything about risk or safety (head trauma/concussion, injury, drug or supplement use and doses, side effects).
State each claim's direction exactly as the speaker meant it. Read negations and double negatives carefully ("if X existed we would have found Y, and we didn't" means Y was NOT found).
Never invent anything that is not in the transcript. Copy evidence and quotes exactly; do not fix grammar or spelling.

TRANSCRIPT PART:
<<<
{text}
>>>"""

VERIFY_SCHEMA = {
    "type": "object",
    "properties": {"results": {"type": "array", "items": {"type": "object", "properties": {
        "id": {"type": "integer"}, "supported": {"type": "string", "enum": ["yes", "no", "partial"]},
        "promotional": {"type": "boolean"}, "transcription_suspect": {"type": "boolean"}},
        "required": ["id", "supported", "promotional", "transcription_suspect"]}}},
    "required": ["results"],
}

VERIFY_PROMPT = """Check each claim strictly against ONLY its source excerpt (a transcript).
"supported": "yes" only if the excerpt clearly states the claim including any numbers, doses and units; "partial" if the claim adds, changes or overstates anything; "no" if the excerpt does not say it.
Check direction and polarity first: negations, double negatives, conditionals ("if X, we would have seen Y - we didn't"), more/less, increase/decrease, did/didn't, helps/harms. If the claim's direction or polarity differs from what the speaker meant in any way, answer "no".
"promotional": true if the claim is advertising a product, sponsor, discount code, course, or the speaker's own merchandise.
"transcription_suspect": true if the claim depends on a word in the excerpt that looks like a speech-to-text error (e.g. a drug, hormone, compound or person name that is misspelled, nonsensical, or inconsistent with the rest of the excerpt).

{items}"""

QUOTE_SCHEMA = {
    "type": "object",
    "properties": {"results": {"type": "array", "items": {"type": "object", "properties": {
        "id": {"type": "integer"}, "coherent": {"type": "boolean"}, "promotional": {"type": "boolean"}},
        "required": ["id", "coherent", "promotional"]}}},
    "required": ["results"],
}

QUOTE_PROMPT = """For each transcript quote: "coherent" is true only if it reads as sensible English on its own, with no garbled or nonsensical words (speech-to-text errors like a wrong drug or hormone name make it false). "promotional" is true if it advertises a product, sponsor or course.

{items}"""

REL_SCHEMA = {"type": "object", "properties": {"relevant": {"type": "boolean"}, "reason": {"type": "string"}},
              "required": ["relevant", "reason"]}

REL_PROMPT = """A research vault covers physical health, athletic performance/training, nutrition, supplements, sleep, and mental health. Is the content below substantively about any of these (not just a passing mention, vlog, lift log, or entertainment)?
Title: {title}
Channel: {channel}
Sample of the transcript:
<<<
{sample}
>>>
Verified claims extracted from it ({n} total, first 15):
{claims}"""

COMPOSE_SCHEMA = {
    "type": "object",
    "properties": {
        "for_future_claude": {"type": "string"},
        "tldr": {"type": "string"},
        "key_points": {"type": "array", "items": {"type": "object", "properties": {
            "text": {"type": "string"}, "claim_ids": {"type": "array", "items": {"type": "integer"}}},
            "required": ["text", "claim_ids"]}},
        "follow_up": {"type": "array", "items": {"type": "string"}},
        "themes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["for_future_claude", "tldr", "key_points", "follow_up", "themes"],
}

COMPOSE_PROMPT = """Write a research note from ONLY the verified claims below. Do not add any fact, number, name or study that is not in them.
Title: {title}
Channel: {channel}
Content type: {kind}; signal density: {density}

- "for_future_claude": 2-4 sentences: what this source is, what kind of evidence it offers (personal experience, cited studies, coaching opinion), and how much to trust it.
- "tldr": 1-3 sentences summarizing the main takeaways.
- "key_points": at most {max_kp} points, most important first. Cover the WHOLE source evenly from beginning to end - the central thesis and main conclusions often come late, so never spend all points on the opening. Merge overlapping claims. Each cites the claim ids it is based on in "claim_ids". Keep numbers exactly as written in the claims. Say plainly when something is the speaker's opinion or anecdote rather than evidence.
- "follow_up": 0-4 specific things worth checking against the scientific literature (claims that are surprising, dosing-related, or contestable).
- "themes": 3-6 short lowercase topic tags.

VERIFIED CLAIMS:
{claims}"""


RISK_SCHEMA = {"type": "object", "properties": {"flags": {"type": "array", "items": {"type": "string"}}}, "required": ["flags"]}

RISK_PROMPT = """You are screening claims from a health video/podcast for safety concerns a careful reader should check.
List up to 5 concerns, each one short sentence, ONLY about the claims below: doses well above common clinical use, drug/supplement combinations with known interaction risk (e.g. two serotonergic agents), off-label or unapproved compounds, practices that are risky for some people, and **numbers the speaker states that are physiologically or pharmacologically implausible** (e.g. a lab value outside what is survivable, like a hematocrit of 84%, or a drug-dose conversion far from standard clinical equivalence) - name the speaker's number and say why it looks wrong, but **do not introduce any new numbers of your own** (say "far above the normal range" or "far from standard clinical equivalence" instead of giving a figure). Return an empty list if there is nothing notable. Do not restate claims that are unremarkable.

CLAIMS:
{claims}"""


CTYPE_SCHEMA = {"type": "object", "properties": {"content_type": {"type": "string",
                "enum": ["monologue", "solo_qa", "conversation"]}}, "required": ["content_type"]}

CTYPE_PROMPT = """Classify the format of this transcript.
"monologue": one speaker presenting or teaching (lecture, solo podcast, explainer video).
"solo_qa": one main expert answering audience or listener questions, with little back-and-forth.
"conversation": two or more people genuinely discussing (interview, co-hosted show, panel, casual chat).
Title: {title}
Channel: {channel}
<<<
{sample}
>>>"""

CONSIST_SCHEMA = {"type": "object", "properties": {"pairs": {"type": "array", "items": {"type": "object",
                  "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}, "required": ["a", "b"]}}},
                  "required": ["pairs"]}

CONSIST_PROMPT = """Below are claims extracted from ONE video/podcast. Find pairs that contradict each other: same topic, opposite direction or incompatible numbers (e.g. "higher volume produced more growth" vs "higher volume produced no additional growth"). Ignore claims that merely differ in topic or detail. Return an empty list if there are none.

{claims}"""

RESOLVE_SCHEMA = {"type": "object", "properties": {"a_supported": {"type": "boolean"}, "b_supported": {"type": "boolean"},
                  "explanation": {"type": "string"}}, "required": ["a_supported", "b_supported", "explanation"]}

RESOLVE_PROMPT = """Two claims extracted from the same transcript appear to contradict each other. Read each against its longer source excerpt and decide which accurately states what the speaker meant. Pay close attention to negations, double negatives and conditionals ("if it existed we would have found it - and we didn't" means it was NOT found). Either, both, or neither may be supported.

CLAIM A: {a}
SOURCE A: "{sa}"

CLAIM B: {b}
SOURCE B: "{sb}"
"""


# ---------------------------------------------------------------- pipeline

def chunks(text: str) -> list[str]:
    if len(text) <= CHUNK_CHARS:
        return [text]
    out, i = [], 0
    while i < len(text):
        out.append(text[i:i + CHUNK_CHARS])
        i += CHUNK_CHARS - CHUNK_OVERLAP
    return out


NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")
# Thinking mode makes the model append its own "[3]"/"[1, 4]" citation markers;
# strip them so they are neither shown nor mistaken for unsupported numbers.
CITE_MARK_RE = re.compile(r"\s*\[\d+(?:\s*,\s*\d+)*\]")


# Compound-name garble flagging (2026-10-01 audit: Whisper turned boldenone
# into "Bouldinone" and Increlex into "Incrolix", and nothing flagged them).
# A word that closely resembles a known compound without matching it gets a
# "verify" note - never an automatic correction. Limitation: a garble that
# lands on another real compound (DHEA heard as "DHA") can't be caught by
# spelling; the audit queue covers that.
COMPOUND_LEXICON = sorted(set("""
testosterone nandrolone boldenone trenbolone masteron drostanolone primobolan methenolone anavar oxandrolone
dianabol methandrostenolone winstrol stanozolol anadrol oxymetholone turinabol halotestin superdrol proviron
mesterolone dht dhea pregnenolone progesterone estradiol enanthate cypionate propionate decanoate undecanoate
hcg hmg fsh gonal clomiphene clomid enclomiphene tamoxifen nolvadex anastrozole arimidex letrozole exemestane
aromasin cabergoline bromocriptine finasteride dutasteride spironolactone
somatropin genotropin norditropin omnitrope humatrope serostim saizen igf mecasermin increlex ipamorelin
sermorelin tesamorelin cjc ghrp hexarelin mk677 ibutamoren somatostatin
semaglutide ozempic wegovy tirzepatide mounjaro zepbound retatrutide liraglutide metformin acarbose
insulin lantus humalog novolog glucagon berberine
bpc tb500 thymosin epitalon pinealon selank semax cerebrolysin dihexa noopept mots kisspeptin oxytocin
melanotan pt141 bremelanotide ghk foxo humanin ss31 elamipretide nad nmn nicotinamide resveratrol rapamycin sirolimus
clenbuterol albuterol salbutamol ephedrine yohimbine dnp liothyronine cytomel levothyroxine thyroxine eltroxin
accutane isotretinoin tretinoin minoxidil ketoconazole
modafinil armodafinil adderall amphetamine methylphenidate ritalin caffeine nicotine theanine tyrosine
fluvoxamine fluoxetine sertraline escitalopram bupropion wellbutrin mirtazapine remeron trazodone
cyproheptadine periactin megestrol buspirone gabapentin pregabalin ashwagandha rhodiola tongkat eurycoma fadogia
creatine citrulline arginine taurine glycine carnitine glutathione cysteine acetylcysteine tudca ursodiol
magnesium zinc selenium boron iodine potassium sodium melatonin inositol berberine quercetin fisetin curcumin
omega dha epa coq10 ubiquinol astaxanthin spermidine urolithin methylene blue
aspirin ibuprofen naproxen acetaminophen tadalafil cialis sildenafil viagra telmisartan losartan lisinopril
atorvastatin rosuvastatin ezetimibe niacin nattokinase serrapeptase lumbrokinase
""".split()))
COMPOUND_SET = set(COMPOUND_LEXICON)


# Real words/compounds the lexicon match would otherwise misfire on (measured
# against ~2,300 words of real notes, 2026-10-01).
NOT_GARBLES = {"glutamine", "inulin", "creatinine", "ornithine", "progestin", "progestins", "thyroid", "romanian",
               "spartan", "spartans", "electron", "increase", "anabolic", "omega-3", "omega-3s", "saline", "healing",
               "insulin-like", "testicular", "estrogen", "cortisol", "dopamine", "serotonin",
               "created", "create", "creates", "creating", "named", "names", "months", "goals", "treating", "retaining",
               "retained", "relative", "combine", "signal", "boring", "fresh", "performing", "practicing", "proximate",
               "reversal", "berries", "carbs", "pound", "pounds", "proportional", "discontinue", "oblique",
               "epithalon", "thiamine", "c-reactive", "incredible", "dayspring", "blues", "roman",
               "ghrelin", "prolactin", "myostatin", "melanocortin", "leptin", "adiponectin", "orexin", "vasopressin",
               "humans", "marine", "mastery", "italian", "superhero"}


def flag_compound_garbles(text: str) -> str:
    """Flag mid-sentence capitalized words that closely resemble a known
    compound without matching it. Measured 2026-10-01 over 600 real notes:
    the real garbles (Bouldinone, Incrolix, Caberline, Tesarelin, Tremolone,
    Ultroxine, Myrtazapine) were all mid-sentence capitalized drug names; the
    false positives were mostly sentence-initial ordinary words."""
    out = text
    for mt in re.finditer(r"(?<![A-Za-z0-9-])[A-Z][A-Za-z0-9-]{4,}", text):
        w = mt.group(0)
        before = text[:mt.start()].rstrip()
        if not before or before[-1] in '.!?:;#>*-(["\n':
            continue  # sentence-initial/list-initial capital: ordinary words, not the garbles seen so far
        if w.isupper() or len(w.replace("-", "")) < 6:
            continue  # acronyms (NADPH, NAFLD) and short words are not the garbles seen so far
        lw = w.lower()
        if lw.replace("-", "") in COMPOUND_SET:
            continue  # hyphenation variants: MK-677, PT-141, TB-500, SS-31
        parts = [x for x in lw.split("-") if x]
        if lw in COMPOUND_SET or lw in NOT_GARBLES or any(x in COMPOUND_SET or x in NOT_GARBLES for x in parts):
            continue
        m = difflib.get_close_matches(lw, COMPOUND_LEXICON, n=1, cutoff=0.75)
        if m:
            out = out.replace(w, f'{w} [transcript term - possibly {m[0]}? verify]', 1)
    return out


MH_RE = re.compile(r"\b(anxi\w*|depress\w*|mood|motivat\w*|burnout|burn(ed|t)? out|irritab\w*|stress\w*|self[- ]worth|"
                   r"identity|mental health|psycholog\w*|emotion\w*|rage|aggress\w*|confidence|lonel\w*|trauma\w*|"
                   r"ptsd|obsess\w*|compuls\w*|addict\w*|neurotic\w*|wellbeing|well-being|happiness)\b", re.I)


SAFETY_RE = re.compile(r"\b(concuss\w*|head (trauma|injur\w*)|two[- ]hit|tbi|brain injur\w*|injur\w*|side effect\w*|"
                       r"overdose|toxic\w*|contraindicat\w*|interact\w*|hypoglyc\w*|bleed\w*|risk\w*)\b", re.I)


def strip_cites(s: str) -> str:
    return CITE_MARK_RE.sub("", s or "").strip()


def numbers_ok(text: str, allowed: str) -> bool:
    allowed_nums = set(NUM_RE.findall(allowed))
    return all(n in allowed_nums for n in NUM_RE.findall(text))


def density_rule(n_claims: int, lite_len: int) -> str:
    rate = n_claims / max(lite_len / 10000, 0.5)
    if rate >= DENSITY_HIGH_RATE and n_claims >= DENSITY_HIGH_MIN:
        return "high"
    if rate < DENSITY_LOW_RATE or n_claims < DENSITY_LOW_MIN:
        return "low"
    return "mixed"


def existing_people() -> dict[str, str]:
    people = {}
    for p in (VAULT_ROOT / "People").glob("*.md"):
        people[loose(p.stem)] = p.stem
    return people


def process_one(raw_path: Path, kind: str, variant: str = "merged", route_only: bool = False) -> dict:
    raw_text = raw_path.read_text(encoding="utf-8", errors="replace")
    header = parse_header_fields(raw_text)
    _, body = split_header_body(raw_text)
    lite, _ = strip_filler_text(body)
    title, channel = header.get("title", raw_path.stem), header.get("channel", "")
    src_loose, src_map = loose_index(body)
    stats = Counter()
    n = len(body)
    sample = body[:2500] + "\n...\n" + body[n // 2:n // 2 + 2000] + "\n...\n" + body[-1500:]
    ctypes = [chat(CTYPE_PROMPT.format(title=title, channel=channel, sample=sample), CTYPE_SCHEMA,
                   temperature=0.7)["content_type"] for _ in range(3)]
    content_type = Counter(ctypes).most_common(1)[0][0]
    if route_only and content_type == "conversation":
        return {"title": title, "channel": channel, "header": header, "content_type": content_type,
                "status": "routed-to-claude", "stats": dict(stats), "density": None}

    # Split variant (Part 2a draft -> Part 2b): the qwen draft's key points
    # become hints the extractor must re-find with exact evidence, and its
    # already-verbatim-checked quotes join the quote pool. Merged variant
    # works from the raw transcript alone.
    hint = ""
    claims, quotes, people, themes = [], [], [], []
    if variant == "split":
        import generate_draft_notes as g2a
        g2a.OLLAMA_URL = OLLAMA_CHAT.replace("/api/chat", "/api/generate")
        t2a = time.time()
        draft = g2a.query_ollama_chunked(lite, title, g2a.choose_num_ctx(len(lite)))
        stats["split_draft_seconds"] = int(time.time() - t2a)
        kps = [str(k) for k in draft.get("key_points", [])]
        quotes += [str(q) for q in draft.get("notable_quotes", [])]
        if kps:
            hint = ("\n\nAn earlier, less reliable model suggested these points. Include one only if this transcript part "
                    "states it, with exact evidence copied from the transcript:\n" + "\n".join(f"- {k}" for k in kps))

    # 1-2. extract + ground
    parts = chunks(lite)
    for i, part in enumerate(parts, 1):
        r = chat(EXTRACT_PROMPT.format(part=i, parts=len(parts), title=title, channel=channel, text=part) + hint, CLAIM_SCHEMA)
        # Coverage pass (v2, after the 2026-09-30 gate showed ~60-75% of
        # Claude's coverage on dense content): ask what the first pass missed.
        # Its claims go through exactly the same grounding/verification.
        got = "\n".join(f"- {c.get('claim', '')}" for c in r.get("claims", []))
        r2 = chat(EXTRACT_PROMPT.format(part=i, parts=len(parts), title=title, channel=channel, text=part)
                  + "\n\nThese claims were ALREADY extracted from this part:\n" + (got or "(none)")
                  + "\nReturn ONLY substantive claims, people and quotes that are MISSING from that list "
                    "(details of study designs and results, caveats, risk/safety statements, recommendations). "
                    "Return empty lists if nothing important is missing.", CLAIM_SCHEMA, think=T("coverage"))
        stats["claims_from_coverage_pass"] += len(r2.get("claims", []))
        for k in ("claims", "quotes", "people", "themes"):
            r[k] = r.get(k, []) + r2.get(k, [])
        for c in r.get("claims", []):
            stats["claims_proposed"] += 1
            pos = ground(c.get("evidence", ""), src_loose, src_map)
            if pos is None:
                stats["claims_ungrounded"] += 1
                continue
            claims.append({"claim": c["claim"].strip(), "evidence": c["evidence"].strip(), "pos": pos})
        quotes += r.get("quotes", [])
        for p in r.get("people", []):
            name = p.get("name", "").strip()
            if name and loose(name) in src_loose and ground(p.get("evidence", ""), src_loose, src_map) is not None:
                people.append(p)
        themes += r.get("themes", [])

    # dedupe claims by evidence position
    seen, uniq = set(), []
    for c in sorted(claims, key=lambda c: c["pos"]):
        key = (c["pos"] // 200, loose(c["claim"])[:60])
        if key not in seen:
            seen.add(key); uniq.append(c)
    claims = uniq

    # 3. verify claims in batches against real source windows
    verified = []
    for b in range(0, len(claims), VERIFY_BATCH):
        batch = claims[b:b + VERIFY_BATCH]
        items = "\n\n".join(
            f"[{j}] CLAIM: {c['claim']}\nSOURCE EXCERPT: \"{body[max(0, c['pos'] - WINDOW):c['pos'] + WINDOW]}\""
            for j, c in enumerate(batch))
        res = {x["id"]: x for x in chat(VERIFY_PROMPT.format(items=items), VERIFY_SCHEMA, think=T("verify")).get("results", [])}
        for j, c in enumerate(batch):
            v = res.get(j)
            if v and v["supported"] == "yes" and not v["promotional"]:
                if v.get("transcription_suspect"):
                    c["claim"] += " [transcript term may be garbled - verify]"
                    stats["claims_transcription_suspect"] += 1
                verified.append(c)
            else:
                stats["claims_rejected_by_verifier"] += 1

    # 3b. cross-model verification (v3): a different model family must also
    # judge each surviving claim supported.
    if CROSS_VERIFY and verified:
        kept = []
        for b in range(0, len(verified), VERIFY_BATCH):
            batch = verified[b:b + VERIFY_BATCH]
            items = "\n\n".join(
                f"[{j}] CLAIM: {c['claim']}\nSOURCE EXCERPT: \"{body[max(0, c['pos'] - WINDOW):c['pos'] + WINDOW]}\""
                for j, c in enumerate(batch))
            res = {x["id"]: x for x in chat(VERIFY_PROMPT.format(items=items), VERIFY_SCHEMA, think=T("cross"),
                                            model=VERIFY_MODEL).get("results", [])}
            for j, c in enumerate(batch):
                v = res.get(j)
                if v and v["supported"] == "yes" and not v["promotional"]:
                    kept.append(c)
                else:
                    stats["claims_rejected_by_cross_verifier"] += 1
        verified = kept

    # 3c. internal-consistency check (v3): contradicting pairs are re-judged
    # against much wider source windows by the second model; any side it
    # doesn't support is dropped.
    if CROSS_VERIFY and len(verified) > 1:
        listing = "\n".join(f"[{i}] {c['claim']}" for i, c in enumerate(verified))
        pairs = chat(CONSIST_PROMPT.format(claims=listing), CONSIST_SCHEMA, think=T("consist"),
                     model=VERIFY_MODEL).get("pairs", [])
        drop = set()
        for pr in pairs[:8]:
            a, b = pr.get("a"), pr.get("b")
            if not (isinstance(a, int) and isinstance(b, int) and 0 <= a < len(verified)
                    and 0 <= b < len(verified)) or a == b:
                continue
            ca, cb = verified[a], verified[b]
            sa = body[max(0, ca["pos"] - WIDE_WINDOW):ca["pos"] + WIDE_WINDOW]
            sb = body[max(0, cb["pos"] - WIDE_WINDOW):cb["pos"] + WIDE_WINDOW]
            r = chat(RESOLVE_PROMPT.format(a=ca["claim"], sa=sa, b=cb["claim"], sb=sb), RESOLVE_SCHEMA,
                     think=T("resolve"), model=VERIFY_MODEL)
            stats["contradiction_pairs_checked"] += 1
            if not r.get("a_supported"):
                drop.add(a)
            if not r.get("b_supported"):
                drop.add(b)
        stats["claims_dropped_by_consistency"] = len(drop)
        verified = [c for i, c in enumerate(verified) if i not in drop]
    stats["claims_verified"] = len(verified)

    # quotes: exact-substring gate first, then coherence/promo
    q_exact, q_dropped = verify_and_filter_quotes(list(dict.fromkeys(quotes)), body)
    q_exact = [q for q in q_exact if 12 <= len(q.split()) <= 80]
    # Drop a quote already contained in a longer kept quote (split variant
    # pools qwen + gemma quotes, which often overlap - found 2026-10-01).
    q_exact = sorted(dict.fromkeys(q_exact), key=len, reverse=True)
    q_exact = [q for i, q in enumerate(q_exact) if not any(loose(q) in loose(o) for o in q_exact[:i])]
    stats["quotes_proposed"], stats["quotes_not_verbatim"] = len(quotes), q_dropped
    good_quotes = []
    if q_exact:
        items = "\n".join(f"[{j}] \"{q}\"" for j, q in enumerate(q_exact))
        res = {x["id"]: x for x in chat(QUOTE_PROMPT.format(items=items), QUOTE_SCHEMA, think=T("quotes")).get("results", [])}
        good_quotes = [q for j, q in enumerate(q_exact) if res.get(j, {}).get("coherent") and not res.get(j, {}).get("promotional")]
    stats["quotes_kept"] = len(good_quotes)

    # 4. relevance, majority of 3 votes
    claim_list = "\n".join(f"- {c['claim']}" for c in verified[:15]) or "(none)"
    votes = [chat(REL_PROMPT.format(title=title, channel=channel, sample=sample, n=len(verified), claims=claim_list),
                  REL_SCHEMA, temperature=0.7)["relevant"] for _ in range(RELEVANCE_VOTES)]
    relevant = sum(votes) * 2 > len(votes)
    stats["relevance_votes_yes"] = sum(votes)

    # 5. density
    density = density_rule(len(verified), len(lite))

    result = {"title": title, "channel": channel, "header": header, "relevant": relevant, "density": density,
              "stats": dict(stats), "lite_len": len(lite), "content_type": content_type}
    if not relevant or not verified:
        result["status"] = "skipped-irrelevant" if not relevant else "no-substance"
        return result

    # 6. compose from verified claims only
    max_kp, max_q = DEPTH[density]
    # Long, dense sources need more points than the density default allows:
    # the 2026-10-01 fast gate filled 16 slots before reaching the second
    # half of a podcast (its core thesis). Scale with verified claims, cap 24.
    max_kp = min(24, max(max_kp, len(verified) // 2))
    claim_txt = "\n".join(f"[{i}] {c['claim']}  (source: \"{c['evidence']}\")" for i, c in enumerate(verified))
    all_allowed = claim_txt + " " + title + " " + json.dumps(header)

    def compose_and_validate():
        comp = chat(COMPOSE_PROMPT.format(title=title, channel=channel, kind=kind, density=density, max_kp=max_kp,
                                          claims=claim_txt), COMPOSE_SCHEMA, num_predict=3000, think=T("compose"))
        kps, rejected, cited_ids, recovered = [], [], set(), 0
        for kp in comp.get("key_points", [])[:max_kp]:
            kp["text"] = strip_cites(kp.get("text", ""))
            ids = [i for i in kp.get("claim_ids", []) if isinstance(i, int) and 0 <= i < len(verified)]
            if not ids:
                # Model omitted citations: recover them by word overlap with the
                # verified claims (still grounded - the point must closely match a
                # verified claim, and its numbers are then checked against it).
                kw = set(loose(kp["text"]).split())
                scored = sorted(((len(kw & set(loose(c["claim"]).split())) / max(len(kw), 1), i)
                                 for i, c in enumerate(verified)), reverse=True)
                ids = [i for sc, i in scored[:3] if sc >= 0.4]
                recovered += bool(ids)
            cited = " ".join(verified[i]["claim"] + " " + verified[i]["evidence"] for i in ids)
            if ids and numbers_ok(kp["text"], cited):
                kps.append(kp["text"].strip())
                cited_ids.update(ids)
            else:
                rejected.append({"text": kp.get("text"), "claim_ids": kp.get("claim_ids"),
                                 "reason": "no matching verified claim" if not ids else "number not in cited claims"})
        return comp, kps, rejected, cited_ids, recovered

    comp, key_points, rejected_kps, cited_ids, recovered = compose_and_validate()
    # Intermittent bad compose output (2026-10-01: a production run rejected 8
    # of 13 key points; a re-run of the same item rejected 0). If most points
    # fail grounding, compose once more and keep whichever kept more points.
    if len(rejected_kps) >= max(3, len(key_points)):
        stats["compose_retried"] += 1
        retry = compose_and_validate()
        if len(retry[1]) > len(key_points):
            comp, key_points, rejected_kps, cited_ids, recovered = retry
    stats["key_points_rejected"] += len(rejected_kps)
    stats["key_points_citations_recovered"] += recovered
    if rejected_kps:
        stats["kp_reject_reasons"] = dict(Counter(r["reason"] for r in rejected_kps))

    # Coverage-balance floor: if a third of the transcript has 2+ verified
    # claims but no key point cites any of them, add its first claim verbatim
    # (already twice-verified). Stops compose favouring the opening section.
    if verified:
        span = max(len(body), 1)
        for third in range(3):
            lo, hi = span * third / 3, span * (third + 1) / 3
            idx = [i for i, c in enumerate(verified) if lo <= c["pos"] < hi]
            if len(idx) >= 2 and not cited_ids.intersection(idx):
                key_points.append(strip_cites(verified[idx[0]]["claim"].replace(" [transcript term may be garbled - verify]", "")))
                cited_ids.add(idx[0])
                stats["balance_points_added"] += 1

    # Mental-health floor (v3): the 2026-10-01 gate saw verified mental-health
    # claims dropped at compose time in favour of physical ones. CLAUDE.md
    # treats mental health as first-class, so if any verified claim is about it
    # and no key point covers it, the best such claim is added verbatim (its
    # text is already twice-verified, so this adds no new risk).
    # Same floor for injury/safety content (head trauma is directly relevant to
    # this vault's documented concussion history; the gate saw it dropped too).
    for name, rx in (("mental_health", MH_RE), ("safety", SAFETY_RE)):
        def _covered(text: str) -> bool:
            # A key point already stating the same thing (>=60% word overlap)
            # counts as coverage even without the keyword - avoids near-
            # duplicates like "...may prevent X" + "There is a risk ... X".
            w = set(loose(text).split())
            return any(len(w & set(loose(k).split())) / max(len(w), 1) >= 0.6 for k in key_points)

        hits = [c for c in verified if rx.search(c["claim"]) and not _covered(c["claim"])]
        if hits and not any(rx.search(k) for k in key_points):
            key_points += [strip_cites(c["claim"].replace(" [transcript term may be garbled - verify]", "")) for c in hits[:2]]
            stats[f"{name}_points_added"] = min(2, len(hits))

    def clean(s: str) -> str:
        sents = re.split(r"(?<=[.!?])\s+", strip_cites(s))
        kept = [x for x in sents if numbers_ok(x, all_allowed)]
        stats["summary_sentences_rejected"] += len(sents) - len(kept)
        return " ".join(kept)

    # Risk screen: prompts for later checking, labelled as unverified. Numbers
    # must still come from the verified claims.
    risk = chat(RISK_PROMPT.format(claims=claim_txt), RISK_SCHEMA, think=T("risk")).get("flags", [])
    risk_flags = [f"{strip_cites(x)} (model risk flag, unverified)" for x in risk[:5] if strip_cites(x) and numbers_ok(strip_cites(x), claim_txt)]

    known = existing_people()
    ppl, seen_names = [], set()
    for p in people:
        # Normalize titles so "Dr. James Hoffman" and "James Hoffman" dedupe;
        # single-word names only kept if they match an existing People note.
        k = loose(re.sub(r"^(dr|prof|professor|doctor|mr|ms|mrs)\.?\s+", "", p["name"].strip(), flags=re.I))
        if k in seen_names or (len(k.split()) < 2 and k not in known):
            continue
        seen_names.add(k)
        match = k if k in known else None
        if match is None:
            # Speech-to-text often garbles names ("Peter Artea" for Peter
            # Attia): link a close match to an existing People note, flagged.
            close = difflib.get_close_matches(k, list(known), n=1, cutoff=0.78)  # real garbles scored 0.80-0.96; different people <=0.62 (tested 2026-10-01)
            match = close[0] if close else None
        if match and match != k:
            link = f"[[People/{known[match]}]] (transcript spelling: \"{p['name']}\")"
        else:
            link = f"[[People/{known[match]}]]" if match else p["name"]
        ppl.append((p["name"], link, p.get("context", "").strip(), match is not None))

    key_points = [flag_compound_garbles(k) for k in key_points]
    result.update(status="ok", for_future_claude=clean(comp.get("for_future_claude", "")), tldr=clean(comp.get("tldr", "")),
                  key_points=key_points, quotes=good_quotes[:max_q], people=ppl,
                  themes=list(dict.fromkeys((comp.get("themes") or themes)))[:6],
                  follow_up=[clean(x) for x in comp.get("follow_up", [])[:4] if clean(x)] + risk_flags,
                  rejected_key_points=rejected_kps, stats=dict(stats))
    return result


# ---------------------------------------------------------------- output

def slug(s: str) -> str:
    s = re.sub(r'[\\/:*?"<>|#\[\]^]', "", s).strip()
    return re.sub(r"\s+", " ", s)[:120]


def yaml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def render(res: dict, kind: str, item_id: str) -> str:
    h = res["header"]
    method = h.get("transcript_method", "")
    src = "whisper-local" if "whisper" in method else "official-captions"
    tags = ["research", kind] + [re.sub(r"[^a-z0-9-]", "", t.lower().replace(" ", "-")) for t in res["themes"]]
    fm = ["---", f"date: {date.today().isoformat()}", f"type: {kind}"]
    if kind == "youtube":
        fm += [f"video-id: {item_id}", f"video-url: {h.get('url', 'https://www.youtube.com/watch?v=' + item_id)}"]
        up = h.get("upload_date", "")
        published = f"{up[:4]}-{up[4:6]}-{up[6:8]}" if len(up) == 8 else up
    else:
        fm += [f"episode-guid: {item_id}", f"episode-url: {h.get('audio_url', '')}"]
        published = h.get("pub_date", "")
    fm += [f"title: {yaml_str(res['title'])}", f"channel: {yaml_str(res['channel'])}", f"published: {yaml_str(published)}",
           f"tags: [{', '.join(dict.fromkeys(t for t in tags if t))}]", "ai-first: true", "cost-usd: 0",
           f"signal_density: {res['density']}", "signal_density_method: verified-claim-rate", f"transcript_source: {src}",
           f"finished_by: {finished_by_label()}", f"cross_verified_by: {VERIFY_MODEL if CROSS_VERIFY else 'none'}",
           f"content_type: {res.get('content_type', 'unknown')}", "trust_tier: local-verified", "---", ""]
    out = fm + [
        "> [!info] Finished by model pipeline (Part 2b)" if is_gemini(MODEL) else "> [!info] Finished locally (Part 2b-local)",
        f"> Written by `{MODEL}` behind programmatic gates: every Key Point cites claims whose evidence was found verbatim in the transcript, then checked by {MODEL} and re-checked by {VERIFY_MODEL if CROSS_VERIFY else "no second model"} (plus a contradiction check); quotes are exact substrings. Not reviewed by Claude - lower trust than a Claude-finished note. Concept-linking pending.",
        "", "## For future Claude", res["for_future_claude"], "", "## TL;DR", res["tldr"], "", "## Key Points"]
    out += [f"- {k}" for k in res["key_points"]] or ["- (none survived verification)"]
    out += ["", "## Notable Quotes"]
    out += [f"> \"{q}\"\n" for q in res["quotes"]] or ["- None passed both the verbatim and coherence checks."]
    out += ["", "## Themes & Topics"] + [f"- {t}" for t in res["themes"]]
    out += ["", "## Worth Following Up On"] + ([f"- {x}" for x in res["follow_up"]] or ["- Nothing flagged."])
    out += ["", "## Researchers & Sources Cited"]
    out += [f"- {link} - {ctx}" for _, link, ctx, _ in res["people"]] or ["- None cited."]
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", choices=["youtube", "podcast"])
    ap.add_argument("--batch-size", type=int, default=20)
    ap.add_argument("--gate", help="comma-separated ids; write to the gate dir, touch no checkpoints")
    ap.add_argument("--model", default=None)
    ap.add_argument("--variant", choices=["merged", "split"], default="merged")
    ap.add_argument("--gate-suffix", default="")
    ap.add_argument("--gate-route", action="store_true", help="in gate mode, route conversations like production does")
    ap.add_argument("--routed-conversations", action="store_true",
                    help="process only items triaged 'route-claude' (conversations) - for a hosted model such as gemini:<name>")
    args = ap.parse_args()
    global MODEL
    if args.model:
        MODEL = args.model

    raw_dir = TARGETS[args.target]["raw_dir"]
    note_dir = raw_dir.parent
    processed_path, drafted_path = raw_dir / ".processed_ids.json", raw_dir / ".drafted_ids.json"

    files = {extract_video_id(p.name): p for p in raw_dir.glob("*_full.txt") if extract_video_id(p.name)}

    def already_done(vid: str, processed: dict) -> bool:
        """Podcasts are drafted under the filename hash but older finishing
        runs keyed .processed_ids.json by episode_guid - check both."""
        if vid in processed:
            return True
        if args.target == "podcast" and vid in files:
            guid = parse_header_fields(files[vid].read_text(encoding="utf-8", errors="replace")[:3000]).get("episode_guid")
            return bool(guid) and guid in processed
        return False

    if args.gate:
        ids = args.gate.split(",")
        GATE_DIR.mkdir(parents=True, exist_ok=True)
    else:
        processed, drafted = read_json(processed_path), read_json(drafted_path)
        # Only triaged items (scripts/triage_for_2b.py) are taken, priority
        # channels first, doubtful-relevance last; conversations routed to
        # Claude and triage skips are excluded.
        routed = read_json(raw_dir / ".local_2b_routing.json")
        triage = read_json(raw_dir / ".local_2b_triage.json")
        rank = {"local-priority": 0, "local": 1, "doubtful-last": 2}
        if ROUTE_CONVERSATIONS_LOCAL:
            rank["route-claude"] = 1
        if args.routed_conversations:
            rank = {"route-claude": 0}
        cand = [i for i in drafted if i in files and not already_done(i, processed)
                and (ROUTE_CONVERSATIONS_LOCAL or args.routed_conversations or i not in routed)
                and triage.get(i, {}).get("decision") in rank]
        ids = sorted(cand, key=lambda i: rank[triage[i]["decision"]])[: args.batch_size]
    log(f"=== {args.target}: {len(ids)} item(s), model={MODEL}, verify={VERIFY_MODEL if CROSS_VERIFY else 'off'}, profile={THINK_PROFILE}, "
        f"variant={args.variant}, think={THINK}, gate={bool(args.gate)}")
    if ids and not gpu_preflight():
        log("ABORT: Ollama is not running this model on the GPU (CPU fallback?) - refusing to run CPU-only")
        return 2

    for n, vid in enumerate(ids, 1):
        if vid not in files:
            log(f"[{n}/{len(ids)}] {vid}: raw file not found, skipped")
            continue
        t0 = time.time()
        try:
            res = process_one(files[vid], args.target, args.variant,
                              route_only=(not args.gate or args.gate_route) and not ROUTE_CONVERSATIONS_LOCAL
                              and not args.routed_conversations)
        except QuotaExhausted as e:
            log(f"[{n}/{len(ids)}] {vid}: STOP - {e}")
            break
        except Exception as e:
            log(f"[{n}/{len(ids)}] {vid}: FAILED {e}")
            continue
        summary = (f"status={res['status']} type={res.get('content_type')} density={res['density']} "
                   f"{res['stats']} {time.time() - t0:.0f}s")
        if args.gate:
            out = GATE_DIR / f"{vid}{args.gate_suffix}.md"
            out.write_text(render(res, args.target, vid) if res["status"] == "ok"
                           else f"{res['status']} content_type={res.get('content_type')}\n{json.dumps(res['stats'])}\n",
                           encoding="utf-8")
            (GATE_DIR / f"{vid}{args.gate_suffix}.json").write_text(json.dumps({k: v for k, v in res.items() if k != "header"}, indent=2, default=str), encoding="utf-8")
            log(f"[{n}/{len(ids)}] {vid}: {summary}")
            continue
        if res["status"] == "routed-to-claude":
            # Leave .drafted_ids.json/.processed_ids.json untouched so Claude's
            # /finish-draft-notes still picks this one up; remember the routing.
            routed = read_json(raw_dir / ".local_2b_routing.json")
            routed[vid] = {"content_type": res["content_type"], "routed": "claude", "at": date.today().isoformat()}
            write_json_atomic(raw_dir / ".local_2b_routing.json", routed)
            log(f"[{n}/{len(ids)}] {vid}: {summary}")
            continue
        processed = read_json(processed_path)  # read-modify-write per file
        entry = {"status": res["status"], "finished_by": finished_by_label(), "signal_density": res["density"]}
        if res["header"].get("episode_guid"):
            entry["episode_guid"] = res["header"]["episode_guid"]
        if res["status"] == "ok":
            path = note_dir / f"{date.today().isoformat()} - {slug(res['title'])} ({slug(res['channel'])}).md"
            path.write_text(render(res, args.target, vid), encoding="utf-8")
            new_people = [nm for nm, _, _, known in res["people"] if not known]
            entry.update(note=str(path.relative_to(VAULT_ROOT)).replace("\\", "/"), people_discovered=[nm for nm, *_ in res["people"]])
            # Tightened 2026-10-01: generic "(model risk flag, unverified)" lines
            # appear on nearly every drug-related note and flagged ~50% of output.
            # Flag only the signals audits actually found errors behind.
            flagged = res["stats"].get("claims_transcription_suspect", 0) >= 3 \
                or bool(res["stats"].get("claims_dropped_by_consistency")) \
                or any("[transcript term - possibly" in k for k in res["key_points"])
            done_local = sum(1 for v in processed.values() if isinstance(v, dict) and str(v.get("finished_by", "")).startswith("local-"))
            if flagged or done_local % AUDIT_SAMPLE_EVERY == 0:
                aq = read_json(AUDIT_QUEUE)
                aq[entry["note"]] = {"reason": "flagged" if flagged else "random-sample", "id": vid, "audited": False}
                write_json_atomic(AUDIT_QUEUE, aq)
            if new_people:
                cands = read_json(PEOPLE_CANDIDATES)
                for nm in new_people:
                    cands.setdefault(nm, []).append(entry["note"])
                write_json_atomic(PEOPLE_CANDIDATES, cands)
        processed[vid] = entry
        write_json_atomic(processed_path, processed)
        drafted = read_json(drafted_path)
        d = drafted.pop(vid, None)
        write_json_atomic(drafted_path, drafted)
        if isinstance(d, dict) and d.get("draft_file"):
            (raw_dir / d["draft_file"]).unlink(missing_ok=True)
        log(f"[{n}/{len(ids)}] {vid}: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
