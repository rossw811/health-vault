#!/usr/bin/env python3
"""Generate a static, offline dashboard (Dashboard/index.html) from Daily/ note
frontmatter. No server, no CDN, no external calls - hand-rolled SVG line charts.
Run manually, or as the last step of /oura-sync.
"""

import re
from datetime import datetime
from pathlib import Path

import yaml

VAULT_ROOT = Path(__file__).resolve().parent.parent
DAILY_DIR = VAULT_ROOT / "Daily"
OUTPUT = VAULT_ROOT / "Dashboard" / "index.html"

METRICS = [
    ("readiness_score", "Readiness"),
    ("sleep_score", "Sleep Score"),
    ("average_hrv", "Average HRV"),
    ("resting_hr", "Resting HR"),
    ("activity_score", "Activity Score"),
    ("steps", "Steps"),
    ("sleep_total_hours", "Sleep Total (hrs)"),
    ("sleep_efficiency", "Sleep Efficiency"),
]


def load_daily_notes():
    notes = []
    if not DAILY_DIR.exists():
        return notes
    for path in sorted(DAILY_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
        if not match:
            continue
        try:
            fm = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            continue
        date_str = fm.get("date") or path.stem
        try:
            date = datetime.strptime(str(date_str), "%Y-%m-%d")
        except ValueError:
            continue
        notes.append({"date": date, "fm": fm})
    notes.sort(key=lambda n: n["date"])
    return notes


def svg_line_chart(values, dates, label, width=760, height=160, pad=28):
    points = [(d, v) for d, v in zip(dates, values) if isinstance(v, (int, float))]
    if not points:
        return f'<div class="chart-empty">No data yet for {label}</div>'
    vals = [v for _, v in points]
    vmin, vmax = min(vals), max(vals)
    if vmin == vmax:
        vmin -= 1
        vmax += 1
    span_x = max(len(points) - 1, 1)

    def x_at(i):
        return pad + (i / span_x) * (width - 2 * pad)

    def y_at(v):
        return height - pad - ((v - vmin) / (vmax - vmin)) * (height - 2 * pad)

    path_d = " ".join(
        f"{'M' if i == 0 else 'L'}{x_at(i):.1f},{y_at(v):.1f}"
        for i, (_, v) in enumerate(points)
    )
    last_x, last_v = x_at(len(points) - 1), y_at(points[-1][1])
    grid = "".join(
        f'<line x1="{pad}" y1="{y}" x2="{width - pad}" y2="{y}" class="grid" />'
        for y in (pad, height / 2, height - pad)
    )
    return f"""
<div class="chart">
  <div class="chart-title">{label} <span class="chart-latest">{points[-1][1]}</span></div>
  <svg viewBox="0 0 {width} {height}" width="100%" height="{height}">
    {grid}
    <path d="{path_d}" class="line" fill="none" />
    <circle cx="{last_x:.1f}" cy="{last_v:.1f}" r="4" class="dot" />
  </svg>
</div>"""


def render_protocols(notes):
    if not notes:
        return "<p>No daily notes yet.</p>"
    latest = notes[-1]["fm"]
    protocols = latest.get("active_protocols") or []
    if not protocols:
        return "<p>No active protocols logged.</p>"
    items = "".join(f"<li>{p}</li>" for p in protocols)
    return f"<ul>{items}</ul>"


def main():
    notes = load_daily_notes()
    dates = [n["date"].strftime("%Y-%m-%d") for n in notes]
    charts = "\n".join(
        svg_line_chart([n["fm"].get(key) for n in notes], dates, label)
        for key, label in METRICS
    )
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Health Vault Dashboard</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: system-ui, sans-serif; max-width: 820px; margin: 2rem auto; padding: 0 1rem;
          background: Canvas; color: CanvasText; }}
  h1 {{ font-size: 1.4rem; }}
  .chart {{ margin-bottom: 1.5rem; }}
  .chart-title {{ font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.04em;
                  opacity: 0.7; margin-bottom: 0.25rem; }}
  .chart-latest {{ font-size: 1.1rem; font-weight: 600; opacity: 1; margin-left: 0.5rem; }}
  .chart-empty {{ opacity: 0.5; font-size: 0.85rem; margin-bottom: 1rem; }}
  .line {{ stroke: currentColor; stroke-width: 2; opacity: 0.8; }}
  .dot {{ fill: currentColor; }}
  .grid {{ stroke: currentColor; stroke-opacity: 0.12; stroke-width: 1; }}
  footer {{ font-size: 0.75rem; opacity: 0.5; margin-top: 2rem; }}
</style></head>
<body>
  <h1>Health Vault Dashboard</h1>
  {charts}
  <h2>Active Protocols</h2>
  {render_protocols(notes)}
  <footer>Generated {generated_at} from {len(notes)} daily note(s). Regenerate with /oura-sync or `python scripts/generate_dashboard.py`.</footer>
</body></html>
"""
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"Wrote {OUTPUT} from {len(notes)} daily note(s)")


if __name__ == "__main__":
    main()
