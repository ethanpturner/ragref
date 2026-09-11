# ragref

A reference retrieval-augmented generation application with entitlement filtering, built to be
verified rather than deployed. It exists as a target for
[tearline](https://github.com/ethanpturner/tearline), which checks that a retrieval index's
entitlement tags match the source system's ACLs and that retrieval respects them.

**This application is not for production.** Eight branches each carry one deliberately injected
fault. The `main` branch is the clean reference. Nothing here is hardened, and the credentials in
`ragref.yaml` are local development defaults.

## What it does

- Reads a corpus of Markdown documents from a POSIX filesystem. A document's tenant is the tenant
  its owning group maps to (`ragref.yaml`, `group_to_tenant`); its role is `everyone` when the file
  is world-readable and `member` otherwise. This is the reading tearline's filesystem adapter makes,
  so the application and the verifier agree on what the source states.
- Chunks each document on paragraph boundaries. A chunk inherits the entitlement of the one
  document it came from, and the chunker never merges text across documents.
- Writes the chunks to two indexes: PostgreSQL with `pgvector` under a row-level security policy
  that the engine evaluates, and Qdrant, where the tenant filter is supplied by the application on
  every search.
- Retrieves as a principal. Tenancy is enforced by the policy on PostgreSQL and by the filter on
  Qdrant; roles are checked by the application on both.

Vectors are a deterministic function of the text's digest. No embedding model is in the loop,
because relevance is not the property under verification.

## Intent

Every member of a tenant may read every document of that tenant, with one exception: documents
under `acme/audit/` are readable only by principals holding the `audit` role, because they name
control owners and open findings. World-readable documents are
readable by every member of the owning tenant and by no one outside it: the read bit for "other"
is a statement about the group's members, not about other tenants. Documents under `handover/`
belong to whichever tenant's group owns the file, one side or the other, never both.

## Running it

Requires PostgreSQL 17 with `pgvector`, and Qdrant on `localhost:6333`. Create the database and
roles once, as a superuser:

```sql
CREATE ROLE ragref_app LOGIN PASSWORD 'ragref_app';
CREATE ROLE ragref_reader LOGIN PASSWORD 'ragref_reader';
CREATE DATABASE ragref_pg OWNER ragref_app;
\c ragref_pg
CREATE EXTENSION vector;
```

Then:

```bash
uv sync
uv run ragref apply-acl          # write corpus/acl.yaml's groups and modes onto the working tree
uv run ragref ingest             # chunk the corpus and replace both indexes
uv run ragref inventory          # what ingestion writes: ids and tags, never text
uv run ragref retrieve --principal p-acme-member --query "expense receipts"
```

`apply-acl` is needed because git records neither group ownership nor the other-read bit. The
manifest is the intended ACL; the working tree carries it only after the command runs.

## Verifying it with tearline

`tearline/pgvector/` and `tearline/qdrant/` are scan targets. From a tearline checkout:

```bash
uv run tearline scan /path/to/ragref/tearline/pgvector
uv run tearline scan /path/to/ragref/tearline/qdrant
```

The shared rule, principals, and probes are in `tearline/shared/`. Probes name chunk ids, so they
are re-authored if the corpus or the chunk size changes.

## The fault branches

| Branch | Fault | tearline scenario |
|---|---|---|
| `f-parent-dir` | tenant derived from the top-level directory instead of the owning group | wrong-tenant-tag |
| `f-exclusion` | policy admits any chunk whose stated tenants do not exclude the caller, so an untagged chunk is admitted to everyone | untagged-chunk / faulted-naive |
| `f-untagged` | documents two directories deep are written with no entitlement; policy correct | untagged-chunk / faulted |
| `f-limit-first` | approximate index with a small candidate bound, filtered after the scan | post-filter-truncation |
| `f-chmod` | no code change; a script narrows two ACLs after ingestion | narrowed-after-ingest |
| `f-superuser` | the application connects as a superuser, so the policy is never applied to it | none; the verifier refuses the connection |
| `f-merge` | the chunker joins a short tail onto the next document's head, across a tenant boundary | boundary-crossing-chunk |
| `f-policy-intent` | the documented intent requires the `audit` role for `acme/audit/`; neither the source ACL nor the policy expresses it | none by decision; tearline evaluation plan section 7 |

Each branch is one commit off `main`. `truth/matrix.yaml` records, before any tool runs, which
of a code reviewer and tearline is expected to catch each fault, and why.

## Licence

MIT.
