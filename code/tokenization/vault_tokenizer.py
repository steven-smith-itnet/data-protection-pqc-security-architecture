#!/usr/bin/env python3
"""Vault tokenization for payment card numbers (Phase 3: Structured data).

A token vault replaces a PAN with a random token and keeps the PAN, encrypted,
in one tightly controlled store. Systems that hold only tokens can drop out of
PCI DSS scope for stored cardholder data (subject to QSA agreement), because
a random token has no mathematical relationship to the PAN.

Properties of the tokens produced here:

* Random: every digit except the last four comes from a CSPRNG. Nothing is
  derived from the PAN, so there is no key to steal that reverses a token.
* Format-preserving in appearance: same length as the PAN and the same last
  four digits, so receipts, call-center screens, and matching logic that use
  "card ending 1111" keep working.
* Never Luhn-valid: each token is forced to fail the Luhn check, so a token
  can never be mistaken for a real PAN by a person, a DLP rule, or the
  discovery scanner in code/discovery/. Changing any single digit always
  changes the Luhn sum modulo 10, so one adjusted digit is enough.
* Consistent: the same PAN returns the same token (lookup by keyed hash,
  HMAC-SHA-256, per PCI DSS 3.5.1.1), which keeps joins and duplicate checks
  working without storing a plain hash.

Detokenization requires a caller role in the allow list and every attempt,
allowed or denied, is written to an audit table.

Demo only: the vault key and the HMAC key are passed in as bytes. In
production they come from a KMS or HSM (see code/envelope/), the vault runs
as an isolated service, and the role check is an IAM decision, not a string.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import datetime, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

DEFAULT_DETOKENIZE_ROLES = frozenset({"payment-settlement", "chargeback-analyst"})


def luhn_valid(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def normalize_pan(pan: str) -> str:
    digits = "".join(ch for ch in pan if ch.isdigit())
    if len(digits) != len(pan.replace(" ", "").replace("-", "")):
        raise ValueError("PAN may contain only digits, spaces, and dashes")
    if not 13 <= len(digits) <= 19:
        raise ValueError("PAN must be 13 to 19 digits")
    if not luhn_valid(digits):
        raise ValueError("PAN fails the Luhn check")
    return digits


def make_token(pan: str) -> str:
    """Random token: same length, same last four, guaranteed not Luhn-valid."""
    n = len(pan)
    body = [secrets.choice("0123456789") for _ in range(n - 4)]
    # Avoid a leading zero so the token survives numeric column types.
    if body[0] == "0":
        body[0] = secrets.choice("123456789")
    token = "".join(body) + pan[-4:]
    if luhn_valid(token):
        # Change one non-last-four digit (not the first, to keep it non-zero).
        pos = secrets.randbelow(n - 5) + 1  # index 1 .. n-5; n >= 13
        old = token[pos]
        new = secrets.choice([d for d in "0123456789" if d != old and not (pos == 0 and d == "0")])
        token = token[:pos] + new + token[pos + 1 :]
    assert not luhn_valid(token)
    return token


class TokenVault:
    def __init__(
        self,
        vault_key: bytes,
        index_key: bytes,
        db_path: str = ":memory:",
        detokenize_roles: frozenset[str] = DEFAULT_DETOKENIZE_ROLES,
    ):
        if len(vault_key) != 32 or len(index_key) < 32:
            raise ValueError("vault_key must be 32 bytes and index_key at least 32 bytes")
        self._aead = AESGCM(vault_key)
        self._index_key = index_key
        self.detokenize_roles = detokenize_roles
        self.db = sqlite3.connect(db_path)
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS vault (
                token       TEXT PRIMARY KEY,
                pan_index   TEXT NOT NULL UNIQUE,  -- HMAC-SHA-256 of PAN (keyed, PCI 3.5.1.1)
                pan_ct      BLOB NOT NULL,         -- nonce || AES-256-GCM(PAN), AAD = token
                last4       TEXT NOT NULL,
                created_at  TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                at        TEXT NOT NULL,
                action    TEXT NOT NULL,
                role      TEXT,
                token     TEXT,
                allowed   INTEGER NOT NULL,
                reason    TEXT
            );
            """
        )

    def _index(self, pan: str) -> str:
        return hmac.new(self._index_key, pan.encode(), hashlib.sha256).hexdigest()

    def _audit(self, action: str, role: str | None, token: str | None, allowed: bool, reason: str = "") -> None:
        self.db.execute(
            "INSERT INTO audit (at, action, role, token, allowed, reason) VALUES (?,?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(), action, role, token, int(allowed), reason),
        )
        self.db.commit()

    def tokenize(self, pan: str) -> str:
        digits = normalize_pan(pan)
        idx = self._index(digits)
        row = self.db.execute("SELECT token FROM vault WHERE pan_index = ?", (idx,)).fetchone()
        if row:
            return row[0]
        for _ in range(20):
            token = make_token(digits)
            if token == digits:
                continue
            nonce = os.urandom(12)
            ct = nonce + self._aead.encrypt(nonce, digits.encode(), token.encode())
            try:
                self.db.execute(
                    "INSERT INTO vault (token, pan_index, pan_ct, last4, created_at) VALUES (?,?,?,?,?)",
                    (token, idx, ct, digits[-4:], datetime.now(timezone.utc).isoformat()),
                )
                self.db.commit()
                self._audit("tokenize", None, token, True)
                return token
            except sqlite3.IntegrityError:
                continue  # token collision; try again
        raise RuntimeError("could not generate a unique token")

    def detokenize(self, token: str, role: str) -> str:
        if role not in self.detokenize_roles:
            self._audit("detokenize", role, token, False, "role not authorized")
            raise PermissionError(f"role '{role}' is not authorized to detokenize")
        row = self.db.execute("SELECT pan_ct FROM vault WHERE token = ?", (token,)).fetchone()
        if row is None:
            self._audit("detokenize", role, token, False, "unknown token")
            raise KeyError("unknown token")
        blob = row[0]
        pan = self._aead.decrypt(blob[:12], blob[12:], token.encode()).decode()
        self._audit("detokenize", role, token, True)
        return pan

    def audit_log(self) -> list[tuple]:
        return self.db.execute("SELECT action, role, token, allowed, reason FROM audit ORDER BY id").fetchall()


if __name__ == "__main__":
    vault = TokenVault(os.urandom(32), os.urandom(32))
    for pan in ["4111111111111111", "5555 5555 5555 4444", "378282246310005"]:
        tok = vault.tokenize(pan)
        d = normalize_pan(pan)
        print(f"{d[:6]}{'*' * (len(d) - 10)}{d[-4:]} -> {tok}  token_luhn_valid={luhn_valid(tok)}")
    tok = vault.tokenize("4111111111111111")
    print("same PAN, same token:", tok == vault.tokenize("4111 1111 1111 1111"))
    print("detokenize as payment-settlement:", vault.detokenize(tok, "payment-settlement")[-4:], "(last four shown)")
    try:
        vault.detokenize(tok, "marketing-analyst")
    except PermissionError as exc:
        print("detokenize as marketing-analyst:", exc)
