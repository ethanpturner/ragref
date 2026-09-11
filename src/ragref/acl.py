"""What the source system states about each document.

The source system is a POSIX filesystem. A document's tenant is the tenant its owning group maps
to; its role is `everyone` when the file is world-readable and `member` otherwise. That is the same
reading tearline's filesystem adapter makes, on purpose: the application and the verifier must
agree on what the source says, or every disagreement between them is noise about the reading
rather than a fact about the index.

Git records neither group ownership nor the other-read bit, so the intended ACL lives in a
manifest and `apply_manifest` writes it onto the working tree before ingestion.
"""

from __future__ import annotations

import grp
import os
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

WORLD_READABLE = stat.S_IROTH


@dataclass(frozen=True)
class Entitlement:
    """Stated by the source, or unknown. There is no permissive value to fall back to."""

    state: str
    tenants: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()
    principals: tuple[str, ...] = ()

    @staticmethod
    def unknown() -> Entitlement:
        return Entitlement(state="unknown")


@dataclass(frozen=True)
class Document:
    id: str
    path: Path
    entitlement: Entitlement
    acl_modified_at: datetime


def _group_name(gid: int) -> str | None:
    try:
        return grp.getgrgid(gid).gr_name
    except KeyError:
        return None


def entitlement_for(path: Path, root: Path, group_to_tenant: dict[str, str]) -> Entitlement:
    """Read the ACL of one file. An unmapped group is `unknown`, never an empty stated grant."""
    info = path.stat()
    group = _group_name(info.st_gid)
    tenant = group_to_tenant.get(group) if group else None
    if tenant is None:
        return Entitlement.unknown()
    role = "everyone" if info.st_mode & WORLD_READABLE else "member"
    return Entitlement(state="stated", tenants=(tenant,), roles=(role,))


def documents(root: Path, group_to_tenant: dict[str, str]) -> list[Document]:
    """One document per file under the root, identified by its path relative to the root."""
    found: list[Document] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "acl.yaml":
            continue
        info = path.stat()
        found.append(
            Document(
                id=str(path.relative_to(root)),
                path=path,
                entitlement=entitlement_for(path, root, group_to_tenant),
                acl_modified_at=datetime.fromtimestamp(info.st_ctime, tz=UTC),
            )
        )
    return found


def apply_manifest(root: Path, manifest: Path) -> int:
    """Set group and mode on every file the manifest names. Returns the number touched.

    Files the manifest does not name are left alone, and a named file that is missing is an error:
    an ACL manifest that silently skips entries is one whose coverage nobody can state.
    """
    raw: dict[str, Any] = yaml.safe_load(manifest.read_text()) or {}
    entries: list[dict[str, Any]] = raw.get("files") or []
    for entry in entries:
        path = root / str(entry["path"])
        if not path.is_file():
            raise FileNotFoundError(f"manifest names {path}, which does not exist")
        gid = grp.getgrnam(str(entry["group"])).gr_gid
        os.chown(path, -1, gid)
        os.chmod(path, int(str(entry["mode"]), 8))
    return len(entries)
