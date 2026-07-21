---
description: Find books relevant to a topic or author using ONLY legitimate sources - Google Books previews, Project Gutenberg public-domain full texts, and open-access academic book repositories (NCBI Bookshelf, DOAB). Never fetches unauthorized full text.
category: research
---

Execute `/book-discovery [topic or author]`:

## 1. Resolve the query
A topic (e.g. "concussion recovery protocols") or an author name (e.g. one already tracked in `People/`). If none, ask.

## 2. Search legitimate sources only
- **Google Books API** (`https://www.googleapis.com/books/v1/volumes?q=<query>`, no key needed for basic search): title, author, description, ISBN, `previewLink`.
- **Project Gutenberg** (`https://gutenberg.org/ebooks/search/?query=<query>`): public-domain full texts — mostly relevant for foundational/historical physiology, psychology, or nutrition works, rarely modern releases.
- **NCBI Bookshelf** (E-utilities `esearch`/`esummary` against the `books` database) and **DOAB** (Directory of Open Access Books, `https://doabooks.org/`): open-access academic monographs, genuinely full-text and legal.

## 3. Classify each result by availability
- `public-domain-fulltext` (Gutenberg) or `open-access-fulltext` (NCBI Bookshelf/DOAB item confirmed open-access): fetch the real text.
- `preview-only` (everything else — this is most modern health/fitness/performance books): do not fetch or store full text under any circumstance, regardless of what third-party sites might claim to offer.

## 4. Write the source note
`Sources/Books/<title>.md` (raw-source schema like other `Sources/` entries: `type: source`, `tags: [source, book]`, `availability`, `isbn`, `source_url`):
- **Full text available**: produce an `/obsidian-distill`-style condensed note — every claim tagged `(src: Bn)` back to a numbered source block from the actual text, so it's auditable against the original.
- **Preview-only**: do NOT fabricate a distillation from the preview snippet alone. Instead run `/research` on the book's actual claims/reception (reviews, author interviews discussing the book's thesis, its official description) and note where to legitimately access the full book (library catalog search link, publisher/purchase page) — never a scraped or unauthorized copy.

## 5. Cross-link
If the author matches an existing `People/<name>.md` note, link both directions — the book becomes part of that person's tracked body of work in the Web, same as their video content.

## 6. Summary
Books found, split by availability tier, which got a full distillation vs. citation-only treatment, and any cross-links made to existing `People/` notes.

**Hard boundary, not a preference**: Internet Archive's "controlled digital lending" is deliberately excluded here — its legal status is genuinely contested (Internet Archive lost the Hachette appeal in 2024) — do not use it as a source even if it appears to offer a convenient full-text copy.

**Anti-fabrication:** never invent a book's existence, contents, or claims. If nothing legitimate turns up for a query, say so rather than padding results. See `references/ai-first-rules.md` in the obsidian-second-brain skill root.
