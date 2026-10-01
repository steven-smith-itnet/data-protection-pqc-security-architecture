#!/usr/bin/env python3
"""Keyed-hash (HMAC-SHA-256) deterministic surrogates for analytics joins.

Use case: the data lake and warehouse need to join guest records across the
PMS, CRS, loyalty, and CRM feeds, but analysts do not need the raw email
address, loyalty number, or PAN. A deterministic surrogate lets the same input
produce the same value in every dataset, so joins and distinct counts work.

Why keyed (HMAC) and not a plain hash: email addresses, phone numbers, and
PANs have small or guessable input spaces. A plain SHA-256 of an email can be
reversed by hashing a list of candidate addresses. With HMAC, an attacker also
needs the key, which stays in a KMS or HSM. PCI DSS v4.0.1 requirement
3.5.1.1 requires keyed cryptographic hashes where hashes render PAN unreadable.

Purpose separation: a per-purpose key is derived with HKDF-SHA-256 from one
root key, so surrogates made for "marketing-analytics" cannot be joined to
surrogates made for "fraud-analytics" unless both are deliberately issued
from the same purpose. Rotating the root key (or a purpose) re-keys every
surrogate, which is also a way to break linkage when a purpose ends.

Trade-offs: surrogates are pseudonymous personal data under GDPR (the key
holder can re-identify by recomputing), not anonymous data. They cannot be
reversed, so where the original value is needed later, use the vault
tokenizer (vault_tokenizer.py) or envelope encryption instead.
"""
from __future__ import annotations

import hashlib
import hmac
import re

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def normalize(value: str, kind: str) -> str:
    """Normalize before hashing so trivial formatting differences still join."""
    if kind == "email":
        return value.strip().lower()
    if kind in ("pan", "phone"):
        return re.sub(r"\D", "", value)
    if kind == "loyalty":
        return value.strip().upper()
    return value.strip()


class SurrogateKeys:
    def __init__(self, root_key: bytes, key_version: str = "v1"):
        if len(root_key) < 32:
            raise ValueError("root key must be at least 256 bits")
        self._root = root_key
        self.key_version = key_version
        self._cache: dict[str, bytes] = {}

    def purpose_key(self, purpose: str) -> bytes:
        if purpose not in self._cache:
            self._cache[purpose] = HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=None,
                info=f"surrogate:{self.key_version}:{purpose}".encode(),
            ).derive(self._root)
        return self._cache[purpose]

    def surrogate(self, value: str, kind: str, purpose: str, length: int = 32) -> str:
        """Return a hex surrogate, prefixed with the key version so a rotated
        key never silently produces values that look joinable with old ones."""
        mac = hmac.new(self.purpose_key(purpose), f"{kind}:{normalize(value, kind)}".encode(), hashlib.sha256)
        return f"{self.key_version}_{mac.hexdigest()[:length]}"


if __name__ == "__main__":
    import os

    keys = SurrogateKeys(os.urandom(32))
    a = keys.surrogate("Alpha.Guest@Example.com ", "email", "marketing-analytics")
    b = keys.surrogate("alpha.guest@example.com", "email", "marketing-analytics")
    c = keys.surrogate("alpha.guest@example.com", "email", "fraud-analytics")
    print("PMS feed :", a)
    print("CRM feed :", b, "(joins:", a == b, ")")
    print("fraud    :", c, "(joins with marketing:", a == c, ")")
