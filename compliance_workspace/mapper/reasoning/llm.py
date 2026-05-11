"""llama.cpp local backend via OpenAI-compatible REST API (P3-T03).

Uses only urllib.request for HTTP — no requests/httpx dependency.
Retries up to max_retries times with exponential backoff on connection errors.
Configuration is loaded from config/cdw_config.toml via stdlib tomllib (≥3.11).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

_DEFAULTS: dict[str, Any] = {
    "base_url": "http://localhost:8080",
    "model": "qwen2.5-14b",
    "timeout_seconds": 120,
    "max_retries": 3,
    "max_tokens": 1024,
    "temperature": 0.1,
}


def _load_toml_section(config_path: Path, section: str) -> dict[str, Any]:
    """Return a TOML section dict; empty dict on any failure."""
    try:
        try:
            import tomllib  # Python 3.11+
        except ImportError:
            try:
                import tomli as tomllib  # type: ignore
            except ImportError:
                return {}
        with config_path.open("rb") as f:
            data = tomllib.load(f)
        return data.get(section, {})
    except Exception:
        return {}


class LlamaCppBackend:
    """Thin wrapper around the llama.cpp OpenAI-compatible HTTP API."""

    PROMPT_VERSION = "v1"

    def __init__(
        self,
        base_url: str = _DEFAULTS["base_url"],
        model: str = _DEFAULTS["model"],
        timeout: int = _DEFAULTS["timeout_seconds"],
        max_retries: int = _DEFAULTS["max_retries"],
        max_tokens: int = _DEFAULTS["max_tokens"],
        temperature: float = _DEFAULTS["temperature"],
        inter_call_delay: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = int(timeout)
        self.max_retries = int(max_retries)
        self.max_tokens = int(max_tokens)
        self.temperature = float(temperature)
        self.inter_call_delay = int(inter_call_delay)

    @classmethod
    def from_config(cls, config_path: Path) -> "LlamaCppBackend":
        """Construct from the [llm] section of cdw_config.toml."""
        cfg = _load_toml_section(config_path, "llm")
        return cls(
            base_url=cfg.get("base_url", _DEFAULTS["base_url"]),
            model=cfg.get("model", _DEFAULTS["model"]),
            timeout=cfg.get("timeout_seconds", _DEFAULTS["timeout_seconds"]),
            max_retries=cfg.get("max_retries", _DEFAULTS["max_retries"]),
            max_tokens=cfg.get("max_tokens", _DEFAULTS["max_tokens"]),
            temperature=cfg.get("temperature", _DEFAULTS["temperature"]),
            inter_call_delay=cfg.get("inter_call_delay_seconds", 3),
        )

    def _ollama_root(self) -> str:
        """Return the bare Ollama root URL (no /v1 suffix)."""
        base = self.base_url.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        return base

    def health_check(self) -> bool:
        """Return True if Ollama is reachable, False otherwise."""
        try:
            req = urllib.request.Request(self._ollama_root(), method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """Return the list of model names registered in Ollama.

        Returns an empty list if Ollama is unreachable or the response is malformed.
        """
        try:
            url = f"{self._ollama_root()}/api/tags"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
            # Each entry has a "name" field like "nemomix-local:latest"
            return [m["name"].split(":")[0] for m in data.get("models", [])]
        except Exception:
            return []

    def assert_healthy(self) -> None:
        """Raise a clear RuntimeError if Ollama is unreachable or the configured model is missing."""
        if not self.health_check():
            raise RuntimeError(
                f"Ollama is not running at {self._ollama_root()}.\n"
                "  Start it first with: start_cdw.bat  (Windows)\n"
                "  or:  ollama serve  (Mac/Linux)"
            )
        # Verify the configured model name is actually registered.
        available = self.list_models()
        if available and self.model not in available:
            raise RuntimeError(
                f"Model '{self.model}' is not registered in Ollama.\n"
                f"  Registered models: {', '.join(available)}\n"
                f"  Check the [llm] model = ... value in cdw_config.toml."
            )

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int | None = None,
    ) -> str:
        """Send a chat-completion request and return the assistant content string.

        Retries up to *max_retries* times with exponential backoff (1 s, 2 s, …)
        on connection / OS errors.  Raises RuntimeError if all attempts fail.
        """
        payload = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
                "temperature": self.temperature,
            }
        ).encode()

        # Normalize URL — config may already include /v1, avoid /v1/v1/chat/completions
        base = self.base_url.rstrip("/")
        if base.endswith("/v1"):
            url = f"{base}/chat/completions"
        else:
            url = f"{base}/v1/chat/completions"

        req = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = json.loads(resp.read().decode())
                    return body["choices"][0]["message"]["content"]
            except urllib.error.HTTPError as exc:
                body_snippet = ""
                try:
                    body_snippet = exc.read(200).decode(errors="replace")
                except Exception:
                    pass
                last_exc = RuntimeError(
                    f"HTTP {exc.code} from {url}: {body_snippet}"
                )
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                last_exc = exc
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
            except (KeyError, json.JSONDecodeError) as exc:
                raise RuntimeError(
                    f"Unexpected response format from Ollama: {exc}"
                ) from exc

        raise RuntimeError(
            f"Ollama unreachable after {self.max_retries} attempt(s) [{url}]: {last_exc}"
        )
