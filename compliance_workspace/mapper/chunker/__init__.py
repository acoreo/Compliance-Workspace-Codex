"""NERC-aware document chunking package."""
from mapper.chunker.parser import parse_nerc_document, ParsedUnit
from mapper.chunker.chunker import build_chunks
from mapper.chunker.linker import build_relationships, write_relationships_to_db
from mapper.chunker.vsl import parse_vsl_table
from mapper.chunker.evidence import infer_evidence

__all__ = [
    "parse_nerc_document",
    "ParsedUnit",
    "build_chunks",
    "build_relationships",
    "write_relationships_to_db",
    "parse_vsl_table",
    "infer_evidence",
]
