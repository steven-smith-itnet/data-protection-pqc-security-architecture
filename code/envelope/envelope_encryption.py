#!/usr/bin/env python3
"""Envelope encryption with an algorithm-agile, versioned header.

Pattern (Phase 2 key management, Phase 3 and 4 field and object encryption):

    plaintext --AES-256-GCM(DEK)--> ciphertext
    DEK       --wrap(KEK)---------> wrapped DEK   (KEK never leaves the KMS or HSM)

The output blob is self-describing so that algorithms and key-encryption keys
(KEKs) can change without a flag day:

    +-------+---------+------------+-----------------------------+------------------+
    | magic | version | header len | header (canonical JSON)     | ciphertext + tag |
    | "DPE" | 1 byte  | 2 bytes BE | alg, kek, wdek, nonce, ctx  |                  |
    +-------+---------+------------+-----------------------------+------------------+

Header fields:
    v      format version (1)
    alg    data algorithm id from ALGORITHMS (AES-256-GCM by default)
    kek    {"provider", "id", "alg"}: which KEK wrapped the DEK and how
    wdek   wrapped DEK, base64
    nonce  96-bit nonce, base64
    ctx    encryption context: non-secret key/value pairs (for example the
           data-classification and data-domain tags and a record id). It is
           bound to the ciphertext as AAD and passed to the KEK provider
           (AWS KMS EncryptionContext, GCP KMS additional_authenticated_data).

The data AAD covers v, alg, nonce, and ctx, but not kek or wdek. That is
deliberate: re-wrapping the DEK under a new KEK (key rotation or migration
between providers) rewrites only the header and leaves the ciphertext bytes
unchanged. Substituting a different wrapped DEK does not help an attacker:
it unwraps to a different key and GCM authentication fails.

KEK providers:
    LocalKek            AES key wrap (RFC 3394) or AES-256-GCM wrap with the
                        context as AAD. For demonstration and tests only: the
                        KEK is in process memory.
    AwsKmsKek           boto3 KMS generate_data_key / encrypt / decrypt with
                        EncryptionContext.
    AzureKeyVaultKek    azure-keyvault-keys CryptographyClient wrap_key /
                        unwrap_key.
    GcpKmsKek           google-cloud-kms encrypt / decrypt with
                        additional_authenticated_data.

The cloud adapters import their SDKs lazily and have NOT been run against real
cloud services in this repository (no credentials in the build environment).
Their call wiring is exercised in code/tests/ with stub clients only.
"""
from __future__ import annotations

import base64
import json
import os
import struct
from abc import ABC, abstractmethod
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
from cryptography.hazmat.primitives.keywrap import InvalidUnwrap, aes_key_unwrap, aes_key_wrap

MAGIC = b"DPE"
FORMAT_VERSION = 1
DEK_BYTES = 32
NONCE_BYTES = 12

# Algorithm registry. Adding an algorithm means adding an entry here; old
# blobs keep decrypting because the header names the algorithm they used.
ALGORITHMS = {
    "AES-256-GCM": AESGCM,
    "CHACHA20-POLY1305": ChaCha20Poly1305,
}
DEFAULT_ALGORITHM = "AES-256-GCM"


