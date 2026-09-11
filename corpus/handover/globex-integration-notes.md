# Globex notes for the joint integration

Globex consumes the Acme read endpoints from a scheduled job that runs hourly and writes into the
Globex warehouse. The job is idempotent and retries with exponential backoff.

Globex's connector holds one token per Acme tenant and refreshes it ten minutes before expiry.
Token material is held in the secrets service and is never logged.

Reconciliation runs nightly and reports any record present on one side and absent on the other.
The report goes to both integration leads.
