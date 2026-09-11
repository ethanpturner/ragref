# Globex security policy summary

Production access requires hardware-backed second factors and is granted per system and per role.
Standing administrative access is not granted; elevated access is requested for a window and
expires automatically.

Secrets are stored in the secrets service and never in source control or configuration files. A
secret found in source control is rotated the same day whether or not it was live.

Third-party code is pinned by digest and reviewed before an upgrade. Dependency upgrades that
change a security-relevant component require a second reviewer.

Security incidents follow the on-call procedure with the security lead added to the bridge.