class EnvelopeError(Exception):
    """Raised for any decryption, integrity, or context failure."""


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _unb64(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"), validate=True)


def canonical_context(context: dict[str, str] | None) -> bytes:
    context = context or {}
    for k, v in context.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise TypeError("encryption context keys and values must be strings")
    return json.dumps(context, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True)
class WrappedKey:
    provider: str
    kek_id: str
    kek_alg: str
    blob: bytes


# --------------------------------------------------------------------------
# KEK provider interface
# --------------------------------------------------------------------------


class KekProvider(ABC):
    provider_name: str = "abstract"

    def generate_data_key(self, context: dict[str, str]) -> tuple[bytes, WrappedKey]:
        """Return (plaintext DEK, wrapped DEK). Providers with a native
        generate-data-key call (AWS KMS) override this."""
        dek = os.urandom(DEK_BYTES)
        return dek, self.wrap(dek, context)

    @abstractmethod
    def wrap(self, dek: bytes, context: dict[str, str]) -> WrappedKey: ...

    @abstractmethod
    def unwrap(self, wrapped: WrappedKey, context: dict[str, str]) -> bytes: ...


class LocalKek(KekProvider):
    """In-memory KEK for demonstration and tests. Never use for real data:
    the KEK is not in an HSM and there is no access control or audit."""

    provider_name = "local"

    def __init__(self, kek_id: str, key: bytes | None = None, mode: str = "AES-GCM"):
        if mode not in ("AES-KW", "AES-GCM"):
            raise ValueError("mode must be AES-KW or AES-GCM")
        self.kek_id = kek_id
        self.key = key if key is not None else os.urandom(32)
        if len(self.key) != 32:
            raise ValueError("local KEK must be 256 bits")
        self.mode = mode

    def wrap(self, dek: bytes, context: dict[str, str]) -> WrappedKey:
        if self.mode == "AES-KW":
            # RFC 3394 has no AAD input; the context is still bound to the
            # data through the data-layer AAD.
            blob = aes_key_wrap(self.key, dek)
            return WrappedKey(self.provider_name, self.kek_id, "AES-256-KW", blob)
        nonce = os.urandom(NONCE_BYTES)
        blob = nonce + AESGCM(self.key).encrypt(nonce, dek, canonical_context(context))
        return WrappedKey(self.provider_name, self.kek_id, "AES-256-GCM-WRAP", blob)

    def unwrap(self, wrapped: WrappedKey, context: dict[str, str]) -> bytes:
        if wrapped.kek_id != self.kek_id:
            raise EnvelopeError(f"wrapped by {wrapped.kek_id}, this provider holds {self.kek_id}")
        try:
            if wrapped.kek_alg == "AES-256-KW":
                return aes_key_unwrap(self.key, wrapped.blob)
            if wrapped.kek_alg == "AES-256-GCM-WRAP":
                nonce, ct = wrapped.blob[:NONCE_BYTES], wrapped.blob[NONCE_BYTES:]
                return AESGCM(self.key).decrypt(nonce, ct, canonical_context(context))
        except (InvalidUnwrap, InvalidTag) as exc:
            raise EnvelopeError("DEK unwrap failed (wrong KEK, wrong context, or tampered key)") from exc
        raise EnvelopeError(f"unsupported local wrap algorithm {wrapped.kek_alg}")


class LocalKeyring(KekProvider):
    """Holds several local KEK versions so old blobs can be unwrapped after
    rotation; new wraps use the current (last added) version."""

    provider_name = "local"

    def __init__(self, *keks: LocalKek):
        self.keks = {k.kek_id: k for k in keks}
        self.current = keks[-1]

    def add(self, kek: LocalKek) -> None:
        self.keks[kek.kek_id] = kek
        self.current = kek

    def wrap(self, dek: bytes, context: dict[str, str]) -> WrappedKey:
        return self.current.wrap(dek, context)

    def unwrap(self, wrapped: WrappedKey, context: dict[str, str]) -> bytes:
        kek = self.keks.get(wrapped.kek_id)
        if kek is None:
            raise EnvelopeError(f"KEK {wrapped.kek_id} not in keyring (destroyed or never present)")
        return kek.unwrap(wrapped, context)


class AwsKmsKek(KekProvider):
    """AWS KMS symmetric KMS key as KEK. UNTESTED against AWS in this repo.

    Uses GenerateDataKey (KeySpec AES_256) so the plaintext DEK is generated
    inside KMS, and passes the context as EncryptionContext, which KMS binds
    to the ciphertext and records in CloudTrail. Requires boto3 and IAM
    permissions kms:GenerateDataKey, kms:Encrypt, kms:Decrypt on the key.
    """

    provider_name = "aws-kms"

    def __init__(self, key_id: str, client=None, region_name: str | None = None):
        self.key_id = key_id
        if client is None:
            import boto3  # lazy import: optional dependency

            client = boto3.client("kms", region_name=region_name)
        self.client = client

    def generate_data_key(self, context: dict[str, str]) -> tuple[bytes, WrappedKey]:
        resp = self.client.generate_data_key(KeyId=self.key_id, KeySpec="AES_256", EncryptionContext=context)
        wrapped = WrappedKey(self.provider_name, resp["KeyId"], "SYMMETRIC_DEFAULT", resp["CiphertextBlob"])
        return resp["Plaintext"], wrapped

    def wrap(self, dek: bytes, context: dict[str, str]) -> WrappedKey:
        resp = self.client.encrypt(KeyId=self.key_id, Plaintext=dek, EncryptionContext=context)
        return WrappedKey(self.provider_name, resp["KeyId"], "SYMMETRIC_DEFAULT", resp["CiphertextBlob"])

    def unwrap(self, wrapped: WrappedKey, context: dict[str, str]) -> bytes:
        # KeyId is optional for symmetric keys but pinning it prevents a
        # ciphertext from being decrypted under an unexpected key.
        resp = self.client.decrypt(CiphertextBlob=wrapped.blob, EncryptionContext=context, KeyId=wrapped.kek_id)
        return resp["Plaintext"]


class AzureKeyVaultKek(KekProvider):
    """Azure Key Vault or Managed HSM key as KEK. UNTESTED against Azure in this repo.

    Uses CryptographyClient.wrap_key / unwrap_key. RSA-OAEP-256 is the default
    for RSA keys; use algorithm "A256KW" with an AES key in Managed HSM.
    Key Vault wrap operations take no AAD, so the context is bound only at the
    data layer (the envelope AAD). Requires azure-keyvault-keys and
    azure-identity, and the Key Vault Crypto User role (or wrapKey/unwrapKey
    access policy permissions).
    """

    provider_name = "azure-keyvault"

    def __init__(self, key_id: str, client=None, credential=None, algorithm: str = "RSA-OAEP-256"):
        self.key_id = key_id
        self.algorithm_name = algorithm
        if client is None:
            from azure.identity import DefaultAzureCredential  # lazy import
            from azure.keyvault.keys.crypto import CryptographyClient

            client = CryptographyClient(key_id, credential or DefaultAzureCredential())
        self.client = client

    def _alg(self):
        try:
            from azure.keyvault.keys.crypto import KeyWrapAlgorithm

            return KeyWrapAlgorithm(self.algorithm_name)
        except ImportError:  # stub clients in tests
            return self.algorithm_name

    def wrap(self, dek: bytes, context: dict[str, str]) -> WrappedKey:
        result = self.client.wrap_key(self._alg(), dek)
        return WrappedKey(self.provider_name, result.key_id or self.key_id, self.algorithm_name, result.encrypted_key)

    def unwrap(self, wrapped: WrappedKey, context: dict[str, str]) -> bytes:
        return self.client.unwrap_key(self._alg(), wrapped.blob).key


class GcpKmsKek(KekProvider):
    """Google Cloud KMS symmetric key as KEK. UNTESTED against Google Cloud in this repo.

    Uses encrypt / decrypt with additional_authenticated_data set to the
    canonical context. Requires google-cloud-kms and roles/cloudkms.cryptoKeyEncrypterDecrypter.
    key_name: projects/P/locations/L/keyRings/R/cryptoKeys/K
    """

    provider_name = "gcp-kms"

    def __init__(self, key_name: str, client=None):
        self.key_name = key_name
        if client is None:
            from google.cloud import kms  # lazy import

            client = kms.KeyManagementServiceClient()
        self.client = client

    def wrap(self, dek: bytes, context: dict[str, str]) -> WrappedKey:
        resp = self.client.encrypt(
            request={"name": self.key_name, "plaintext": dek, "additional_authenticated_data": canonical_context(context)}
        )
        # resp.name is the key version used; decrypt must target the key, not the version.
        return WrappedKey(self.provider_name, self.key_name, "GOOGLE_SYMMETRIC_ENCRYPTION", resp.ciphertext)

    def unwrap(self, wrapped: WrappedKey, context: dict[str, str]) -> bytes:
        resp = self.client.decrypt(
            request={
                "name": wrapped.kek_id,
                "ciphertext": wrapped.blob,
                "additional_authenticated_data": canonical_context(context),
            }
        )
        return resp.plaintext


# --------------------------------------------------------------------------
# Envelope format
# --------------------------------------------------------------------------


def _data_aad(header: dict) -> bytes:
    bound = {"v": header["v"], "alg": header["alg"], "nonce": header["nonce"], "ctx": header["ctx"]}
    return MAGIC + json.dumps(bound, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _pack(header: dict, ciphertext: bytes) -> bytes:
    hbytes = json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(hbytes) > 0xFFFF:
        raise EnvelopeError("header too large")
    return MAGIC + bytes([FORMAT_VERSION]) + struct.pack(">H", len(hbytes)) + hbytes + ciphertext


def parse(blob: bytes) -> tuple[dict, bytes]:
    if len(blob) < 6 or blob[:3] != MAGIC:
        raise EnvelopeError("not an envelope blob")
    version = blob[3]
    if version != FORMAT_VERSION:
        raise EnvelopeError(f"unsupported format version {version}")
    (hlen,) = struct.unpack(">H", blob[4:6])
    try:
        header = json.loads(blob[6 : 6 + hlen])
    except ValueError as exc:
        raise EnvelopeError("header is not valid JSON") from exc
    if header.get("v") != version:
        raise EnvelopeError("header version does not match framing version")
    return header, blob[6 + hlen :]


def encrypt(
    plaintext: bytes,
    kek: KekProvider,
    context: dict[str, str] | None = None,
    algorithm: str = DEFAULT_ALGORITHM,
) -> bytes:
    if algorithm not in ALGORITHMS:
        raise EnvelopeError(f"unknown algorithm {algorithm}")
    context = dict(context or {})
    canonical_context(context)  # type check
    dek, wrapped = kek.generate_data_key(context)
    nonce = os.urandom(NONCE_BYTES)
    header = {
        "v": FORMAT_VERSION,
        "alg": algorithm,
        "kek": {"provider": wrapped.provider, "id": wrapped.kek_id, "alg": wrapped.kek_alg},
        "wdek": _b64(wrapped.blob),
        "nonce": _b64(nonce),
        "ctx": context,
    }
    ct = ALGORITHMS[algorithm](dek).encrypt(nonce, plaintext, _data_aad(header))
    return _pack(header, ct)


def _wrapped_from_header(header: dict) -> WrappedKey:
    k = header["kek"]
    return WrappedKey(k["provider"], k["id"], k["alg"], _unb64(header["wdek"]))


def decrypt(blob: bytes, kek: KekProvider, expected_context: dict[str, str] | None = None) -> bytes:
    """Decrypt a blob. If expected_context is given, every pair in it must be
    present in the stored context (same rule as the AWS Encryption SDK's
    required encryption context); this stops a caller being handed a valid
    ciphertext that belongs to a different record or classification."""
    header, ct = parse(blob)
    ctx = header["ctx"]
    if expected_context is not None:
        for k, v in expected_context.items():
            if ctx.get(k) != v:
                raise EnvelopeError(f"encryption context mismatch on '{k}'")
    alg = header["alg"]
    if alg not in ALGORITHMS:
        raise EnvelopeError(f"unknown algorithm {alg}")
    dek = kek.unwrap(_wrapped_from_header(header), ctx)
    try:
        return ALGORITHMS[alg](dek).decrypt(_unb64(header["nonce"]), ct, _data_aad(header))
    except InvalidTag as exc:
        raise EnvelopeError("authentication failed: ciphertext, header, or context was modified") from exc


def rewrap(blob: bytes, old_kek: KekProvider, new_kek: KekProvider) -> bytes:
    """Re-wrap the DEK under a new KEK without touching the data ciphertext.

    Used for KEK rotation and provider migration. The plaintext DEK exists in
    memory briefly; with AWS KMS, ReEncrypt performs the same operation
    server side without exposing the DEK to the caller.
    """
    header, ct = parse(blob)
    dek = old_kek.unwrap(_wrapped_from_header(header), header["ctx"])
    wrapped = new_kek.wrap(dek, header["ctx"])
    header = dict(header)
    header["kek"] = {"provider": wrapped.provider, "id": wrapped.kek_id, "alg": wrapped.kek_alg}
    header["wdek"] = _b64(wrapped.blob)
    return _pack(header, ct)


def describe(blob: bytes) -> dict:
    """Return the header without decrypting (safe for inventory and CBOM tooling)."""
    header, ct = parse(blob)
    return {**header, "wdek": f"<{len(_unb64(header['wdek']))} bytes>", "ciphertext_bytes": len(ct)}


if __name__ == "__main__":
    ctx = {"data-classification": "restricted", "data-domain": "guest", "record-id": "G-0001"}
    kek_v1 = LocalKek("local:kek-guest-v1")
    blob = encrypt(b"passport=X00000001", kek_v1, ctx)
    print("header:", json.dumps(describe(blob), indent=2))
    print("decrypted:", decrypt(blob, kek_v1, expected_context={"record-id": "G-0001"}))
    kek_v2 = LocalKek("local:kek-guest-v2")
    blob2 = rewrap(blob, kek_v1, kek_v2)
    print("after rewrap, kek:", describe(blob2)["kek"], "ciphertext unchanged:", parse(blob)[1] == parse(blob2)[1])
    print("decrypted with v2:", decrypt(blob2, kek_v2))
