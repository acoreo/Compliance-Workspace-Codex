"""Semantic retrieval using embedding-based cosine search.

Supports three pluggable backends:
- sentence_transformers  (preferred for air-gap; requires sentence-transformers)
- openai_compatible      (any OpenAI-compatible embeddings endpoint)
- stub                   (deterministic hash-based vectors; no model required)
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional, Tuple

import numpy as np

from mapper.index.store import update_embedding

# Backend name constants
BACKEND_SENTENCE_TRANSFORMERS = "sentence_transformers"
BACKEND_OPENAI_COMPATIBLE = "openai_compatible"
BACKEND_STUB = "stub"


# ---------------------------------------------------------------------------
# Embedder implementations
# ---------------------------------------------------------------------------

class _StubEmbedder:
    """Deterministic unit-norm random vector. No external dependencies."""

    DIM = 384

    def embed(self, text: str) -> np.ndarray:
        seed = abs(hash(text)) % (2 ** 32)
        rng = np.random.default_rng(seed)
        vec = rng.standard_normal(self.DIM).astype(np.float32)
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec


class _SentenceTransformerEmbedder:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        from sentence_transformers import SentenceTransformer  # type: ignore
        self._model = SentenceTransformer(model_name)

    def embed(self, text: str) -> np.ndarray:
        vec = self._model.encode(text, convert_to_numpy=True).astype(np.float32)
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec


class _OpenAICompatibleEmbedder:
    def __init__(
        self,
        api_url: str,
        api_key: str = "",
        model: str = "text-embedding-ada-002",
    ) -> None:
        self._url = api_url
        self._key = api_key
        self._model = model

    def embed(self, text: str) -> np.ndarray:
        import json
        import urllib.request

        payload = json.dumps({"input": text, "model": self._model}).encode()
        headers = {"Content-Type": "application/json"}
        if self._key:
            headers["Authorization"] = f"Bearer {self._key}"

        req = urllib.request.Request(self._url, data=payload, headers=headers)
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())

        vec = np.array(data["data"][0]["embedding"], dtype=np.float32)
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec


def _build_embedder(backend: str, **kwargs):
    if backend == BACKEND_SENTENCE_TRANSFORMERS:
        return _SentenceTransformerEmbedder(
            model_name=kwargs.get("model_name", "all-MiniLM-L6-v2")
        )
    if backend == BACKEND_OPENAI_COMPATIBLE:
        return _OpenAICompatibleEmbedder(
            api_url=kwargs["api_url"],
            api_key=kwargs.get("api_key", ""),
            model=kwargs.get("model", "text-embedding-ada-002"),
        )
    return _StubEmbedder()


# ---------------------------------------------------------------------------
# Retriever
# ---------------------------------------------------------------------------

class SemanticRetriever:
    """Embed-and-cosine-search against stored chunk embeddings.

    Example::

        retriever = SemanticRetriever(conn, backend="stub")
        results = retriever.search("patch management procedure", top_k=5)
        # [(chunk_id, score, chunk_type, citation_path), ...]

    To use sentence-transformers::

        retriever = SemanticRetriever(
            conn,
            backend="sentence_transformers",
            model_name="all-MiniLM-L6-v2",
        )
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        backend: str = BACKEND_STUB,
        **backend_kwargs,
    ) -> None:
        self._conn = conn
        self._embedder = _build_embedder(backend, **backend_kwargs)

    def embed_chunks(self, chunk_ids: Optional[List[str]] = None) -> int:
        """Compute and persist embeddings for chunks missing one.

        If *chunk_ids* is given, only those chunks are processed.
        Returns the number of chunks embedded.
        """
        if chunk_ids:
            placeholders = ",".join("?" * len(chunk_ids))
            rows = self._conn.execute(
                f"SELECT chunk_id, text FROM chunks "
                f"WHERE chunk_id IN ({placeholders}) AND embedding IS NULL",
                chunk_ids,
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT chunk_id, text FROM chunks WHERE embedding IS NULL"
            ).fetchall()

        for chunk_id, text in rows:
            vec = self._embedder.embed(text or "")
            update_embedding(self._conn, chunk_id, vec)

        return len(rows)

    def search(
        self,
        query: str,
        top_k: int = 10,
        chunk_type_filter: Optional[str] = None,
    ) -> List[Tuple[str, float, str, str]]:
        """Cosine-search the query against all stored embeddings.

        Args:
            query: Natural-language query string.
            top_k: Maximum number of results to return.
            chunk_type_filter: If set, restrict search to chunks of this type.

        Returns:
            List of ``(chunk_id, score, chunk_type, citation_path)`` tuples
            sorted descending by cosine similarity.
        """
        query_vec = self._embedder.embed(query)

        if chunk_type_filter:
            rows = self._conn.execute(
                "SELECT chunk_id, embedding, chunk_type, official_citation_path "
                "FROM chunks WHERE embedding IS NOT NULL AND chunk_type = ?",
                (chunk_type_filter,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT chunk_id, embedding, chunk_type, official_citation_path "
                "FROM chunks WHERE embedding IS NOT NULL"
            ).fetchall()

        scored: List[Tuple[str, float, str, str]] = []
        for chunk_id, blob, ctype, citation in rows:
            vec = np.frombuffer(blob, dtype=np.float32)
            score = float(np.dot(query_vec, vec))  # both are unit-norm
            scored.append((chunk_id, score, ctype, citation))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]
