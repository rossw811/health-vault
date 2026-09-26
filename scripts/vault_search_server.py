#!/usr/bin/env python3
"""Local HTTP server wrapping vault_search.py - the shared backend for the
Obsidian plugin's search pane, info-layer sidebar, and chat layer. Stdlib-only
(no Flask/FastAPI installed in this venv, and pulling one in isn't worth it
for three simple JSON endpoints) - keeps the same "no extra infra" ethos the
RAG itself was built with.

Endpoints:
    GET  /health                          -> {"status": "ok"}
    GET  /search?q=...&k=8                -> [{"path","heading","snippet","distance"}, ...]
    POST /chat  {"query": "...", "k": 6}  -> {"answer": "...", "sources": [...]}
                                              Retrieval-then-generation via local Ollama
                                              (qwen2.5:14b, same model already used for
                                              draft generation - zero additional cost).
                                              Every answer is instructed to cite which
                                              notes it drew from - same anti-fabrication
                                              discipline as every other vault command,
                                              carried into the chat surface rather than
                                              relaxed for convenience.

CORS is wide open (Access-Control-Allow-Origin: *) since this only ever binds
to 127.0.0.1 for a single-user local Obsidian plugin - not exposed to the
network, so the usual cross-origin risk model doesn't apply here.

Run: python scripts/vault_search_server.py [--port 8765]
"""
import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vault_search  # noqa: E402 - local module, path inserted above

import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
# phi4, not qwen2.5:14b - this server runs wherever Obsidian runs (Windows), and
# qwen2.5:14b was only ever pulled on the CachyOS box for the draft-generation
# pipeline. phi4:latest is what's actually installed here.
CHAT_MODEL = "phi4:latest"

CHAT_SYSTEM_PROMPT = (
    "You are answering a question using ONLY the material provided below, pulled from the "
    "user's personal health/fitness knowledge vault. Rules, non-negotiable:\n"
    "1. Only state something if it is actually supported by the material given - never fill "
    "gaps from general knowledge or invent a claim.\n"
    "2. After every claim, cite which note it came from in the form [Source: <path>].\n"
    "3. If the material doesn't actually answer the question, say so plainly rather than "
    "guessing.\n"
    "4. Go into REAL DEPTH - use everything relevant in the material below, don't summarize "
    "down to a few sentences when the source notes have more to say. This is a knowledge-base "
    "chat where the user wants the full picture, not a headline. Include specific numbers, "
    "dosing, evidence tiers, and caveats exactly as the notes state them - don't round them "
    "away for brevity."
)

# Real finding, 2026-08-20: chat answers were coming back correct but shallow. Root cause -
# every result's context was a 500-char snippet (vault_search.py's own truncation, tuned for
# a *search results list* where you want a preview, not a *chat* where the model needs the
# actual content to reason over). Fix: read the FULL file for the top few results before
# building the prompt, snippets only for the long tail. Local generation is free, so there's
# no real cost pressure to stay artificially short here the way there is for Claude batches.
FULL_READ_TOP_N = 4
MAX_FULL_READ_CHARS = 6000  # per-file cap, so one huge note doesn't crowd out everything else


def _full_note_text(path_str: str) -> str:
    path = vault_search.VAULT_ROOT / path_str
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    return text[:MAX_FULL_READ_CHARS]


def _build_chat_prompt(query: str, results: list) -> str:
    context_blocks = []
    seen_paths = set()
    for i, r in enumerate(results):
        if i < FULL_READ_TOP_N and r["path"] not in seen_paths:
            full_text = _full_note_text(r["path"])
            seen_paths.add(r["path"])
            if full_text:
                context_blocks.append(f"--- {r['path']} (full note) ---\n{full_text}")
                continue
        context_blocks.append(f"--- {r['path']} :: {r['heading']} (excerpt) ---\n{r['snippet']}")
    context = "\n\n".join(context_blocks)
    return (
        f"{CHAT_SYSTEM_PROMPT}\n\n"
        f"MATERIAL:\n{context}\n\n"
        f"QUESTION: {query}\n\n"
        f"ANSWER (in real depth, with [Source: path] citations):"
    )


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json({"status": "ok"})
            return
        if parsed.path == "/search":
            qs = parse_qs(parsed.query)
            query = (qs.get("q") or [""])[0]
            k = int((qs.get("k") or ["8"])[0])
            if not query:
                self._send_json({"error": "missing q param"}, status=400)
                return
            try:
                results = vault_search.search(query, k)
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
                return
            self._send_json(results)
            return
        self._send_json({"error": "not found"}, status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/chat":
            self._send_json({"error": "not found"}, status=404)
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length))
        except Exception:
            self._send_json({"error": "invalid JSON body"}, status=400)
            return
        query = payload.get("query", "")
        k = int(payload.get("k", 6))
        if not query:
            self._send_json({"error": "missing query"}, status=400)
            return

        try:
            results = vault_search.search(query, k)
        except Exception as e:
            self._send_json({"error": f"search failed: {e}"}, status=500)
            return

        if not results:
            self._send_json({"answer": "No relevant notes found in the vault for this question.", "sources": []})
            return

        prompt = _build_chat_prompt(query, results)
        try:
            resp = requests.post(
                OLLAMA_URL,
                json={
                    "model": CHAT_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": 2048,  # real depth needs real room - Ollama's own
                                               # default cuts responses short well before a
                                               # genuinely thorough answer is finished
                        "num_ctx": 8192,  # phi4's real max is 16384; 8192 comfortably covers
                                           # 4 full notes (MAX_FULL_READ_CHARS=6000 each) plus
                                           # the long-tail snippets without needing the max
                    },
                },
                timeout=480,  # a real-depth answer (num_predict=2048, larger context) on a
                              # 9GB model genuinely takes longer than a short one - measured
                              # 240s as insufficient once full-note context was added
            )
            resp.raise_for_status()
            answer = resp.json().get("response", "").strip()
        except Exception as e:
            self._send_json({"error": f"chat generation failed: {e}"}, status=500)
            return

        self._send_json({
            "answer": answer,
            "sources": [{"path": r["path"], "heading": r["heading"]} for r in results],
        })

    def log_message(self, format, *args):
        pass  # keep the console quiet - this runs continuously in the background


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"vault_search_server listening on http://127.0.0.1:{args.port}")
    print("Endpoints: GET /health, GET /search?q=...&k=8, POST /chat {query,k}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
