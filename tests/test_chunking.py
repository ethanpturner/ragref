from datetime import UTC, datetime
from pathlib import Path

from ragref.acl import Document, Entitlement
from ragref.chunking import chunk_document


def test_a_chunk_inherits_exactly_one_source_and_its_entitlement(tmp_path: Path) -> None:
    file = tmp_path / "acme" / "note.md"
    file.parent.mkdir()
    file.write_text("para one\n\npara two\n\npara three")
    document = Document(
        id="acme/note.md",
        path=file,
        entitlement=Entitlement(state="stated", tenants=("acme",), roles=("member",)),
        acl_modified_at=datetime.now(tz=UTC),
    )
    chunks = chunk_document(document, size=12)
    assert [c.id for c in chunks] == ["c-acme-note-01", "c-acme-note-02", "c-acme-note-03"]
    assert all(c.source_document_ids == ("acme/note.md",) for c in chunks)
    assert all(c.entitlement == document.entitlement for c in chunks)
