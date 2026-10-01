import os

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import envelope_encryption as env

CTX = {"data-classification": "restricted", "data-domain": "guest", "record-id": "G-0001"}


@pytest.mark.parametrize("mode", ["AES-GCM", "AES-KW"])
@pytest.mark.parametrize("alg", sorted(env.ALGORITHMS))
def test_roundtrip(mode, alg):
    kek = env.LocalKek("local:kek-v1", mode=mode)
    blob = env.encrypt(b"passport=X00000001", kek, CTX, algorithm=alg)
    assert env.decrypt(blob, kek) == b"passport=X00000001"
    header, _ = env.parse(blob)
    assert header["alg"] == alg and header["v"] == 1 and header["ctx"] == CTX


def test_each_encryption_uses_fresh_dek_and_nonce():
    kek = env.LocalKek("local:kek-v1")
    a, b = env.encrypt(b"x", kek, CTX), env.encrypt(b"x", kek, CTX)
    ha, hb = env.parse(a)[0], env.parse(b)[0]
    assert ha["nonce"] != hb["nonce"] and ha["wdek"] != hb["wdek"]


def test_ciphertext_tamper_detected():
    kek = env.LocalKek("local:kek-v1")
    blob = bytearray(env.encrypt(b"guest record", kek, CTX))
    blob[-1] ^= 0x01
    with pytest.raises(env.EnvelopeError, match="authentication failed"):
        env.decrypt(bytes(blob), kek)


def test_header_context_tamper_detected():
    # Rewriting the stored context (e.g. downgrading the classification) breaks
    # the KEK unwrap (AES-GCM wrap binds the context) or the data AAD.
    for mode in ("AES-GCM", "AES-KW"):
        kek = env.LocalKek("local:kek-v1", mode=mode)
        blob = env.encrypt(b"guest record", kek, CTX)
        header, ct = env.parse(blob)
        header["ctx"] = {**CTX, "data-classification": "internal"}
        with pytest.raises(env.EnvelopeError):
            env.decrypt(env._pack(header, ct), kek)


def test_algorithm_downgrade_in_header_detected():
    kek = env.LocalKek("local:kek-v1")
    header, ct = env.parse(env.encrypt(b"guest record", kek, CTX))
    header["alg"] = "CHACHA20-POLY1305"
    with pytest.raises(env.EnvelopeError):
        env.decrypt(env._pack(header, ct), kek)


def test_wrong_expected_context_rejected():
    kek = env.LocalKek("local:kek-v1")
    blob = env.encrypt(b"guest record", kek, CTX)
    assert env.decrypt(blob, kek, expected_context={"record-id": "G-0001"}) == b"guest record"
    with pytest.raises(env.EnvelopeError, match="context mismatch"):
        env.decrypt(blob, kek, expected_context={"record-id": "G-0002"})


def test_wrong_kek_rejected():
    blob = env.encrypt(b"x", env.LocalKek("local:kek-v1"), CTX)
    with pytest.raises(env.EnvelopeError):
        env.decrypt(blob, env.LocalKek("local:kek-v1"))  # same id, different key material


def test_rotation_rewrap_without_reencrypting_data():
    v1, v2 = env.LocalKek("local:kek-v1"), env.LocalKek("local:kek-v2", mode="AES-KW")
    blob = env.encrypt(b"stay history", v1, CTX)
    rewrapped = env.rewrap(blob, v1, v2)
    assert env.parse(blob)[1] == env.parse(rewrapped)[1]  # ciphertext bytes identical
    assert env.parse(rewrapped)[0]["kek"]["id"] == "local:kek-v2"
    assert env.decrypt(rewrapped, v2) == b"stay history"
    with pytest.raises(env.EnvelopeError):
        env.decrypt(rewrapped, v1)


def test_keyring_reads_old_and_new_after_rotation_and_fails_after_destroy():
    v1, v2 = env.LocalKek("local:kek-v1"), env.LocalKek("local:kek-v2")
    ring = env.LocalKeyring(v1)
    old = env.encrypt(b"old", ring, CTX)
    ring.add(v2)
    new = env.encrypt(b"new", ring, CTX)
    assert env.parse(new)[0]["kek"]["id"] == "local:kek-v2"
    assert env.decrypt(old, ring) == b"old" and env.decrypt(new, ring) == b"new"
    del ring.keks["local:kek-v1"]  # KEK destroyed: everything wrapped only by it is gone
    with pytest.raises(env.EnvelopeError, match="not in keyring"):
        env.decrypt(old, ring)


