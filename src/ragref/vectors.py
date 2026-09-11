"""A deterministic pseudo-embedding.

No embedding model is in the loop. The vector is a function of the text's digest, so the same
text always lands at the same point and two texts that mean the same thing land at unrelated ones.
That is useless for relevance and irrelevant for entitlement, which is the only property this
application exists to have verified.
"""

from __future__ import annotations

import hashlib

DIMENSIONS = 16


def deterministic_vector(text: str, dimensions: int = DIMENSIONS) -> list[float]:
    digest = hashlib.sha256(text.encode()).digest()
    raw = (digest * (dimensions // len(digest) + 1))[:dimensions]
    return [(byte - 127.5) / 127.5 for byte in raw]
