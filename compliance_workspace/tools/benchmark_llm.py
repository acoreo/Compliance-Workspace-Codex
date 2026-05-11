"""
CDW LLM Benchmark — measures cold and warm inference latency for candidate models.

Usage (from the Dell, with Ollama already running):
    D:\USB-Uncensored-LLM\Shared\cdw\python\python.exe ^
        D:\USB-Uncensored-LLM\Shared\cdw\projects\cdw\compliance_workspace\tools\benchmark_llm.py ^
        nemomix-local qwen2.5:7b

Pass model names as arguments. Defaults to nemomix-local if none given.

Each model gets two calls against a fixed MOD-025-2 prompt:
  cold — model unloaded from RAM first (simulates first call of the day)
  warm — model already in RAM (simulates subsequent calls in a run)

Output: one row per call, pipe-delimited for easy pasting into the discussion log.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# Fixed benchmark prompt — short MOD-025-2 requirement + realistic evidence
# excerpt. Identical across all model runs so results are comparable.
# ---------------------------------------------------------------------------
_SYSTEM = (
    "You are a NERC CIP compliance auditor. "
    "Assess whether the provided evidence satisfies the stated requirement. "
    "Respond ONLY with valid JSON: "
    '{"verdict": "<Met|Partial|Gap|Not_Applicable>", '
    '"rationale": "<one sentence>", '
    '"confidence": <0.0-1.0>}'
)

_USER = """\
Requirement: MOD-025-2 R1
The Generator Owner shall provide reactive capability data for each generating
unit or plant to the Transmission Planner and Planning Coordinator within 90
calendar days of a request, or by an agreed-upon date.

Evidence (500 chars):
CenterPoint Energy — Acknowledgment of Receipt, dated 14 March 2022.
Confirms receipt of reactive capability data for generating units at Houston
South facility, submitted in response to Transmission Planner request dated
12 January 2022. Submission occurred on 10 March 2022 — 57 calendar days
after request. Signed: J. Francis, Compliance Officer.
Reference: MOD-025-2 R1 Q1-2022 submission cycle.

Respond with JSON only."""

OLLAMA_BASE = "http://127.0.0.1:11434"
CHAT_URL    = f"{OLLAMA_BASE}/v1/chat/completions"
TIMEOUT     = 600   # seconds — long enough for a cold 12B load on CPU


def _post(model: str, keep_alive: str = "5m") -> tuple[float, str]:
    """POST a chat completion request. Returns (elapsed_seconds, raw_content)."""
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user",   "content": _USER},
        ],
        "max_tokens":  200,
        "temperature": 0.1,
        "stream":      False,
        "keep_alive":  keep_alive,
    }).encode()

    req = urllib.request.Request(
        CHAT_URL,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = json.loads(resp.read().decode())
            content = body["choices"][0]["message"]["content"].strip()
            return time.time() - start, content
    except urllib.error.HTTPError as exc:
        snippet = ""
        try:
            snippet = exc.read(200).decode(errors="replace")
        except Exception:
            pass
        return time.time() - start, f"HTTP {exc.code}: {snippet}"
    except Exception as exc:
        return time.time() - start, f"ERROR: {exc}"


def _unload(model: str) -> None:
    """Ask Ollama to evict the model from RAM (keep_alive=0s)."""
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "x"}],
        "max_tokens": 1,
        "keep_alive": "0s",
    }).encode()
    req = urllib.request.Request(
        CHAT_URL, data=payload, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30):
            pass
    except Exception:
        pass
    time.sleep(3)


def _verdict_valid(content: str) -> bool:
    """Return True if the response is parseable JSON with a valid verdict."""
    try:
        obj = json.loads(content)
        return obj.get("verdict") in {"Met", "Partial", "Gap", "Not_Applicable"}
    except Exception:
        # Try stripping markdown fences
        stripped = content.strip().strip("`").strip()
        if stripped.startswith("{"):
            try:
                obj = json.loads(stripped)
                return obj.get("verdict") in {"Met", "Partial", "Gap", "Not_Applicable"}
            except Exception:
                pass
    return False


def benchmark(models: list[str]) -> None:
    header = f"{'model':<28} | {'call':<5} | {'seconds':>8} | {'valid_json':>10} | response_snippet"
    sep    = "-" * len(header)
    print(header)
    print(sep)

    for model in models:
        # --- Cold call ---
        print(f"  Unloading {model} from RAM...", flush=True)
        _unload(model)

        print(f"  Cold call → {model}...", flush=True)
        cold_secs, cold_content = _post(model, keep_alive="5m")
        cold_valid   = _verdict_valid(cold_content)
        cold_snippet = cold_content.replace("\n", " ")[:55]
        print(f"{model:<28} | {'cold':<5} | {cold_secs:>8.1f} | {str(cold_valid):>10} | {cold_snippet}")

        # --- Warm call (model still in RAM) ---
        time.sleep(2)
        print(f"  Warm call → {model}...", flush=True)
        warm_secs, warm_content = _post(model, keep_alive="5m")
        warm_valid   = _verdict_valid(warm_content)
        warm_snippet = warm_content.replace("\n", " ")[:55]
        print(f"{model:<28} | {'warm':<5} | {warm_secs:>8.1f} | {str(warm_valid):>10} | {warm_snippet}")
        print()

    print(sep)
    print("Paste this table into 05112026-discussion.md")


if __name__ == "__main__":
    targets = sys.argv[1:] if len(sys.argv) > 1 else ["nemomix-local"]
    print(f"\nCDW LLM Benchmark  |  Ollama: {OLLAMA_BASE}")
    print(f"Models: {', '.join(targets)}\n")
    benchmark(targets)
