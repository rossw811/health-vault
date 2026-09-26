#!/usr/bin/env python3
"""Local semantic search over the vault - a discovery layer, not an answer layer.

Embeds every note (chunked at `##` heading level) with a local Ollama model
and stores vectors in a local sqlite-vec index. Returns ranked (note path,
section heading, snippet) results - never full chunk text meant to be quoted
from, and never an LLM-generated answer. The point is to catch notes that
exist but that keyword grep/glob misses (synonyms, paraphrase, conceptual-
not-lexical matches) - the actual answer still requires a full Read of
whatever this surfaces, same anti-fabrication discipline as every other
vault command. See ideas.md's 2026-08-20 entry for the full design rationale.

Usage:
    python scripts/vault_search.py --reindex           # (re)build the index
    python scripts/vault_search.py --reindex --changed # only re-embed changed files
    python scripts/vault_search.py "query text" [-k N] # search, default k=8
"""
import argparse
import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path

# Windows consoles default to cp1252, which can't encode em-dashes/arrows that
# are common in vault note content - force UTF-8 stdout so results print cleanly
# instead of crashing mid-result on whichever note happens to hit an unmappable char.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import requests
import sqlite_vec

VAULT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = VAULT_ROOT / ".vault_search_index.sqlite3"
OLLAMA_URL = "http://localhost:11434/api/embed"
EMBED_MODEL = "nomic-embed-text"
EMBED_DIM = 768

# Only index real vault content - never Sources/ (raw material, not synthesized
# knowledge; would just duplicate/dilute results with unprocessed transcripts)
# and never Raw/ (same reason, plus these are gitignored bulk text dumps).
INDEXED_DIRS = ["Concepts", "Protocols", "Optimization", "People", "Synthesis",
                 "Research/YouTube", "Research/Podcasts", "Research/Web", "Bloodwork"]
EXCLUDED_NAME_PARTS = {".drafts", ".lite", "Raw", ".state"}


def iter_notes():
    for rel in INDEXED_DIRS:
        d = VAULT_ROOT / rel
        if not d.exists():
            continue
        for p in d.rglob("*.md"):
            if EXCLUDED_NAME_PARTS & set(p.parts):
                continue
            yield p


def chunk_note(text: str, path: Path):
    """Split on `## ` headings. Frontmatter + preamble (before the first ##)
    becomes its own chunk labeled with the note title so it's still searchable."""
    lines = text.splitlines()
    chunks = []
    current_heading = path.stem
    current_lines = []

    def flush():
        body = "\n".join(current_lines).strip()
        if body:
            chunks.append((current_heading, body))

    for line in lines:
        if line.startswith("## "):
            flush()
            current_heading = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)
    flush()
    return chunks


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def embed_batch(texts: list) -> list:
    resp = requests.post(OLLAMA_URL, json={"model": EMBED_MODEL, "input": texts}, timeout=120)
    resp.raise_for_status()
    return resp.json()["embeddings"]


def connect_db():
    conn = sqlite3.connect(DB_PATH)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY,
            path TEXT NOT NULL,
            heading TEXT NOT NULL,
            snippet TEXT NOT NULL,
            file_hash TEXT NOT NULL
        )
    """)
    conn.execute(f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vectors USING vec0(
            embedding FLOAT[{EMBED_DIM}]
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS file_hashes (
            path TEXT PRIMARY KEY,
            file_hash TEXT NOT NULL
        )
    """)
    return conn


