"""Tests for LlamaCppBackend — health checks and model validation (no live Ollama needed)."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from mapper.reasoning.llm import LlamaCppBackend


def _make_backend(model: str = "nemomix-local") -> LlamaCppBackend:
    return LlamaCppBackend(
        base_url="http://localhost:11434/v1",
        model=model,
        timeout=5,
        max_retries=1,
    )


class TestListModels(unittest.TestCase):
    def test_returns_full_model_names_and_latest_alias(self):
        """list_models preserves tags and adds a bare alias for :latest."""
        payload = json.dumps(
            {"models": [{"name": "nemomix-local:latest"}, {"name": "qwen2.5:9b"}]}
        ).encode()
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = payload

        backend = _make_backend()
        with patch("urllib.request.urlopen", return_value=mock_resp):
            names = backend.list_models()

        self.assertIn("nemomix-local:latest", names)
        self.assertIn("nemomix-local", names)
        self.assertIn("qwen2.5:9b", names)
        self.assertNotIn("qwen2.5", names)

    def test_returns_empty_list_on_connection_error(self):
        """list_models returns [] instead of raising if Ollama is down."""
        import urllib.error
        backend = _make_backend()
        with patch("urllib.request.urlopen", side_effect=OSError("refused")):
            names = backend.list_models()
        self.assertEqual(names, [])


class TestAssertHealthy(unittest.TestCase):
    def test_raises_when_ollama_unreachable(self):
        backend = _make_backend()
        with patch.object(backend, "health_check", return_value=False):
            with self.assertRaises(RuntimeError) as ctx:
                backend.assert_healthy()
        self.assertIn("not running", str(ctx.exception))

    def test_raises_when_model_not_registered(self):
        """assert_healthy raises with a clear message when the model name is wrong."""
        backend = _make_backend(model="nemomix-unleashed-12b")
        with patch.object(backend, "health_check", return_value=True):
            with patch.object(backend, "list_models", return_value=["nemomix-local", "qwen2.5:9b"]):
                with self.assertRaises(RuntimeError) as ctx:
                    backend.assert_healthy()
        msg = str(ctx.exception)
        self.assertIn("nemomix-unleashed-12b", msg)
        self.assertIn("nemomix-local", msg)
        self.assertIn("cdw_config.toml", msg)

    def test_passes_when_model_is_registered(self):
        """assert_healthy does not raise when the configured model exists."""
        backend = _make_backend(model="nemomix-local")
        with patch.object(backend, "health_check", return_value=True):
            with patch.object(backend, "list_models", return_value=["nemomix-local", "qwen2.5:9b"]):
                backend.assert_healthy()  # must not raise

    def test_skips_model_check_when_list_is_empty(self):
        """If list_models returns [] (e.g. old Ollama with no /api/tags), don't false-alarm."""
        backend = _make_backend(model="nemomix-local")
        with patch.object(backend, "health_check", return_value=True):
            with patch.object(backend, "list_models", return_value=[]):
                backend.assert_healthy()  # must not raise


if __name__ == "__main__":
    unittest.main()
