"""Pluggable model backends for local Part 2b (scripts/finish_drafts_local.py).
Added 2026-10-02 so a hosted model (Gemini, via Ross's student plan from
2026-10-19 or an AI Studio key) can be tested against the local Ollama models
without changing the pipeline. A model string picks the backend:

    "gemma4:26b"                 -> local Ollama (default, unchanged behaviour)
    "gemini:<model-name>"        -> Gemini API (generativelanguage.googleapis.com)

Both backends take the same arguments and return the same parsed-JSON dict, so
every grounding/verification gate in the pipeline applies identically.

Gemini specifics:
  - Key: GEMINI_API_KEY from the environment, else ~/Health/.env, else
    ~/.config/obsidian-second-brain/.env (where the vault already keeps it).
    Never logged or printed.
  - Quota safety: GEMINI_MIN_INTERVAL_S (default 4 s between calls, ~15/min)
    and GEMINI_DAILY_MAX_CALLS (default 1000); hitting the daily cap raises
    QuotaExhausted so a batch stops cleanly instead of hammering the API.
    429/5xx responses retry with backoff.
  - Usage: every call appends {time, model, prompt/output/thinking tokens} to
    Logs/gemini-usage.jsonl.
  - Privacy: callers send public transcript text only - nothing from
    Protocols/My Profile, Bloodwork/ or Daily/ goes through this module.

CLI (for setup checks):
    python scripts/llm_backends.py list-models
    python scripts/llm_backends.py ping gemini:<model-name>
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
USAGE_LOG = VAULT / "Logs" / "gemini-usage.jsonl"


class QuotaExhausted(RuntimeError):
    pass


# ---------------------------------------------------------------- config

def _env_file_value(path: Path, key: str) -> str | None:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(f"{key}=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    except OSError:
        pass
    return None


def gemini_api_key() -> str | None:
    return (os.environ.get("GEMINI_API_KEY")
            or _env_file_value(VAULT / ".env", "GEMINI_API_KEY")
            or _env_file_value(Path.home() / ".config" / "obsidian-second-brain" / ".env", "GEMINI_API_KEY"))


def is_gemini(model: str | None) -> bool:
    return bool(model) and model.startswith("gemini:")


# ---------------------------------------------------------------- ollama

def ollama_chat(model: str, prompt: str, schema: dict, *, temperature: float, num_predict: int,
                think, num_ctx: int, host: str, timeout: int = 1800) -> dict:
    body = {"model": model, "messages": [{"role": "user", "content": prompt}], "format": schema,
            "stream": False, "think": think,
            "options": {"num_ctx": num_ctx, "temperature": temperature, "num_predict": num_predict}}
    req = urllib.request.Request(host.rstrip("/") + "/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(json.loads(r.read())["message"]["content"])


# ---------------------------------------------------------------- gemini

def _to_gemini_schema(s):
    """JSON-schema subset used by the pipeline -> Gemini responseSchema
    (OpenAPI-style: upper-case types, same keys for properties/items/enum)."""
    if isinstance(s, dict):
        out = {}
        for k, v in s.items():
            if k == "type" and isinstance(v, str):
                out["type"] = v.upper()
            elif k in ("properties",):
                out[k] = {pk: _to_gemini_schema(pv) for pk, pv in v.items()}
            elif k in ("items",):
                out[k] = _to_gemini_schema(v)
            elif k in ("required", "enum", "description"):
                out[k] = v
        return out
    return s


_last_call = [0.0]


def _daily_count() -> int:
    today = date.today().isoformat()
    try:
        with USAGE_LOG.open(encoding="utf-8") as f:
            return sum(1 for line in f if f'"day": "{today}"' in line)
    except OSError:
        return 0


def gemini_chat(model: str, prompt: str, schema: dict, *, temperature: float, num_predict: int,
                think, timeout: int = 600) -> dict:
    key = gemini_api_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set (env, ~/Health/.env, or ~/.config/obsidian-second-brain/.env)")
    name = model.split(":", 1)[1]
    if _daily_count() >= int(os.environ.get("GEMINI_DAILY_MAX_CALLS", "1000")):
        raise QuotaExhausted("GEMINI_DAILY_MAX_CALLS reached for today")
    gap = float(os.environ.get("GEMINI_MIN_INTERVAL_S", "4"))
    wait = _last_call[0] + gap - time.time()
    if wait > 0:
        time.sleep(wait)

    gen = {"temperature": temperature, "maxOutputTokens": num_predict,
           "responseMimeType": "application/json", "responseSchema": _to_gemini_schema(schema)}
    if think is not None:
        # True / "low" / False -> a thinking budget; models without thinking ignore 0.
        budget = {True: int(os.environ.get("GEMINI_THINKING_BUDGET", "4096")), "low": 1024, False: 0}.get(think, 0)
        gen["thinkingConfig"] = {"thinkingBudget": budget}
        gen["maxOutputTokens"] = num_predict + budget
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": gen}
    req = urllib.request.Request(f"{GEMINI_BASE}/models/{name}:generateContent", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    for attempt in range(5):
        _last_call[0] = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                resp = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:300]
            if e.code in (429, 500, 502, 503, 504) and attempt < 4:
                time.sleep(15 * (attempt + 1))
                continue
            if e.code == 400 and "thinking" in msg.lower() and "thinkingConfig" in gen:
                gen.pop("thinkingConfig")  # model doesn't support thinking config
                req = urllib.request.Request(req.full_url, data=json.dumps(body).encode(), headers=dict(req.headers))
                continue
            raise RuntimeError(f"Gemini HTTP {e.code}: {msg}") from None
    u = resp.get("usageMetadata", {})
    USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with USAGE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"day": date.today().isoformat(), "t": time.strftime("%H:%M:%S"), "model": name,
                            "prompt": u.get("promptTokenCount"), "output": u.get("candidatesTokenCount"),
                            "thinking": u.get("thoughtsTokenCount")}) + "\n")
    parts = resp.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    return json.loads(text)


def gemini_list_models() -> list[str]:
    key = gemini_api_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")
    req = urllib.request.Request(f"{GEMINI_BASE}/models?pageSize=200", headers={"x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    return [m["name"].split("/", 1)[1] for m in data.get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])]


# ---------------------------------------------------------------- dispatch

def chat(model: str, prompt: str, schema: dict, *, temperature: float = 0.2, num_predict: int = 4096,
         think=False, num_ctx: int = 32768, host: str = "http://localhost:11434") -> dict:
    if is_gemini(model):
        return gemini_chat(model, prompt, schema, temperature=temperature, num_predict=num_predict, think=think)
    return ollama_chat(model, prompt, schema, temperature=temperature, num_predict=num_predict,
                       think=think, num_ctx=num_ctx, host=host)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "list-models":
        for m in gemini_list_models():
            print(m)
    elif cmd == "ping" and len(sys.argv) > 2:
        out = chat(sys.argv[2], "Return JSON {\"ok\": true, \"model_family\": \"<your model family>\"}.",
                   {"type": "object", "properties": {"ok": {"type": "boolean"}, "model_family": {"type": "string"}},
                    "required": ["ok"]}, num_predict=100)
        print(out)
    else:
        print(__doc__)
