# Scan results

Output of `tearline scan` against each branch, both stores, recorded 2026-09-10 with tearline at
commit `b5eda9e`. Each branch was checked out, `ragref apply-acl` and `ragref ingest` were run,
and both targets under `tearline/` were scanned. On `f-chmod` the narrowing script ran between
ingestion and the scan. Files hold chunk identifiers only.

| Branch | pgvector (engine-enforced) | Qdrant (application-enforced) |
|---|---|---|
| `main` | clean, exit 0 | clean, exit 0 |
| `f-parent-dir` | 2 propagation faults, over-retrieval for every Acme probe, under-retrieval for Globex | same |
| `f-untagged` | 5 propagation faults, under-retrieval for both Acme principals, no leak | same |
| `f-exclusion` | 5 propagation faults, the 5 untagged chunks over-retrieved by every Globex probe | 5 propagation faults, under-retrieval only |
| `f-limit-first` | under-retrieval on 13 probe/principal pairs, no leak | clean |
| `f-chmod` | 5 chunks contradicted with cause `drift`; over-retrieval for Acme, under-retrieval for Globex | same |
| `f-superuser` | adapter refuses the connection (`BypassesRowSecurity`), exit 1, nothing verified | clean; the fault is in the PostgreSQL connection |
| `f-merge` | 2 chunks `exceeds-safe-bound`, each over-retrieved by the other tenant; `partial=True` | same |
| `f-policy-intent` | clean, exit 0 | clean, exit 0 |

Three things the runs establish about the verifier rather than the application:

- On Qdrant the differential axis uses the verifier's own filtered search, so a fault in the
  application's retrieval code (`f-exclusion`, `f-limit-first`) is invisible there. Only faults in
  the stored data reach the probes. On PostgreSQL the same fault is visible because the policy is
  the engine's and the verifier's query passes through it.
- On both stores the live retrieval path communicates the tenant and not the roles. A principal
  without `member` would register over-retrieval of member-only chunks against a correctly tagged
  index. Every probing principal in `tearline/shared/principals.yaml` holds `member` for that
  reason, and the limitation is the verifier's, not the corpus's.
- `f-merge` removes two chunk ids the probes name, and the verifier reports `partial=True` with
  the missing ids rather than treating their absence as under-retrieval.
