#!/usr/bin/env python3
"""PII and payment card discovery scanner (Phase 1: Know the data).

Scans a directory of text, CSV, and JSON files and reports, per file:

* findings by type, with counts, a confidence level, and masked samples
  (a full PAN is never printed; at most the BIN and last four are shown,
  in line with PCI DSS v4.0.1 requirement 3.4.1),
* a recommended classification tier (C0 to C3) and Purview-style label,
* the protection profile (pp1, pp2, pp3) that the tier maps to, and
* suggested resource tags using the shared tag schema
  (data-classification, protection-profile, data-domain, regulatory-scope).

Detectors
---------
pan         13 to 19 digits, optional space or dash grouping, Luhn check,
            and a known issuer (IIN) prefix and length.
email       RFC 5322-ish local@domain.tld.
phone       E.164-ish: a leading "+", country code, 8 to 15 digits in total.
iban        ISO 13616 structure and the ISO 7064 mod-97 check.
ssn         US SSN in NNN-NN-NNNN form, excluding invalid ranges
            (area 000, 666, 900-999; group 00; serial 0000) and two widely
            published numbers.
passport    keyword proximity heuristic ("passport" near a 6 to 9 character
            alphanumeric token). Low confidence by design.
dob         date of birth: a date near a DOB keyword. Medium confidence.
loyalty     configurable regular expression (default matches a fictional
            "LOY" + 9 digit member number).

This is a reference implementation for a portfolio. It is not a replacement
for Microsoft Purview, Amazon Macie, Google Sensitive Data Protection, or OCI
Data Safe, which add ML classifiers, exact data match, and scale. It exists
to show the logic that sits behind a recommended label.

Usage
-----
    python pii_scanner.py samples/ --pretty
    python pii_scanner.py /data/export --output report.json --jurisdictions gdpr,ccpa
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Iterable

SCANNER_VERSION = "1.0.0"
DEFAULT_EXTENSIONS = (".txt", ".csv", ".json", ".log", ".md", ".tsv")
DEFAULT_LOYALTY_REGEX = r"\bLOY\d{9}\b"
MAX_SAMPLES = 3

# --------------------------------------------------------------------------
# Classification model (fixed shared model from the architecture)
# --------------------------------------------------------------------------

TIER_ORDER = ["C0", "C1", "C2", "C3"]
TIER_TO_CLASSIFICATION = {
    "C0": "public",
    "C1": "internal",
    "C2": "confidential",
    "C3": "restricted",
}
TIER_TO_PROFILE = {"C0": "pp1", "C1": "pp1", "C2": "pp2", "C3": "pp3"}

# finding type -> (tier, label, data-domain hint, is personal data, is PCI)
FINDING_POLICY = {
    "pan": ("C3", "Restricted\\PCI", "payment", True, True),
    "iban": ("C3", "Restricted\\Guest-Identity", "finance", True, False),
    "ssn": ("C3", "Restricted\\Guest-Identity", "employee", True, False),
    "passport": ("C3", "Restricted\\Guest-Identity", "guest", True, False),
    "dob": ("C2", "Confidential\\Guest-PII", "guest", True, False),
    "email": ("C2", "Confidential\\Guest-PII", "guest", True, False),
    "phone": ("C2", "Confidential\\Guest-PII", "guest", True, False),
    "loyalty": ("C2", "Confidential\\Guest-PII", "loyalty", True, False),
}

# When several labels apply, the highest-priority label wins (Purview label
# priority works the same way). Lower index = higher priority.
LABEL_PRIORITY = [
    "Restricted\\Secrets",
    "Restricted\\PCI",
    "Restricted\\Special-Category",
    "Restricted\\Guest-Identity",
    "Confidential\\Guest-PII",
    "Confidential\\Employee",
    "Confidential\\Business",
    "Internal",
    "Public",
]

# Domain precedence when several domains are hinted.
DOMAIN_PRIORITY = ["payment", "finance", "employee", "guest", "loyalty"]

PRIVACY_REGIMES = ["gdpr", "ccpa", "pipl", "lgpd"]

# --------------------------------------------------------------------------
# Validators
# --------------------------------------------------------------------------


def luhn_valid(digits: str) -> bool:
    """Return True if the digit string passes the Luhn (mod 10) check."""
    if not digits.isdigit():
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def card_brand(digits: str) -> str | None:
    """Return the card brand if the IIN prefix and length match a known scheme."""
    n = len(digits)
    p2, p3, p4 = int(digits[:2]), int(digits[:3]), int(digits[:4])
    if digits[0] == "4" and n in (13, 16, 19):
        return "visa"
    if (51 <= p2 <= 55 or 2221 <= p4 <= 2720) and n == 16:
        return "mastercard"
    if p2 in (34, 37) and n == 15:
        return "amex"
    if (p4 == 6011 or 644 <= p3 <= 649 or p2 == 65) and 16 <= n <= 19:
        return "discover"
    if 3528 <= p4 <= 3589 and 16 <= n <= 19:
        return "jcb"
    if (300 <= p3 <= 305 or p2 in (36, 38, 39)) and 14 <= n <= 19:
        return "diners"
    if p2 == 62 and 16 <= n <= 19:
        return "unionpay"
    return None


def iban_valid(iban: str) -> bool:
    """ISO 7064 mod-97-10 check used by IBAN (result must equal 1)."""
    s = re.sub(r"\s+", "", iban).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", s):
        return False
    rearranged = s[4:] + s[:4]
    numeric = "".join(str(int(c, 36)) for c in rearranged)
    return int(numeric) % 97 == 1


SSN_PUBLICIZED_INVALID = {"078051120", "219099999"}


def ssn_valid(area: str, group: str, serial: str) -> bool:
    a = int(area)
    if a == 0 or a == 666 or a >= 900:
        return False
    if group == "00" or serial == "0000":
        return False
    if area + group + serial in SSN_PUBLICIZED_INVALID:
        return False
    return True


# --------------------------------------------------------------------------
# Masking (never emit a full identifier)
# --------------------------------------------------------------------------


def mask_pan(digits: str) -> str:
    # PCI DSS 3.4.1: at most BIN (first six) and last four displayed.
    return digits[:6] + "*" * (len(digits) - 10) + digits[-4:]


def mask_email(value: str) -> str:
    local, _, domain = value.partition("@")
    return (local[:1] + "***@" + domain) if local else "***@" + domain


def mask_tail(value: str, keep: int = 4) -> str:
    clean = re.sub(r"[\s-]", "", value)
    if len(clean) <= keep:
        return "*" * len(clean)
    return "*" * (len(clean) - keep) + clean[-keep:]


def mask_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    return "+" + digits[:1] + "*" * max(len(digits) - 4, 0) + digits[-3:]


def mask_iban(value: str) -> str:
    s = re.sub(r"\s+", "", value).upper()
    return s[:2] + "*" * (len(s) - 6) + s[-4:]


def mask_ssn(_area: str, _group: str, serial: str) -> str:
    return "***-**-" + serial


def mask_dob(value: str) -> str:
    return re.sub(r"\d", "*", value)


# --------------------------------------------------------------------------
# Detectors
# --------------------------------------------------------------------------


@dataclass
class Finding:
    type: str
    start: int
    end: int
    masked: str
    confidence: str  # high | medium | low
    detail: dict = field(default_factory=dict)


PAN_RE = re.compile(
    r"(?<![\d])"
    r"(?:\d{13,19}"  # contiguous
    r"|\d{4}([ -])\d{4}\1\d{4}\1\d{1,7}"  # 4-4-4-x (13 to 19)
    r"|\d{4}([ -])\d{6}\2\d{4,5})"  # 4-6-5 Amex, 4-6-4 Diners
    r"(?![\d])"
)
EMAIL_RE = re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,24}\b")
PHONE_RE = re.compile(r"(?<![\w+])\+[1-9](?:[ .-]?\(?\d\)?){7,14}(?![\d])")
IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]){11,30}\b")
SSN_RE = re.compile(r"(?<![\d-])(\d{3})-(\d{2})-(\d{4})(?![\d-])")
PASSPORT_KW_RE = re.compile(r"passport|travel[ _-]?document|pasaporte|reisepass", re.I)
PASSPORT_TOKEN_RE = re.compile(r"\b(?=[A-Z0-9]*\d)[A-Z0-9]{6,9}\b")
DOB_KW_RE = re.compile(r"\b(?:dob|d\.o\.b\.|date[ _-]?of[ _-]?birth|birth[ _-]?date|birthdate|born)\b", re.I)
DATE_RE = re.compile(
    r"\b(?:(?:19|20)\d{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])"
    r"|(?:0[1-9]|[12]\d|3[01])[/.](?:0[1-9]|1[0-2])[/.](?:19|20)\d{2}"
    r"|(?:0[1-9]|1[0-2])/(?:0[1-9]|[12]\d|3[01])/(?:19|20)\d{2})\b"
)
KEYWORD_WINDOW = 40  # characters after a keyword in which a value is accepted


def detect_iban(text: str) -> Iterable[Finding]:
    for m in IBAN_RE.finditer(text):
        raw = m.group(0)
        # The pattern is greedy and may run into a following word; drop
        # trailing space-separated groups until the check digits validate.
        groups = raw.split(" ")
        while groups:
            candidate = " ".join(groups)
            if iban_valid(candidate):
                yield Finding("iban", m.start(), m.start() + len(candidate), mask_iban(candidate), "high")
                break
            groups.pop()


def detect_pan(text: str) -> Iterable[Finding]:
    for m in PAN_RE.finditer(text):
        digits = re.sub(r"[ -]", "", m.group(0))
        if not 13 <= len(digits) <= 19:
            continue
        brand = card_brand(digits)
        if brand and luhn_valid(digits):
            yield Finding("pan", m.start(), m.end(), mask_pan(digits), "high", {"brand": brand})


def detect_ssn(text: str) -> Iterable[Finding]:
    for m in SSN_RE.finditer(text):
        area, group, serial = m.groups()
        if ssn_valid(area, group, serial):
            yield Finding("ssn", m.start(), m.end(), mask_ssn(area, group, serial), "high")


def detect_email(text: str) -> Iterable[Finding]:
    for m in EMAIL_RE.finditer(text):
        yield Finding("email", m.start(), m.end(), mask_email(m.group(0)), "high")


def detect_phone(text: str) -> Iterable[Finding]:
    for m in PHONE_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 8 <= len(digits) <= 15:
            yield Finding("phone", m.start(), m.end(), mask_phone(m.group(0)), "medium")


def _keyword_proximity(text: str, kw_re: re.Pattern, val_re: re.Pattern) -> Iterable[re.Match]:
    for kw in kw_re.finditer(text):
        window_end = min(len(text), kw.end() + KEYWORD_WINDOW)
        m = val_re.search(text, kw.end(), window_end)
        if m:
            yield m


def detect_passport(text: str) -> Iterable[Finding]:
    for m in _keyword_proximity(text, PASSPORT_KW_RE, PASSPORT_TOKEN_RE):
        yield Finding("passport", m.start(), m.end(), mask_tail(m.group(0), 2), "low")


def detect_dob(text: str) -> Iterable[Finding]:
    for m in _keyword_proximity(text, DOB_KW_RE, DATE_RE):
        yield Finding("dob", m.start(), m.end(), mask_dob(m.group(0)), "medium")


def make_loyalty_detector(pattern: str) -> Callable[[str], Iterable[Finding]]:
    rx = re.compile(pattern)

    def detect_loyalty(text: str) -> Iterable[Finding]:
        for m in rx.finditer(text):
            yield Finding("loyalty", m.start(), m.end(), mask_tail(m.group(0), 4), "medium")

    return detect_loyalty


def build_detectors(loyalty_regex: str = DEFAULT_LOYALTY_REGEX) -> list[Callable[[str], Iterable[Finding]]]:
    # Order matters: a span claimed by an earlier detector is not re-reported
    # by a later one (for example, IBAN digits are never re-read as a PAN).
    return [
        detect_iban,
        detect_pan,
        detect_ssn,
        detect_email,
        detect_phone,
        make_loyalty_detector(loyalty_regex),
        detect_passport,
        detect_dob,
    ]


def scan_text(text: str, detectors) -> list[Finding]:
    claimed: list[tuple[int, int]] = []
    results: list[Finding] = []
    for det in detectors:
        for f in det(text):
            if any(f.start < e and s < f.end for s, e in claimed):
                continue
            claimed.append((f.start, f.end))
            results.append(f)
    return results


# --------------------------------------------------------------------------
# File handling: CSV and JSON are flattened to "key: value" lines so that
# header and key names act as context for the keyword heuristics.
# --------------------------------------------------------------------------


def _flatten_json(obj, prefix: str = "") -> Iterable[str]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _flatten_json(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _flatten_json(v, f"{prefix}[{i}]")
    else:
        yield f"{prefix}: {obj}"


def file_to_text(path: str, raw: str) -> str:
    lower = path.lower()
    try:
        if lower.endswith(".json"):
            return "\n".join(_flatten_json(json.loads(raw)))
        if lower.endswith((".csv", ".tsv")):
            dialect = "excel-tab" if lower.endswith(".tsv") else "excel"
            rows = list(csv.reader(io.StringIO(raw), dialect=dialect))
            if len(rows) >= 2:
                header = rows[0]
                lines = []
                for row in rows[1:]:
                    lines.append(" | ".join(f"{h}: {v}" for h, v in zip(header, row)))
                return "\n".join(lines)
    except (ValueError, csv.Error):
        pass  # fall back to raw text
    return raw


# --------------------------------------------------------------------------
# Recommendation
# --------------------------------------------------------------------------


def recommend(findings_by_type: dict, jurisdictions: list[str]) -> dict:
    if not findings_by_type:
        return {
            "tier": "C1",
            "label": "Internal",
            "protection_profile": TIER_TO_PROFILE["C1"],
            "rationale": "No sensitive data types detected. Default to Internal until the data owner confirms; "
            "Public (C0) requires an explicit owner decision.",
            "needs_review": False,
            "tags": {
                "data-classification": "internal",
                "protection-profile": "pp1",
                "regulatory-scope": "none",
            },
        }

    tiers, labels, domains = [], [], []
    personal = pci = False
    for ftype in findings_by_type:
        tier, label, domain, is_personal, is_pci = FINDING_POLICY[ftype]
        tiers.append(tier)
        labels.append(label)
        domains.append(domain)
        personal |= is_personal
        pci |= is_pci

    tier = max(tiers, key=TIER_ORDER.index)
    label = min(labels, key=LABEL_PRIORITY.index)
    domain = min(domains, key=DOMAIN_PRIORITY.index)

    scope_parts = []
    if pci:
        scope_parts.append("pci")
    if personal:
        scope_parts.extend(r for r in PRIVACY_REGIMES if r in jurisdictions)
    scope = "_".join(scope_parts) or "none"

    drivers = sorted(t for t in findings_by_type if FINDING_POLICY[t][0] == tier)
    only_low = all(findings_by_type[t]["confidence"] == "low" for t in drivers)
    rationale = f"Tier {tier} is driven by: {', '.join(drivers)}. Tier {tier} maps to {TIER_TO_PROFILE[tier]}."
    if only_low:
        rationale += (
            " Every finding at this tier is low confidence; route to the data owner for review before"
            " applying the label."
        )

    return {
        "tier": tier,
        "label": label,
        "protection_profile": TIER_TO_PROFILE[tier],
        "rationale": rationale,
        "needs_review": only_low,
        "tags": {
            "data-classification": TIER_TO_CLASSIFICATION[tier],
            "protection-profile": TIER_TO_PROFILE[tier],
            "data-domain": domain,
            "regulatory-scope": scope,
        },
    }


def scan_file(path: str, detectors, jurisdictions: list[str], max_bytes: int) -> dict:
    with open(path, "rb") as fh:
        data = fh.read(max_bytes + 1)
    truncated = len(data) > max_bytes
    raw = data[:max_bytes].decode("utf-8", errors="replace")
    text = file_to_text(path, raw)
    findings = scan_text(text, detectors)

    by_type: dict[str, dict] = {}
    rank = {"low": 0, "medium": 1, "high": 2}
    for f in findings:
        entry = by_type.setdefault(f.type, {"count": 0, "confidence": f.confidence, "samples": []})
        entry["count"] += 1
        if rank[f.confidence] > rank[entry["confidence"]]:
            entry["confidence"] = f.confidence
        if len(entry["samples"]) < MAX_SAMPLES and f.masked not in entry["samples"]:
            entry["samples"].append(f.masked)
        if f.type == "pan":
            brands = entry.setdefault("brands", {})
            brands[f.detail["brand"]] = brands.get(f.detail["brand"], 0) + 1

    return {
        "path": path,
        "bytes_scanned": min(len(data), max_bytes),
        "truncated": truncated,
        "findings": dict(sorted(by_type.items())),
        "recommendation": recommend(by_type, jurisdictions),
    }


def iter_files(root: str, extensions: tuple[str, ...]) -> Iterable[str]:
    if os.path.isfile(root):
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            if name.lower().endswith(extensions):
                yield os.path.join(dirpath, name)


def scan_path(
    root: str,
    loyalty_regex: str = DEFAULT_LOYALTY_REGEX,
    jurisdictions: list[str] | None = None,
    extensions: tuple[str, ...] = DEFAULT_EXTENSIONS,
    max_bytes: int = 10 * 1024 * 1024,
) -> dict:
    jurisdictions = jurisdictions if jurisdictions is not None else ["gdpr"]
    detectors = build_detectors(loyalty_regex)
    files = [scan_file(p, detectors, jurisdictions, max_bytes) for p in iter_files(root, extensions)]
    tier_counts: dict[str, int] = {}
    for f in files:
        t = f["recommendation"]["tier"]
        tier_counts[t] = tier_counts.get(t, 0) + 1
    return {
        "scanner": "pii_scanner",
        "version": SCANNER_VERSION,
        "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "root": root,
        "jurisdictions": jurisdictions,
        "summary": {"files_scanned": len(files), "files_by_tier": dict(sorted(tier_counts.items()))},
        "files": files,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Scan files for PII and payment card data and recommend a label.")
    ap.add_argument("path", help="file or directory to scan")
    ap.add_argument("--output", "-o", help="write JSON report to this file instead of stdout")
    ap.add_argument("--pretty", action="store_true", help="indent JSON output")
    ap.add_argument(
        "--loyalty-regex",
        default=DEFAULT_LOYALTY_REGEX,
        help=f"regular expression for loyalty member numbers (default: {DEFAULT_LOYALTY_REGEX})",
    )
    ap.add_argument(
        "--jurisdictions",
        default="gdpr",
        help="comma-separated privacy regimes in scope for personal data: gdpr,ccpa,pipl,lgpd (default: gdpr)",
    )
    ap.add_argument("--extensions", default=",".join(DEFAULT_EXTENSIONS), help="comma-separated file extensions")
    ap.add_argument("--max-bytes", type=int, default=10 * 1024 * 1024, help="bytes read per file (default 10 MiB)")
    ap.add_argument(
        "--fail-on",
        choices=["C2", "C3"],
        help="exit with status 2 if any file is recommended at or above this tier (for CI gates)",
    )
    args = ap.parse_args(argv)

    jurisdictions = [j.strip() for j in args.jurisdictions.split(",") if j.strip()]
    bad = [j for j in jurisdictions if j not in PRIVACY_REGIMES]
    if bad:
        ap.error(f"unknown jurisdiction(s): {', '.join(bad)}; allowed: {', '.join(PRIVACY_REGIMES)}")
    try:
        re.compile(args.loyalty_regex)
    except re.error as exc:
        ap.error(f"invalid --loyalty-regex: {exc}")
    if not os.path.exists(args.path):
        ap.error(f"path not found: {args.path}")

    exts = tuple(e if e.startswith(".") else "." + e for e in args.extensions.split(",") if e)
    report = scan_path(args.path, args.loyalty_regex, jurisdictions, exts, args.max_bytes)
    out = json.dumps(report, indent=2 if args.pretty else None)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out + "\n")
    else:
        print(out)

    if args.fail_on:
        threshold = TIER_ORDER.index(args.fail_on)
        if any(TIER_ORDER.index(f["recommendation"]["tier"]) >= threshold for f in report["files"]):
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
