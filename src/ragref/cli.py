"""The command surface: apply the ACL, ingest, retrieve."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from ragref.acl import apply_manifest, documents
from ragref.chunking import chunk_documents
from ragref.stores import PgStore, Principal, QdrantStore


def _config(path: Path) -> dict[str, Any]:
    raw: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
    raw["_root"] = path.resolve().parent
    return raw


def _stores(config: dict[str, Any], which: str) -> list[PgStore | QdrantStore]:
    out: list[PgStore | QdrantStore] = []
    if which in ("pgvector", "both"):
        pg = config["pgvector"]
        out.append(PgStore(str(pg["dsn"]), reader_role=pg.get("reader_role")))
    if which in ("qdrant", "both"):
        qd = config["qdrant"]
        out.append(QdrantStore(str(qd["base_url"]), str(qd["collection"])))
    return out


def _principal(config: dict[str, Any], principal_id: str) -> Principal:
    raw = yaml.safe_load((config["_root"] / str(config["principals"])).read_text())
    for entry in raw["principals"]:
        if str(entry["id"]) == principal_id:
            return Principal(
                id=principal_id,
                tenant=entry.get("tenant"),
                roles=tuple(str(r) for r in entry.get("roles") or ()),
            )
    raise SystemExit(f"no principal {principal_id!r} in {config['principals']}")


def _corpus(config: dict[str, Any]) -> tuple[Path, dict[str, str]]:
    corpus = config["corpus"]
    root = (config["_root"] / str(corpus["root"])).resolve()
    return root, {str(k): str(v) for k, v in corpus["group_to_tenant"].items()}


def cmd_apply_acl(config: dict[str, Any], _: argparse.Namespace) -> int:
    root, _mapping = _corpus(config)
    count = apply_manifest(root, config["_root"] / str(config["corpus"]["acl_manifest"]))
    print(f"applied {count} ACL entries under {root}")
    return 0


def cmd_ingest(config: dict[str, Any], args: argparse.Namespace) -> int:
    root, mapping = _corpus(config)
    chunks = chunk_documents(documents(root, mapping), int(config["chunking"]["size"]))
    for store in _stores(config, args.store):
        store.create_schema()
        store.replace(chunks)
        print(f"{type(store).__name__}: {len(chunks)} chunks written")
    return 0


def cmd_inventory(config: dict[str, Any], _: argparse.Namespace) -> int:
    """What the application would write, before writing it. Identifiers and tags only."""
    root, mapping = _corpus(config)
    for chunk in chunk_documents(documents(root, mapping), int(config["chunking"]["size"])):
        ent = chunk.entitlement
        print(
            json.dumps(
                {
                    "id": chunk.id,
                    "sources": list(chunk.source_document_ids),
                    "state": ent.state,
                    "tenants": list(ent.tenants),
                    "roles": list(ent.roles),
                }
            )
        )
    return 0


def cmd_retrieve(config: dict[str, Any], args: argparse.Namespace) -> int:
    principal = _principal(config, args.principal)
    for store in _stores(config, args.store):
        ids = store.retrieve(principal, args.query, args.k)
        print(f"{type(store).__name__}: {' '.join(ids) if ids else '(nothing)'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ragref", description=__doc__)
    parser.add_argument("--config", default="ragref.yaml", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("apply-acl", help="write the manifest's groups and modes onto the corpus")
    ingest = sub.add_parser("ingest", help="chunk the corpus and replace both indexes")
    ingest.add_argument("--store", choices=["pgvector", "qdrant", "both"], default="both")
    sub.add_parser("inventory", help="print what ingestion would write, ids and tags only")
    retrieve = sub.add_parser("retrieve", help="query as a principal")
    retrieve.add_argument("--principal", required=True)
    retrieve.add_argument("--query", required=True)
    retrieve.add_argument("--store", choices=["pgvector", "qdrant", "both"], default="both")
    retrieve.add_argument("-k", type=int, default=10)
    args = parser.parse_args(argv)
    config = _config(args.config)
    handler = {
        "apply-acl": cmd_apply_acl,
        "ingest": cmd_ingest,
        "inventory": cmd_inventory,
        "retrieve": cmd_retrieve,
    }[args.command]
    return handler(config, args)


if __name__ == "__main__":
    sys.exit(main())