def test_bad_framing_rejected():
    with pytest.raises(env.EnvelopeError):
        env.parse(b"XXX\x01\x00\x02{}")
    blob = bytearray(env.encrypt(b"x", env.LocalKek("k"), CTX))
    blob[3] = 9
    with pytest.raises(env.EnvelopeError, match="unsupported format version"):
        env.parse(bytes(blob))


def test_context_values_must_be_strings():
    with pytest.raises(TypeError):
        env.encrypt(b"x", env.LocalKek("k"), {"n": 1})


def test_describe_does_not_expose_wrapped_key():
    d = env.describe(env.encrypt(b"x", env.LocalKek("k"), CTX))
    assert d["wdek"].startswith("<") and d["ciphertext_bytes"] == 17


# ---- cloud adapters: call wiring only, with stub clients (no cloud calls) ----

class _StubKms:
    """Mimics the parts of each SDK the adapters call; binds context like the real services."""

    def __init__(self):
        self.key = AESGCM.generate_key(bit_length=256)
        self.calls = []

    def _enc(self, pt, aad):
        n = os.urandom(12)
        return n + AESGCM(self.key).encrypt(n, pt, aad)

    def _dec(self, ct, aad):
        return AESGCM(self.key).decrypt(ct[:12], ct[12:], aad)


class StubAws(_StubKms):
    def generate_data_key(self, KeyId, KeySpec, EncryptionContext):
        self.calls.append(("generate_data_key", KeyId, KeySpec, dict(EncryptionContext)))
        dek = os.urandom(32)
        return {"Plaintext": dek, "CiphertextBlob": self._enc(dek, env.canonical_context(EncryptionContext)), "KeyId": KeyId}

    def encrypt(self, KeyId, Plaintext, EncryptionContext):
        self.calls.append(("encrypt", KeyId))
        return {"CiphertextBlob": self._enc(Plaintext, env.canonical_context(EncryptionContext)), "KeyId": KeyId}

    def decrypt(self, CiphertextBlob, EncryptionContext, KeyId):
        self.calls.append(("decrypt", KeyId, dict(EncryptionContext)))
        return {"Plaintext": self._dec(CiphertextBlob, env.canonical_context(EncryptionContext))}


class StubAzure(_StubKms):
    class _R:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    def wrap_key(self, alg, key):
        self.calls.append(("wrap_key", str(alg)))
        return self._R(encrypted_key=self._enc(key, b""), key_id="https://kv.example/keys/guest/1")

    def unwrap_key(self, alg, encrypted_key):
        self.calls.append(("unwrap_key", str(alg)))
        return self._R(key=self._dec(encrypted_key, b""))


class StubGcp(_StubKms):
    class _R:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    def encrypt(self, request):
        self.calls.append(("encrypt", request["name"], request["additional_authenticated_data"]))
        return self._R(ciphertext=self._enc(request["plaintext"], request["additional_authenticated_data"]),
                       name=request["name"] + "/cryptoKeyVersions/1")

    def decrypt(self, request):
        self.calls.append(("decrypt", request["name"]))
        return self._R(plaintext=self._dec(request["ciphertext"], request["additional_authenticated_data"]))


def test_aws_adapter_wiring():
    stub = StubAws()
    kek = env.AwsKmsKek("arn:aws:kms:eu-west-1:111122223333:key/example", client=stub)
    blob = env.encrypt(b"card token map", kek, CTX)
    assert env.decrypt(blob, kek) == b"card token map"
    assert stub.calls[0] == ("generate_data_key", kek.key_id, "AES_256", CTX)
    assert stub.calls[1] == ("decrypt", kek.key_id, CTX)


def test_azure_adapter_wiring():
    stub = StubAzure()
    kek = env.AzureKeyVaultKek("https://kv.example/keys/guest", client=stub)
    blob = env.encrypt(b"guest", kek, CTX)
    assert env.decrypt(blob, kek) == b"guest"
    assert env.parse(blob)[0]["kek"] == {"provider": "azure-keyvault", "id": "https://kv.example/keys/guest/1", "alg": "RSA-OAEP-256"}


def test_gcp_adapter_wiring_and_rewrap_across_providers():
    stub = StubGcp()
    name = "projects/p/locations/europe-west1/keyRings/data/cryptoKeys/guest-kek"
    kek = env.GcpKmsKek(name, client=stub)
    blob = env.encrypt(b"guest", kek, CTX)
    assert stub.calls[0] == ("encrypt", name, env.canonical_context(CTX))
    assert env.decrypt(blob, kek) == b"guest"
    local = env.LocalKek("local:migration")
    moved = env.rewrap(blob, kek, local)  # provider migration, data untouched
    assert env.decrypt(moved, local) == b"guest"
