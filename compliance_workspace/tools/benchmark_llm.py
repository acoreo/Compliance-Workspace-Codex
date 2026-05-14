"""
CDW LLM benchmark.

Measures cold and warm Ollama inference for candidate models using one fixed
NERC-style prompt. The output is intentionally plain Markdown so it can be
pasted directly into 05112026-discussion.md.

Usage from the Dell, with Ollama already running:

    D:\\USB-Uncensored-LLM\\Shared\\cdw\\python\\python.exe ^
        D:\\USB-Uncensored-LLM\\Shared\\cdw\\projects\\cdw\\compliance_workspace\\tools\\benchmark_llm.py ^
        --ollama-bin D:\\USB-Uncensored-LLM\\Shared\\bin\\ollama.exe ^
        nemomix-local qwen2.5:7b

Defaults to nemomix-local if no model names are provided.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_TIMEOUT_SECONDS = 900
DEFAULT_KEEP_ALIVE = "10m"

VALID_VERDICTS = {"satisfied", "partial", "gap", "not_applicable"}

SYSTEM_PROMPT = (
    "You are a NERC compliance auditor. Assess whether the provided evidence "
    "satisfies the stated requirement. Return only one JSON object. Do not add "
    "markdown fences, commentary, labels, or extra text."
)

USER_PROMPT = """\
Requirement: MOD-025-2 R1
The Generator Owner shall provide reactive capability data for each generating
unit or plant to the Transmission Planner and Planning Coordinator within 90
calendar days of a request, or by an agreed-upon date.

Evidence excerpt:
CenterPoint Energy - Acknowledgment of Receipt, dated 14 March 2022.
Confirms receipt of reactive capability data for generating units at Houston
South facility, submitted in response to Transmission Planner request dated
12 January 2022. Submission occurred on 10 March 2022 - 57 calendar days
after request. Signed: J. Francis, Compliance Officer.
Reference: MOD-025-2 R1 Q1-2022 submission cycle.

Task: Does this evidence satisfy the requirement?

Return exactly this JSON shape:
{
  "verdict": "satisfied" | "partial" | "gap" | "not_applicable",
  "confidence": 0.0,
  "rationale": "one paragraph explanation",
  "cited_text": "exact quote from evidence that supports verdict, or null",
  "gaps_identified": []
}

