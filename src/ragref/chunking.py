"""Splitting documents into chunks, each carrying its source's entitlement.

A chunk inherits the entitlement of the one document it came from. The chunker never merges text
across documents, because a chunk drawn from two documents has no single source entitlement, and
the source system has never had an opinion about it.
"""

from __future__ import annotations

from dataclasses import dataclass

from ragref.acl import Document, Entitlement


@dataclass(frozen=True)
class Chunk:
    id: str
    source_document_ids: tuple[str, ...]
    text: str
    entitlement: Entitlement


def _slug(document_id: str) -> str:
    return document_id.rsplit(".", 1)[0].replace("/", "-").replace("_", "-").lower()


def chunk_document(document: Document, size: int) -> list[Chunk]:
    """Fixed-width chunks on paragraph boundaries where possible."""
    text = document.path.read_text(encoding="utf-8")
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    pieces: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) > size and current:
            pieces.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        pieces.append(current)
    slug = _slug(document.id)
    return [
        Chunk(
            id=f"c-{slug}-{index:02d}",
            source_document_ids=(document.id,),
            text=piece,
            entitlement=document.entitlement,
        )
        for index, piece in enumerate(pieces, start=1)
    ]


def chunk_documents(documents: list[Document], size: int) -> list[Chunk]:
    out: list[Chunk] = []
    for document in documents:
        out.extend(chunk_document(document, size))
    return out
