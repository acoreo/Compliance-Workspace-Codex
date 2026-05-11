"""Phase 2 indexing package: schema, store, semantic, and structural retrieval."""
from mapper.index.schema import create_chunk_tables
from mapper.index.store import (
    write_chunks,
    write_vsl_artifacts,
    write_relationships,
    get_chunk,
    update_embedding,
)
from mapper.index.semantic import SemanticRetriever
from mapper.index import structural

__all__ = [
    "create_chunk_tables",
    "write_chunks",
    "write_vsl_artifacts",
    "write_relationships",
    "get_chunk",
    "update_embedding",
    "SemanticRetriever",
    "structural",
]