Use one of the four verdict strings exactly. Respond with JSON only."""


@dataclass
class BenchmarkResult:
    model: str
    call: str
    total_seconds: float
    first_token_seconds: float | None
    processor: str
    valid_json: bool
    verdict: str
    response_snippet: str
    error: str
    raw_response: str


def _get_json(url: str, timeout: int) -> Any:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post_json(url: str, payload: dict[str, Any], timeout: int) -> Any:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _chat_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _api_url(base_url: str, path: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    return f"{base}{path}"


def check_ollama(base_url: str) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(_api_url(base_url, "/"), method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200, f"HTTP {resp.status}"
    except Exception as exc:
        return False, str(exc)


def list_models(base_url: str) -> list[str]:
    try:
        data = _get_json(_api_url(base_url, "/api/tags"), timeout=5)
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    except Exception:
        return []


def unload_model(base_url: str, model: str) -> None:
    """Unload a model without generating a benchmark response."""
    payload = {"model": model, "keep_alive": 0}
    try:
        _post_json(_api_url(base_url, "/api/generate"), payload, timeout=30)
    except Exception:
        # Older Ollama builds may not support this exact unload path. The cold
        # timing is still useful if the model was not already resident.
        pass
    time.sleep(2)


def read_processor_from_cli(ollama_bin: str, model: str) -> str | None:
    """Return PROCESSOR by parsing `ollama ps` output, if available."""
    try:
        proc = subprocess.run(
            [ollama_bin, "ps"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return None

    if proc.returncode != 0 or not proc.stdout.strip():
        return None

    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    if len(lines) < 2:
        return "not_loaded"

    header = lines[0]
    header_names = ["NAME", "ID", "SIZE", "PROCESSOR", "CONTEXT", "UNTIL"]
    starts: dict[str, int] = {}
    for name in header_names:
        idx = header.find(name)
        if idx >= 0:
            starts[name] = idx
    if "NAME" not in starts or "PROCESSOR" not in starts:
        return None

    target = model.split(":")[0]
    for line in lines[1:]:
        name_end = starts.get("ID", len(line))
        name = line[starts["NAME"] : name_end].strip()
        if name == model or name.split(":")[0] == target:
            processor_start = starts["PROCESSOR"]
            processor_end = starts.get("CONTEXT", len(line))
            processor = line[processor_start:processor_end].strip()
            return processor or "loaded"
    return "not_loaded"


def read_processor(base_url: str, model: str, ollama_bin: str | None) -> str:
    """Return the PROCESSOR value from /api/ps for the given model."""
    if ollama_bin:
        cli_value = read_processor_from_cli(ollama_bin, model)
        if cli_value:
            return cli_value

    try:
        data = _get_json(_api_url(base_url, "/api/ps"), timeout=5)
    except Exception as exc:
        return f"unknown ({exc})"

    target = model.split(":")[0]
    for entry in data.get("models", []):
        name = str(entry.get("name", ""))
        if name == model or name.split(":")[0] == target:
            processor = entry.get("processor")
            if processor:
                return str(processor)
            details = entry.get("details") or {}
            if details.get("processor"):
                return str(details["processor"])
            return "loaded"
    return "not_loaded"


def extract_json(content: str) -> dict[str, Any] | None:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(text[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def validate_response(content: str) -> tuple[bool, str]:
    obj = extract_json(content)
    if obj is None:
        return False, ""
    verdict = str(obj.get("verdict", "")).lower().strip()
    required = {"verdict", "confidence", "rationale", "cited_text", "gaps_identified"}
    return verdict in VALID_VERDICTS and required.issubset(obj.keys()), verdict


def chat_completion_stream(
    base_url: str,
    model: str,
    timeout: int,
    keep_alive: str,
) -> tuple[float, float | None, str, str]:
    """Run a streaming chat completion and return timing plus content/error."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT},
        ],
        "max_tokens": 200,
        "temperature": 0.1,
        "stream": True,
        "keep_alive": keep_alive,
    }

    req = urllib.request.Request(
        _chat_url(base_url),
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    started = time.time()
    first_token: float | None = None
    parts: list[str] = []

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                if line.startswith("data:"):
                    line = line[5:].strip()
                if line == "[DONE]":
                    break
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                delta = event.get("choices", [{}])[0].get("delta", {})
                token = delta.get("content") or ""
                if token and first_token is None:
                    first_token = time.time() - started
                if token:
                    parts.append(token)
    except urllib.error.HTTPError as exc:
        snippet = ""
        try:
            snippet = exc.read(300).decode(errors="replace")
        except Exception:
            pass
        return time.time() - started, first_token, "", f"HTTP {exc.code}: {snippet}"
    except Exception as exc:
        return time.time() - started, first_token, "", str(exc)

    return time.time() - started, first_token, "".join(parts).strip(), ""


def run_call(
    base_url: str,
    model: str,
    call: str,
    timeout: int,
    keep_alive: str,
    ollama_bin: str | None,
) -> BenchmarkResult:
    total, first_token, content, error = chat_completion_stream(
        base_url=base_url,
        model=model,
        timeout=timeout,
        keep_alive=keep_alive,
    )
    processor = read_processor(base_url, model, ollama_bin)
    valid, verdict = validate_response(content)
    snippet_source = content if content else error
    snippet = " ".join(snippet_source.split())[:80]
    return BenchmarkResult(
        model=model,
        call=call,
        total_seconds=total,
        first_token_seconds=first_token,
        processor=processor,
        valid_json=valid,
        verdict=verdict,
        response_snippet=snippet,
        error=error,
        raw_response=content,
    )


def print_table(results: list[BenchmarkResult]) -> None:
    print("| model | call | first_token_s | total_s | processor | valid_json | verdict | notes |")
    print("|---|---:|---:|---:|---|---:|---|---|")
    for r in results:
        first = "" if r.first_token_seconds is None else f"{r.first_token_seconds:.1f}"
        notes = r.error or r.response_snippet
        notes = notes.replace("|", "/")
        print(
            f"| {r.model} | {r.call} | {first} | {r.total_seconds:.1f} | "
            f"{r.processor} | {str(r.valid_json)} | {r.verdict} | {notes} |"
        )


def write_raw_results(path: Path, results: list[BenchmarkResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for r in results:
            f.write(
                json.dumps(
                    {
                        "ts": dt.datetime.now(dt.UTC).isoformat(),
                        "model": r.model,
                        "call": r.call,
                        "total_seconds": r.total_seconds,
                        "first_token_seconds": r.first_token_seconds,
                        "processor": r.processor,
                        "valid_json": r.valid_json,
                        "verdict": r.verdict,
                        "error": r.error,
                        "raw_response": r.raw_response,
                    },
                    ensure_ascii=True,
                )
                + "\n"
            )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark local Ollama models for CDW.")
    parser.add_argument("models", nargs="*", default=["nemomix-local"])
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--keep-alive", default=DEFAULT_KEEP_ALIVE)
    parser.add_argument(
        "--raw-log",
        default=None,
        help="Optional JSONL path for full raw responses. Defaults to data/benchmark_raw.jsonl.",
    )
    parser.add_argument(
        "--ollama-bin",
        default=None,
        help=(
            "Optional path to ollama.exe/ollama. When set, processor is read "
            "from `ollama ps`, matching the Dell runtime check."
        ),
    )
    parser.add_argument(
        "--calls",
        choices=("both", "cold", "warm"),
        default="both",
        help="Which calls to run. Use warm to avoid long cold-load timing.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    ok, status = check_ollama(args.base_url)
    if not ok:
        print(f"ERROR: Ollama is not reachable at {args.base_url}: {status}", file=sys.stderr)
        return 2

    registered = list_models(args.base_url)
    if registered:
        print(f"Ollama models registered: {', '.join(registered)}")
    else:
        print("Ollama model list unavailable or empty.")

    ollama_bin = args.ollama_bin or shutil.which("ollama")
    if ollama_bin:
        print(f"Processor source: {ollama_bin} ps")
    else:
        print("Processor source: Ollama HTTP /api/ps")

    results: list[BenchmarkResult] = []
    for model in args.models:
        print(f"\n== {model} ==")
        if args.calls in ("both", "cold"):
            print("Unloading model before cold call...")
            unload_model(args.base_url, model)
            print("Cold call...")
            results.append(
                run_call(args.base_url, model, "cold", args.timeout, args.keep_alive, ollama_bin)
            )
        if args.calls in ("both", "warm"):
            print("Warm call...")
            results.append(
                run_call(args.base_url, model, "warm", args.timeout, args.keep_alive, ollama_bin)
            )

    print("\nPaste this table into 05112026-discussion.md:")
    print_table(results)
    raw_log = Path(args.raw_log) if args.raw_log else Path("data") / "benchmark_raw.jsonl"
    write_raw_results(raw_log, results)
    print(f"\nRaw responses written to: {raw_log}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
