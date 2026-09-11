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


#: A trailing chunk shorter than this is folded into the next document's first chunk when both
#: sit in the same directory, so that no retrieval unit is too short to be useful.
MIN_TAIL = 140


def chunk_documents(documents: list[Document], size: int) -> list[Chunk]:
    out: list[Chunk] = []
    for document in documents:
        chunks = chunk_document(document, size)
        if (
            out
            and chunks
            and len(out[-1].text) < MIN_TAIL
            and out[-1].source_document_ids[-1].rsplit("/", 1)[0] == document.id.rsplit("/", 1)[0]
        ):
            tail = out.pop()
            head = chunks.pop(0)
            chunks.insert(
                0,
                Chunk(
                    id=tail.id,
                    source_document_ids=tail.source_document_ids + head.source_document_ids,
                    text=f"{tail.text}\n\n{head.text}",
                    entitlement=tail.entitlement,
                ),
            )
        out.extend(chunks)
    return out
