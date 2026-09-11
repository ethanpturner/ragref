#!/bin/sh
# Narrow two ACLs after ingestion. No code changes; the index keeps the tags it was given.
#   acme/onboarding.md      world-readable -> members only   (role everyone -> member)
#   handover/joint-timeline.md  owned by staff -> owned by admin  (tenant acme -> globex)
set -eu
cd "$(dirname "$0")/.."
chmod o-r corpus/acme/onboarding.md
chgrp admin corpus/handover/joint-timeline.md
echo "narrowed two ACLs; the index has not been told"
