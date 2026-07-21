---
description: Track every marker across all Bloodwork/ panels over time - direction of change, whether it's moving toward/past a reference-range boundary, and nearby Oura/protocol context around each draw date. Requires 2+ panels; says so plainly if there's only one.
category: research
---

Execute `/bloodwork-trend [marker name (optional)]`:

## 1. Check there's enough to trend
Read every `Bloodwork/*.md` note. If there's only one (or zero), say so plainly and stop — "trend" requires at least two draws; don't manufacture a trend narrative from a single data point.

## 2. Build the per-marker timeline
For every marker appearing in 2+ panels (or just the one named in the argument, if given): list its value at each draw date in order. Compute:
- **Direction**: rising / falling / stable (define "stable" as within a small tolerance you state explicitly, don't hand-wave it).
- **Reference-range proximity**: is it moving toward, away from, or has it crossed a boundary between draws? Use each draw's own stated reference range (ranges can differ between labs/draws — don't assume they're identical, check).
- Do NOT compute a statistical trend line or slope from 2-3 points and present it as if it were a real regression — with this few points per marker, "direction between consecutive draws" is honest; a fitted trend line is not.

## 3. Cross-reference nearby Oura/protocol context
For each draw date, pull that date's (and surrounding ~7 days') `Daily/` frontmatter if it exists (readiness, HRV, sleep, stress) and any `active_protocols` that were active around that time — this is context to note alongside a marker's movement, not a claimed causal link. If Oura data doesn't cover that period, say so rather than leaving it ambiguous.

## 4. Write the note
`Synthesis/Bloodwork Trends - YYYY-MM-DD.md` (`type: synthesis`, tags `[synthesis, bloodwork, trends]`, sources listing every panel note used):
- `## For future Claude` preamble: how many panels, date range, how many markers had 2+ data points to trend.
- Per-marker section (or just the one requested): value-over-time table, direction, reference-range proximity, nearby Oura/protocol context if any.
- `## Markers moving toward or past a boundary` — pulled into one place regardless of current flag status, since a "normal" marker heading toward the edge of its range is more actionable to surface than a stable one deep in-range.
- `## Insufficient data yet` — markers that only appear in one panel so far, explicitly listed rather than silently omitted.

## 5. Summary
Panels used, markers trended, any moving toward/past a boundary, note path.

**Anti-fabrication:** never fit or imply a statistical trend from fewer than ~5 points; "direction between draws" is the honest claim at typical bloodwork frequency (a few panels a year). Never assert a causal link to a protocol or Oura metric — context, not causation.
