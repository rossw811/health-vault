---
description: Sweep a creator's blog/Substack/newsletter for real content - full distillation of free posts, citation-only for paywalled ones. The text-based sibling of /journal-sweep and /institution-sweep, reusing the same legitimate-access-only discipline.
category: research
---

Execute `/blog-sweep [person | blog/Substack URL]`:

## 1. Resolve the blog/newsletter
If given a person already tracked in `People/`, check their note first for an existing blog/Substack URL. If none documented, one targeted WebSearch (`"<name>" substack` or `"<name>" blog newsletter`) - verify it's actually theirs before using it (matching name/bio, not a same-named unrelated writer).

If the person genuinely has no blog/newsletter (many creators only publish video), say so plainly and stop - don't force this command onto every tracked person.

## 2. Enumerate posts
**Substack publications expose a real RSS feed** at `<publication>.substack.com/feed` - use it instead of scraping the archive page. It gives title/link/pubDate for every post, plus (for free posts) often the full content inline; paywalled posts typically show only a truncated teaser in the feed itself, which is a reliable signal for step 3's free-vs-paywalled split without needing to visit each post first.

For a non-Substack personal blog/newsletter without RSS, fetch the site's archive/post-list page directly (WebFetch/defuddle) to enumerate posts.

**Scope, same principle as `/journal-sweep`**: don't attempt "every post this person has ever written" in one pass. Default to the most recent N posts (state N in the output) or a specific topic search within the blog if the user named one - say what the actual scope was, never imply exhaustive coverage.

## 3. For each post found
- **Free/public post**: fetch the real full content (WebFetch/defuddle, or straight from the RSS feed's inline content if present) and distill it the same way `/book-discovery`'s public-domain path works - tagged claims, verbatim quotes where they matter, never paraphrased-as-verbatim.
- **Paywalled/subscriber-only post**: citation only (title, date, URL, the free teaser text the feed/page itself shows) - never attempt to bypass or work around a paywall. Same hard boundary as `/journal-sweep`'s paywalled-journal handling and `/book-discovery`'s preview-only path.

## 4. Write the output
`Research/Web/YYYY-MM-DD - Blog Sweep - <person/publication>.md` (`type: research`, `tags: [research, blog-sweep]`):
- `## For future Claude` preamble stating the exact scope (this blog, these N most recent posts or this topic - not "comprehensive").
- Per post: citation, free-full-text vs. paywalled-citation-only, distilled claims with tags, notable verbatim quotes where relevant.
- `## What this run did NOT cover` - explicit, matching every other scoped-sweep command in this vault.

## 5. Cross-link
Link relevant posts to existing `Concepts/`/`People/` notes - same principle as `/journal-sweep`'s step 5, this feeds the vault's existing knowledge graph rather than creating an isolated pile of blog notes. If the post directly extends something a person already discussed on video (per their `People/` note), note that connection explicitly.

## 6. Summary
Blog/publication identified (or "no blog exists"), scope of this run, free vs. paywalled split, key findings, what wasn't covered.

**Anti-fabrication:** never invent a post's content beyond what was actually fetched, and never attempt to access paywalled content through any workaround - this is a hard boundary, not a preference, same as `/journal-sweep` and `/book-discovery`.
