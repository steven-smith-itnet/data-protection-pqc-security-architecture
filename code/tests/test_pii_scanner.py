import json
import os

import pytest

import pii_scanner as ps

CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES = os.path.join(CODE_DIR, "discovery", "samples")
TEST_PANS = ["4111111111111111", "5555555555554444", "378282246310005", "6011111111111117"]


def scan(text, **kw):
    return ps.scan_text(text, ps.build_detectors(**kw))


def types(findings):
    return sorted(f.type for f in findings)


@pytest.mark.parametrize("pan", TEST_PANS)
def test_luhn_and_brand_on_public_test_cards(pan):
    assert ps.luhn_valid(pan)
    assert ps.card_brand(pan) is not None


def test_luhn_rejects_single_digit_change():
    assert not ps.luhn_valid("4111111111111112")


@pytest.mark.parametrize("text", ["4111 1111 1111 1111", "4111-1111-1111-1111", "3782-822463-10005", "card 5555555555554444."])
def test_pan_detected_in_common_formats(text):
    found = scan(text)
    assert types(found) == ["pan"]


@pytest.mark.parametrize("text", ["4111111111111112", "1234567890123456", "order 9999999999999995"])
def test_pan_false_positives_rejected(text):
    # Luhn failure, or Luhn-valid but no known issuer prefix.
    assert "pan" not in types(scan(text))


def test_pan_mask_shows_at_most_bin_and_last_four():
    (f,) = scan("4111111111111111")
    assert f.masked == "411111******1111"
    assert "4111111111111111" not in f.masked


def test_iban_mod97():
    assert ps.iban_valid("GB82 WEST 1234 5698 7654 32")
    assert ps.iban_valid("DE89370400440532013000")
    assert not ps.iban_valid("GB83 WEST 1234 5698 7654 32")


def test_iban_digits_not_reread_as_pan():
    found = scan("pay to GB82 WEST 1234 5698 7654 32 thanks")
    assert types(found) == ["iban"]


@pytest.mark.parametrize("ssn,ok", [
    ("123-45-6789", True), ("000-12-3456", False), ("666-12-3456", False),
    ("900-12-3456", False), ("123-00-4567", False), ("123-45-0000", False), ("078-05-1120", False),
])
def test_ssn_invalid_ranges(ssn, ok):
    assert (types(scan(f"SSN {ssn}")) == ["ssn"]) is ok


def test_phone_and_email():
    found = scan("call +44 20 7946 0102 or mail a.guest@example.com")
    assert types(found) == ["email", "phone"]


def test_passport_requires_keyword_and_is_low_confidence():
    assert types(scan("ref X00000004")) == []
    (f,) = scan("Passport no. X00000004")
    assert f.type == "passport" and f.confidence == "low"


def test_dob_requires_context():
    assert types(scan("stayed 1980-01-01")) == []
    assert types(scan("date of birth: 1980-01-01")) == ["dob"]


def test_loyalty_regex_is_configurable():
    assert types(scan("member LOY000000001")) == ["loyalty"]
    assert types(scan("member GOLD-12345", loyalty_regex=r"\bGOLD-\d{5}\b")) == ["loyalty"]


def test_samples_report():
    report = ps.scan_path(SAMPLES)
    by_name = {os.path.basename(f["path"]): f for f in report["files"]}

    pay = by_name["payment_capture.json"]["recommendation"]
    assert (pay["tier"], pay["label"], pay["protection_profile"]) == ("C3", "Restricted\\PCI", "pp3")
    assert pay["tags"]["regulatory-scope"] == "pci_gdpr"
    assert pay["tags"]["data-domain"] == "payment"
    assert by_name["payment_capture.json"]["findings"]["pan"]["count"] == 4

    guest = by_name["guest_profiles.csv"]
    assert guest["recommendation"]["tier"] == "C3"
    assert guest["recommendation"]["needs_review"] is True  # C3 driven only by low-confidence passport hits
    assert guest["findings"]["email"]["count"] == 3

    notes = by_name["front_desk_notes.txt"]["findings"]
    assert notes["ssn"]["count"] == 1  # the four excluded test values are not reported
    assert notes["iban"]["count"] == 2

    rates = by_name["published_rates.txt"]["recommendation"]
    assert (rates["tier"], rates["label"], rates["protection_profile"]) == ("C1", "Internal", "pp1")


def test_report_never_contains_full_test_pans():
    blob = json.dumps(ps.scan_path(SAMPLES))
    for pan in TEST_PANS:
        assert pan not in blob


def test_jurisdictions_change_regulatory_scope():
    report = ps.scan_path(os.path.join(SAMPLES, "payment_capture.json"), jurisdictions=["ccpa", "gdpr"])
    assert report["files"][0]["recommendation"]["tags"]["regulatory-scope"] == "pci_gdpr_ccpa"


def test_cli_fail_on_gate(tmp_path, capsys):
    out = tmp_path / "r.json"
    assert ps.main([SAMPLES, "--output", str(out), "--fail-on", "C3"]) == 2
    assert ps.main([os.path.join(SAMPLES, "published_rates.txt"), "--fail-on", "C2"]) == 0
    assert json.loads(out.read_text())["summary"]["files_scanned"] == 4


def test_cli_rejects_unknown_jurisdiction():
    with pytest.raises(SystemExit):
        ps.main([SAMPLES, "--jurisdictions", "hipaa"])
