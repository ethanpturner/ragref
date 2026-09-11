# Acme product roadmap, second half

The second half concentrates on three themes: reliability of the ingestion pipeline, the partner
API, and the reporting surface.

Reliability work replaces the scheduler and introduces per-tenant rate limits. The scheduler
replacement is the largest item and has a hard dependency on the storage migration completing in
the first quarter of the half.

The partner API ships in two phases. Phase one exposes read endpoints behind the existing gateway.
Phase two adds write endpoints and the webhook subscription model, and is gated on the signing
work that security has open.

Reporting moves to the new warehouse. Existing dashboards are ported first; new ones wait until
the port is complete so that nobody is maintaining two copies.
