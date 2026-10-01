#!/usr/bin/env python3
"""Crypto-shredding with per-data-subject DEKs (Phase 5: retention and erasure).

Problem: a guest asks for erasure (GDPR Art. 17, CCPA deletion). Their data is
spread across the primary database, the data lake, and backups that are
immutable or retained for years. Deleting every copy is slow and sometimes
impossible (WORM backups, object lock).

Pattern: encrypt each data subject's records with a data encryption key (DEK)
that belongs to that subject only. The DEK is stored wrapped by a KEK in a
separate key store. To erase the subject, destroy the wrapped DEK. Every copy
of the ciphertext, including copies in backups, becomes unreadable, while
other subjects' data is untouched.

Conditions for this to count as erasure (state them in the design review):
* The key store is not backed up alongside the data, or key backups expire
  on a shorter schedule than the erasure SLA.
* No plaintext copies exist outside the pattern (caches, exports, logs).
* The KEK and DEK algorithms are strong enough for the data's shelf life
  (AES-256; see the PQC section on harvest now, decrypt later).
* NIST SP 800-88 Rev. 1 describes cryptographic erase for media; this applies
  the same idea per subject rather than per device.

Demo: the KEK is a local AES-256 key. In production it is a KMS or HSM key
(see code/envelope/), and SQLite is replaced by the real stores.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class SubjectErasedError(Exception):
    """The subject's key has been destroyed; their data is unrecoverable."""


class CryptoShredStore:
    def __init__(self, kek: bytes, key_db: str = ":memory:", data_db: str = ":memory:", kek_id: str = "local:kek-v1"):
        if len(kek) != 32:
            raise ValueError("KEK must be 256 bits")
        self._kek = AESGCM(kek)
        self.kek_id = kek_id
        # Keys and data live in separate databases to mirror separate stores
        # with separate backup policies.
        self.keys = sqlite3.connect(key_db)
        self.data = sqlite3.connect(data_db)
        # secure_delete overwrites deleted content in the SQLite file.
        self.keys.execute("PRAGMA secure_delete = ON")
        self.keys.executescript(
            """
            CREATE TABLE IF NOT EXISTS subject_keys (
                subject_id  TEXT PRIMARY KEY,
                kek_id      TEXT,
                wrapped_dek BLOB,
                created_at  TEXT NOT NULL,
                shredded_at TEXT
            );
            """
        )
        self.data.executescript(
            """
            CREATE TABLE IF NOT EXISTS records (
                record_id  TEXT PRIMARY KEY,
                subject_id TEXT NOT NULL,
                nonce      BLOB NOT NULL,
                ciphertext BLOB NOT NULL
            );
            """
        )

    # ---- key handling -------------------------------------------------

    def _wrap(self, subject_id: str, dek: bytes) -> bytes:
        nonce = os.urandom(12)
        return nonce + self._kek.encrypt(nonce, dek, f"subject:{subject_id}".encode())

    def _unwrap(self, subject_id: str, blob: bytes) -> bytes:
        return self._kek.decrypt(blob[:12], blob[12:], f"subject:{subject_id}".encode())

    def _subject_dek(self, subject_id: str, create: bool) -> bytes:
        row = self.keys.execute(
            "SELECT wrapped_dek, shredded_at FROM subject_keys WHERE subject_id = ?", (subject_id,)
        ).fetchone()
        if row is None:
            if not create:
                raise KeyError(f"no key for subject {subject_id}")
            dek = AESGCM.generate_key(bit_length=256)
            self.keys.execute(
                "INSERT INTO subject_keys (subject_id, kek_id, wrapped_dek, created_at) VALUES (?,?,?,?)",
                (subject_id, self.kek_id, self._wrap(subject_id, dek), datetime.now(timezone.utc).isoformat()),
            )
            self.keys.commit()
            return dek
        wrapped, shredded_at = row
        if shredded_at is not None or wrapped is None:
            raise SubjectErasedError(f"subject {subject_id} was crypto-shredded at {shredded_at}")
        return self._unwrap(subject_id, wrapped)

    # ---- data API -----------------------------------------------------

    def put(self, subject_id: str, record_id: str, plaintext: bytes) -> None:
        dek = self._subject_dek(subject_id, create=True)
        nonce = os.urandom(12)
        aad = f"{subject_id}|{record_id}".encode()
        ct = AESGCM(dek).encrypt(nonce, plaintext, aad)
        self.data.execute(
            "INSERT OR REPLACE INTO records (record_id, subject_id, nonce, ciphertext) VALUES (?,?,?,?)",
            (record_id, subject_id, nonce, ct),
        )
        self.data.commit()

    def get(self, record_id: str) -> bytes:
        row = self.data.execute(
            "SELECT subject_id, nonce, ciphertext FROM records WHERE record_id = ?", (record_id,)
        ).fetchone()
        if row is None:
            raise KeyError(record_id)
        subject_id, nonce, ct = row
        return self.decrypt_record(subject_id, record_id, nonce, ct)

    def decrypt_record(self, subject_id: str, record_id: str, nonce: bytes, ct: bytes) -> bytes:
        """Decrypt a record from any copy (primary or backup)."""
        dek = self._subject_dek(subject_id, create=False)
        try:
            return AESGCM(dek).decrypt(nonce, ct, f"{subject_id}|{record_id}".encode())
        except InvalidTag as exc:
            raise ValueError("record failed authentication") from exc

    def export_backup(self) -> list[tuple]:
        """Simulate an immutable backup: a copy of the ciphertext rows only."""
        return self.data.execute("SELECT record_id, subject_id, nonce, ciphertext FROM records").fetchall()

    def shred(self, subject_id: str) -> dict:
        """Destroy one subject's DEK. Ciphertext rows are left in place on
        purpose to show that they are now unreadable; deleting them as well is
        still good hygiene."""
        cur = self.keys.execute(
            "UPDATE subject_keys SET wrapped_dek = NULL, kek_id = NULL, shredded_at = ? "
            "WHERE subject_id = ? AND shredded_at IS NULL",
            (datetime.now(timezone.utc).isoformat(), subject_id),
        )
        self.keys.commit()
        if cur.rowcount != 1:
            raise KeyError(f"no active key for subject {subject_id}")
        remaining = self.data.execute("SELECT COUNT(*) FROM records WHERE subject_id = ?", (subject_id,)).fetchone()[0]
        return {"subject_id": subject_id, "key_destroyed": True, "ciphertext_rows_now_unreadable": remaining}


if __name__ == "__main__":
    store = CryptoShredStore(os.urandom(32))
    store.put("guest-0001", "stay-1", b"Test Guest Alpha, room 1204, allergy: peanuts")
    store.put("guest-0001", "stay-2", b"Test Guest Alpha, room 0807")
    store.put("guest-0002", "stay-3", b"Test Guest Bravo, room 0311")
    backup = store.export_backup()
    print("before:", store.get("stay-1"))
    print("shred :", store.shred("guest-0001"))
    for record_id, subject_id, nonce, ct in backup:
        try:
            print(f"backup {record_id} ({subject_id}):", store.decrypt_record(subject_id, record_id, nonce, ct))
        except SubjectErasedError as exc:
            print(f"backup {record_id} ({subject_id}): unreadable -> {exc}")
