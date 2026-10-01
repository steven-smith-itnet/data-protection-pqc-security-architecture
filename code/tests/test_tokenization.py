import os

import pytest

import keyed_hash as kh
import pii_scanner as ps
import vault_tokenizer as vt

PANS = ["4111111111111111", "5555555555554444", "378282246310005", "6011111111111117", "4222222222222"]


@pytest.fixture
def vault():
    return vt.TokenVault(os.urandom(32), os.urandom(32))


@pytest.mark.parametrize("pan", PANS)
def test_token_format_properties(pan):
    for _ in range(500):
        tok = vt.make_token(pan)
        assert len(tok) == len(pan) and tok.isdigit()
        assert tok[-4:] == pan[-4:]
        assert not vt.luhn_valid(tok)
        assert tok[0] != "0"


def test_same_pan_same_token_and_formatting_ignored(vault):
    t = vault.tokenize("4111111111111111")
    assert vault.tokenize("4111 1111 1111 1111") == t
    assert vault.tokenize("4111-1111-1111-1111") == t
    assert vault.tokenize("5555555555554444") != t


def test_invalid_pan_rejected(vault):
    for bad in ("4111111111111112", "12345", "4111x11111111111"):
        with pytest.raises(ValueError):
            vault.tokenize(bad)


def test_detokenize_requires_authorized_role(vault):
    t = vault.tokenize("378282246310005")
    assert vault.detokenize(t, "payment-settlement") == "378282246310005"
    with pytest.raises(PermissionError):
        vault.detokenize(t, "marketing-analyst")
    with pytest.raises(KeyError):
        vault.detokenize("0000000000000000", "payment-settlement")
    log = vault.audit_log()
    assert ("detokenize", "payment-settlement", t, 1, "") in log
    assert ("detokenize", "marketing-analyst", t, 0, "role not authorized") in log


def test_vault_stores_no_plaintext_pan(tmp_path):
    db = tmp_path / "vault.db"
    v = vt.TokenVault(os.urandom(32), os.urandom(32), db_path=str(db))
    v.tokenize("4111111111111111")
    v.db.close()
    assert b"4111111111111111" not in db.read_bytes()


def test_tokens_are_not_flagged_by_the_discovery_scanner(vault):
    text = " ".join(vault.tokenize(p) for p in PANS)
    findings = ps.scan_text(text, ps.build_detectors())
    assert [f for f in findings if f.type == "pan"] == []
    # ...while the real PANs are.
    assert len([f for f in ps.scan_text(" ".join(PANS), ps.build_detectors()) if f.type == "pan"]) == len(PANS)


# ---- keyed-hash surrogates ----

def test_surrogate_deterministic_and_normalized():
    keys = kh.SurrogateKeys(os.urandom(32))
    a = keys.surrogate(" Alpha.Guest@Example.com", "email", "marketing-analytics")
    b = keys.surrogate("alpha.guest@example.com", "email", "marketing-analytics")
    assert a == b and a.startswith("v1_") and len(a) == 35


def test_surrogate_purpose_and_key_separation():
    root = os.urandom(32)
    k1, k2 = kh.SurrogateKeys(root), kh.SurrogateKeys(os.urandom(32))
    v = "alpha.guest@example.com"
    assert k1.surrogate(v, "email", "marketing-analytics") != k1.surrogate(v, "email", "fraud-analytics")
    assert k1.surrogate(v, "email", "marketing-analytics") != k2.surrogate(v, "email", "marketing-analytics")
    assert kh.SurrogateKeys(root, "v2").surrogate(v, "email", "m").startswith("v2_")


def test_surrogate_is_not_a_plain_hash():
    import hashlib

    keys = kh.SurrogateKeys(os.urandom(32))
    s = keys.surrogate("4111111111111111", "pan", "fraud-analytics", length=64)
    assert s[3:] != hashlib.sha256(b"4111111111111111").hexdigest()
    assert s[3:] != hashlib.sha256(b"pan:4111111111111111").hexdigest()


def test_short_root_key_rejected():
    with pytest.raises(ValueError):
        kh.SurrogateKeys(b"short")
