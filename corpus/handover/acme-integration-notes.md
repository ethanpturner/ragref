# Acme notes for the joint integration

Acme's side of the integration exposes the partner API read endpoints. Authentication is by
signed token issued by the Acme gateway, valid for one hour.

Rate limits are per tenant and are shared across all of a tenant's tokens. The limit is
returned in a response header so that the caller can back off before being throttled.

Acme's test environment refreshes weekly from a masked copy of production. Data written to it
during the week is lost at the refresh.