def reindex(only_changed: bool):
    conn = connect_db()
    known_hashes = dict(conn.execute("SELECT path, file_hash FROM file_hashes").fetchall())

    notes = list(iter_notes())
    to_process = []
    for path in notes:
        rel = str(path.relative_to(VAULT_ROOT))
        h = file_hash(path)
        if only_changed and known_hashes.get(rel) == h:
            continue
        to_process.append((path, rel, h))

    print(f"{len(notes)} notes found, {len(to_process)} to (re)embed "
          f"({'changed only' if only_changed else 'full reindex'})")

    processed = 0
    for path, rel, h in to_process:
        text = path.read_text(encoding="utf-8", errors="replace")
        chunk_list = chunk_note(text, path)
        if not chunk_list:
            continue

        conn.execute("DELETE FROM chunks WHERE path = ?", (rel,))
        old_ids = [r[0] for r in conn.execute(
            "SELECT id FROM chunks WHERE path = ?", (rel,)).fetchall()]

        texts = [f"{heading}\n\n{body[:2000]}" for heading, body in chunk_list]
        try:
            embeddings = embed_batch(texts)
        except Exception as e:
            print(f"  SKIP {rel}: embed failed ({e})")
            continue

        for (heading, body), emb in zip(chunk_list, embeddings):
            snippet = body[:500]
            cur = conn.execute(
                "INSERT INTO chunks (path, heading, snippet, file_hash) VALUES (?, ?, ?, ?)",
                (rel, heading, snippet, h),
            )
            row_id = cur.lastrowid
            conn.execute(
                "INSERT INTO chunk_vectors (rowid, embedding) VALUES (?, ?)",
                (row_id, sqlite_vec.serialize_float32(emb)),
            )

        conn.execute(
            "INSERT INTO file_hashes (path, file_hash) VALUES (?, ?) "
            "ON CONFLICT(path) DO UPDATE SET file_hash = excluded.file_hash",
            (rel, h),
        )
        conn.commit()
        processed += 1
        if processed % 20 == 0:
            print(f"  {processed}/{len(to_process)}...")

    # Clean up entries for deleted files
    all_rels = {str(p.relative_to(VAULT_ROOT)) for p in notes}
    stale = [row[0] for row in conn.execute("SELECT DISTINCT path FROM chunks").fetchall()
             if row[0] not in all_rels]
    for rel in stale:
        conn.execute("DELETE FROM chunks WHERE path = ?", (rel,))
        conn.execute("DELETE FROM file_hashes WHERE path = ?", (rel,))
    if stale:
        conn.commit()
        print(f"Removed {len(stale)} stale file(s) no longer in the vault")

    total_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    print(f"Done. {processed} file(s) embedded this run, {total_chunks} chunks total in index.")
    conn.close()


def search(query: str, k: int):
    if not DB_PATH.exists():
        print("No index found. Run --reindex first.", file=sys.stderr)
        sys.exit(1)
    conn = connect_db()
    try:
        query_emb = embed_batch([query])[0]
    except Exception as e:
        print(f"Embedding query failed: {e}", file=sys.stderr)
        sys.exit(1)

    rows = conn.execute(
        """
        SELECT c.path, c.heading, c.snippet, v.distance
        FROM chunk_vectors v
        JOIN chunks c ON c.id = v.rowid
        WHERE v.embedding MATCH ? AND k = ?
        ORDER BY v.distance
        """,
        (sqlite_vec.serialize_float32(query_emb), k),
    ).fetchall()

    results = []
    for path, heading, snippet, distance in rows:
        results.append({
            "path": path,
            "heading": heading,
            "snippet": snippet,
            "distance": round(distance, 4),
        })
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("query", nargs="?", help="search query")
    parser.add_argument("--reindex", action="store_true", help="(re)build the index")
    parser.add_argument("--changed", action="store_true", help="with --reindex, only re-embed changed files")
    parser.add_argument("-k", type=int, default=8, help="number of results (default 8)")
    parser.add_argument("--json", action="store_true", help="output raw JSON instead of formatted text")
    args = parser.parse_args()

    if args.reindex:
        start = time.time()
        reindex(only_changed=args.changed)
        print(f"({time.time() - start:.1f}s)")
        return

    if not args.query:
        parser.error("provide a query, or use --reindex to build the index")

    results = search(args.query, args.k)
    if args.json:
        print(json.dumps(results, indent=2))
        return

    if not results:
        print("No results.")
        return
    for r in results:
        print(f"[{r['distance']}] {r['path']}  —  {r['heading']}")
        print(f"    {r['snippet'][:180].replace(chr(10), ' ')}...")
        print()


if __name__ == "__main__":
    main()
