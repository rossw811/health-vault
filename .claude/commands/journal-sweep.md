---
description: Sweep a specific journal or topic for real, legitimately-accessible studies (abstracts, open-access full text via PubMed/OpenAlex - never scraping paywalled full text) and critique their methodology, reusing /research --academic's machinery. Scoped down from "download every journal" to what's actually legitimate, same legal-boundary discipline as /book-discovery.
category: research
---

Execute `/journal-sweep [journal name | topic] [--journal "NEJM" | --topic "..."]`:

## 1. Scope check before anything else
"Every journal and its studies" is not a legitimate or achievable scope in one pass - most journals (NEJM, Lancet, JAMA, etc.) are paywalled for full text, and scraping/downloading full paywalled articles is exactly the kind of unauthorized-access risk this vault already treats as a hard boundary elsewhere (`/book-discovery`'s Internet Archive exclusion, this session's third-party-transcript-site exclusion after a real takedown was found). This command works with **abstracts and open-access full text only** - real, legitimate, freely available content - never a paywalled full-text scrape.

## 2. Resolve scope for this run
Either a specific journal (search within it for this vault's topic areas) or a specific topic (search across journals). Use `/research --academic` (OpenAlex/arXiv/Crossref-backed, already built) as the primary mechanism - it already surfaces abstracts, DOIs, citation counts, and (when available) open-access links. Do not attempt "the entire archive of NEJM" in one run - scope to a specific, stated query (a topic, a date range, a specific claim needing verification) each time this is invoked, and say what the scope was in the output.

## 3. For each real result found
- **Abstract-only (most results, especially from paywalled journals)**: cite title/authors/year/DOI/journal, summarize the abstract's own claims, and critique what's assessable from the abstract alone (sample size if stated, study design if stated, whether the abstract's own conclusion matches its stated methodology) - do not fabricate methodology detail the abstract doesn't actually state.
- **Open-access full text (PMC, DOAJ-indexed, or the journal's own open-access articles)**: fetch and read the real full text (WebFetch/defuddle), critique properly - actual sample size, actual methodology limitations, whether the result generalizes to the claim being evaluated. This is the same rigor `/concept-audit`'s study-verification step already applies. **`pmc.ncbi.nlm.nih.gov` (NIH's own PubMed Central) is reliably fetchable via WebFetch directly** (confirmed 2026-08-01) - prefer it over `defuddle`, which gets Cloudflare-bot-blocked on some NCBI pages that WebFetch handles fine. If a legitimately-open-access article is only findable via a mirror site (ResearchGate, Academia.edu) that 403s, check whether the same article exists on PMC/the journal's own open-access page before treating it as inaccessible - the mirror failing isn't the same as the source being unreachable.

## 4. Write the output
`Research/Web/YYYY-MM-DD - Journal Sweep - <scope>.md` (`type: research`, `tags: [research, journal-sweep]`, real `sources:` list of DOIs):
- `## For future Claude` preamble stating the exact scope of this run (this journal/topic, not "comprehensive").
- Per study: citation, abstract-only vs. full-text-critiqued, findings, methodology critique, evidence-quality tag (same Verified/Contradicted/Inconclusive framing `/concept-audit` uses where applicable).
- **When studies on the same question conflict, weight the newer one more heavily** - by default (methodology, sample sizes, and priors tend to improve over time), not automatically ("newer" isn't infallible, but it's the reasonable default absent a specific reason the older study is actually more rigorous). Flag explicitly when an older, frequently-cited study has since been superseded or contradicted by more recent work, rather than presenting both as equally current.
- **No results found is a point-in-time fact, not a permanent verdict (added 2026-08-02)**, same convention as `/concept-audit`: if a topic/claim being swept - especially one whose only existing source in this vault is a podcast, YouTube video, or other non-academic source - turns up no real academic literature, tag it **No evidence found (as of YYYY-MM-DD)** rather than "no evidence exists," and list it in `## Flagged for re-research` below. Absence of published research today doesn't mean it'll still be absent later.
- `## What this run did NOT cover` - explicit, so no one mistakes a scoped sweep for exhaustive coverage.
- `## Flagged for re-research` - every claim tagged `No evidence found (as of YYYY-MM-DD)` this run, with the claim, the date, and which non-academic source (if any) it came from.

## 5. Cross-link
If a study is directly relevant to an existing `Concepts/` note or a documented family-history/personal-profile item, cross-link it there too - this is meant to feed the same Concept-note-as-primary-reading-layer principle the rest of this vault already uses, not create an isolated pile of journal notes.

## 6. Summary
Scope of this run, studies found (abstract-only vs. full-text), key findings, methodology concerns flagged, what wasn't covered.

**Anti-fabrication:** never invent a study's methodology, sample size, or conclusion beyond what the actual abstract/full-text says. Never fetch or store paywalled full text under any circumstance - this is a hard boundary, not a preference, same as `/book-discovery`.
