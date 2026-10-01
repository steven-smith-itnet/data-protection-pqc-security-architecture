#!/usr/bin/env python3
"""Cryptographic inventory scanner that emits a CycloneDX 1.6 CBOM.

Phase 1 (Know the data) builds the cryptographic inventory; Phase 6 (PQC)
uses it to find quantum-vulnerable algorithms and to prove progress. PCI DSS
v4.0.1 requirement 12.3.3 (documented, annually reviewed cipher suites and
protocols) and 4.2.1.1 (inventory of trusted keys and certificates) are
direct consumers.

Sources:
  * TLS endpoints, probed with the local `openssl s_client` (OpenSSL 3.5 or
    later is needed to negotiate and report ML-KEM hybrid groups). Captured:
    protocol version, cipher suite, negotiated key exchange group (for
    example X25519MLKEM768), handshake signature scheme, and the server
    certificate's signature algorithm and public key type and size.
  * Local PEM certificate files, parsed with `openssl x509 -text` (which,
    unlike most Python libraries today, understands ML-DSA and SLH-DSA keys).

Output: CycloneDX 1.6 JSON with "cryptographic-asset" components carrying
cryptoProperties (assetType algorithm, protocol, certificate, and
related-crypto-material). Quantum-vulnerable assets are flagged with
nistQuantumSecurityLevel 0 and a "cbom:quantum-vulnerable" property, and a
findings list with remediation priority is attached as properties.

Priority logic (harvest now, decrypt later):
  * Classical key exchange (ECDHE, X25519, RSA key transport): HIGH. Recorded
    traffic can be decrypted later by a quantum computer.
  * Classical signatures and certificate keys (RSA, ECDSA, EdDSA): MEDIUM.
    Forgery needs a quantum computer at the time of attack; raise to HIGH for
    long-lived roots of trust (CA roots, firmware and code signing).

Usage:
    python cbom_scan.py --endpoint example.org:443 --cert-file ca.pem -o cbom.json
    python cbom_scan.py --endpoint 127.0.0.1:4433 --servername localhost --probe-pq
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone

TOOL_NAME = "cbom_scan"
TOOL_VERSION = "1.0.0"

# --------------------------------------------------------------------------
# Algorithm knowledge base
# --------------------------------------------------------------------------

# Key exchange groups. qsl = NIST PQC security category (0 = quantum-vulnerable).
GROUPS = {
    "X25519MLKEM768": {"primitive": "kem", "qsl": 3, "classical": 128, "hybrid": "X25519 + ML-KEM-768", "codepoint": "0x11EC"},
    "SecP256r1MLKEM768": {"primitive": "kem", "qsl": 3, "classical": 128, "hybrid": "P-256 + ML-KEM-768"},
    "SecP384r1MLKEM1024": {"primitive": "kem", "qsl": 5, "classical": 192, "hybrid": "P-384 + ML-KEM-1024"},
    "X448MLKEM1024": {"primitive": "kem", "qsl": 5, "classical": 224, "hybrid": "X448 + ML-KEM-1024"},
    "MLKEM512": {"primitive": "kem", "qsl": 1, "classical": None},
    "MLKEM768": {"primitive": "kem", "qsl": 3, "classical": None},
    "MLKEM1024": {"primitive": "kem", "qsl": 5, "classical": None},
    "X25519": {"primitive": "key-agree", "qsl": 0, "classical": 128, "curve": "Curve25519", "codepoint": "0x001D"},
    "X448": {"primitive": "key-agree", "qsl": 0, "classical": 224, "curve": "Curve448"},
    "secp256r1": {"primitive": "key-agree", "qsl": 0, "classical": 128, "curve": "P-256", "codepoint": "0x0017"},
    "prime256v1": {"primitive": "key-agree", "qsl": 0, "classical": 128, "curve": "P-256", "codepoint": "0x0017"},
    "secp384r1": {"primitive": "key-agree", "qsl": 0, "classical": 192, "curve": "P-384", "codepoint": "0x0018"},
    "secp521r1": {"primitive": "key-agree", "qsl": 0, "classical": 256, "curve": "P-521"},
    "ffdhe2048": {"primitive": "key-agree", "qsl": 0, "classical": 112},
    "ffdhe3072": {"primitive": "key-agree", "qsl": 0, "classical": 128},
    "ffdhe4096": {"primitive": "key-agree", "qsl": 0, "classical": 152},
}

# TLS 1.3 cipher suites (RFC 8446 codepoints).
TLS13_SUITES = {
    "TLS_AES_128_GCM_SHA256": {"id": "0x13,0x01", "aead": "AES-128-GCM", "hash": "SHA-256"},
    "TLS_AES_256_GCM_SHA384": {"id": "0x13,0x02", "aead": "AES-256-GCM", "hash": "SHA-384"},
    "TLS_CHACHA20_POLY1305_SHA256": {"id": "0x13,0x03", "aead": "ChaCha20-Poly1305", "hash": "SHA-256"},
}

SYMMETRIC = {
    "AES-128-GCM": {"primitive": "ae", "mode": "gcm", "classical": 128, "qsl": 1, "note": "below CNSA 2.0 (AES-256)"},
    "AES-256-GCM": {"primitive": "ae", "mode": "gcm", "classical": 256, "qsl": 5},
    "AES-128-CBC": {"primitive": "block-cipher", "mode": "cbc", "classical": 128, "qsl": 1, "note": "CBC suites are TLS 1.2 only; prefer AEAD"},
    "AES-256-CBC": {"primitive": "block-cipher", "mode": "cbc", "classical": 256, "qsl": 5, "note": "CBC suites are TLS 1.2 only; prefer AEAD"},
    "ChaCha20-Poly1305": {"primitive": "ae", "classical": 256, "qsl": None},
    "SHA-256": {"primitive": "hash", "classical": 128, "qsl": 2},
    "SHA-384": {"primitive": "hash", "classical": 192, "qsl": 4},
    "SHA-1": {"primitive": "hash", "classical": None, "qsl": None, "note": "SHA-1 is deprecated"},
}

SIG_OIDS = {
    "ecdsa-with-SHA256": "1.2.840.10045.4.3.2",
    "ecdsa-with-SHA384": "1.2.840.10045.4.3.3",
    "sha256WithRSAEncryption": "1.2.840.113549.1.1.11",
    "sha384WithRSAEncryption": "1.2.840.113549.1.1.12",
    "rsassaPss": "1.2.840.113549.1.1.10",
    "ED25519": "1.3.101.112",
    "ML-DSA-44": "2.16.840.1.101.3.4.3.17",
    "ML-DSA-65": "2.16.840.1.101.3.4.3.18",
    "ML-DSA-87": "2.16.840.1.101.3.4.3.19",
}
KEY_OIDS = {
    "id-ecPublicKey": "1.2.840.10045.2.1",
    "rsaEncryption": "1.2.840.113549.1.1.1",
    "ED25519": "1.3.101.112",
    "ML-DSA-44": "2.16.840.1.101.3.4.3.17",
    "ML-DSA-65": "2.16.840.1.101.3.4.3.18",
    "ML-DSA-87": "2.16.840.1.101.3.4.3.19",
}
MLDSA_QSL = {"44": 2, "65": 3, "87": 5}


def is_pq_name(name: str) -> bool:
    n = name.upper().replace("-", "").replace("_", "")
    return any(x in n for x in ("MLKEM", "MLDSA", "SLHDSA", "LMS", "XMSS"))


def signature_assessment(name: str) -> dict:
    """Return primitive, qsl, and vulnerability for a signature algorithm or scheme name."""
    up = name.upper().replace("_", "-")
    m = re.search(r"ML-?DSA-?(44|65|87)", up)
    if m:
        return {"primitive": "signature", "qsl": MLDSA_QSL[m.group(1)], "vulnerable": False, "family": f"ML-DSA-{m.group(1)}"}
    if "SLH-DSA" in up or "SLHDSA" in up:
        return {"primitive": "signature", "qsl": None, "vulnerable": False, "family": "SLH-DSA"}
    if "ECDSA" in up:
        return {"primitive": "signature", "qsl": 0, "vulnerable": True, "family": "ECDSA"}
    if "RSA" in up:
        return {"primitive": "signature", "qsl": 0, "vulnerable": True, "family": "RSA"}
    if "ED25519" in up or "ED448" in up:
        return {"primitive": "signature", "qsl": 0, "vulnerable": True, "family": "EdDSA"}
    return {"primitive": "signature", "qsl": None, "vulnerable": None, "family": "unknown"}


# --------------------------------------------------------------------------
# OpenSSL helpers
# --------------------------------------------------------------------------


def openssl_version(openssl: str) -> str:
    return subprocess.run([openssl, "version"], capture_output=True, text=True, check=True).stdout.strip()


PEM_RE = re.compile(r"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----", re.S)


def parse_certificate(pem: str, openssl: str = "openssl") -> dict:
    fields = subprocess.run(
        [openssl, "x509", "-noout", "-subject", "-issuer", "-startdate", "-enddate", "-serial",
         "-fingerprint", "-sha256", "-nameopt", "RFC2253"],
        input=pem, capture_output=True, text=True, check=True,
    ).stdout
    text = subprocess.run(
        [openssl, "x509", "-noout", "-text"], input=pem, capture_output=True, text=True, check=True
    ).stdout

    def grab(pattern: str, src: str) -> str | None:
        m = re.search(pattern, src, re.M)
        return m.group(1).strip() if m else None

    def to_iso(s: str | None) -> str | None:
        if not s:
            return None
        return datetime.strptime(s, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc).isoformat()

    not_before = to_iso(grab(r"^notBefore=(.+)$", fields))
    not_after = to_iso(grab(r"^notAfter=(.+)$", fields))
    key_alg = grab(r"Public Key Algorithm:\s*(\S+)", text)
    key_bits = grab(r"Public-Key:\s*\((\d+) bit\)", text)
    curve = grab(r"NIST CURVE:\s*(\S+)", text) or grab(r"ASN1 OID:\s*(\S+)", text)
    if key_alg and key_alg.startswith("ML-DSA"):
        key_bits = None  # OpenSSL prints no bit size for ML-DSA keys
    validity_days = None
    if not_before and not_after:
        validity_days = (datetime.fromisoformat(not_after) - datetime.fromisoformat(not_before)).days
    return {
        "subject": grab(r"^subject=(.+)$", fields),
        "issuer": grab(r"^issuer=(.+)$", fields),
        "serial": grab(r"^serial=(.+)$", fields),
        "sha256_fingerprint": grab(r"^(?:SHA256|sha256) Fingerprint=(.+)$", fields),
        "not_before": not_before,
        "not_after": not_after,
        "validity_days": validity_days,
        "signature_algorithm": grab(r"Signature Algorithm:\s*(\S+)", text),
        "public_key_algorithm": key_alg,
        "public_key_bits": int(key_bits) if key_bits else None,
        "curve": curve,
        "self_signed": grab(r"^subject=(.+)$", fields) == grab(r"^issuer=(.+)$", fields),
    }


def probe_endpoint(host: str, port: int, servername: str | None, openssl: str, groups: str | None,
                   timeout: float) -> dict:
    cmd = [openssl, "s_client", "-connect", f"{host}:{port}", "-showcerts"]
    if servername:
        cmd += ["-servername", servername]
    if groups:
        cmd += ["-groups", groups]
    try:
        proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "command": " ".join(cmd)}
    out = proc.stdout + "\n" + proc.stderr

    def grab(pattern: str) -> str | None:
        m = re.search(pattern, out, re.M)
        return m.group(1).strip() if m else None

    protocol = grab(r"^\s*Protocol\s*:\s*(\S+)") or grab(r"^New, (TLSv[\d.]+), Cipher is")
    cipher = grab(r"Cipher is (\S+)") or grab(r"^\s*Cipher\s*:\s*(\S+)")
    group = grab(r"Negotiated TLS1\.3 group:\s*(\S+)")
    if not group:
        # OpenSSL 3.5 prints "Peer Temp Key", older releases "Server Temp Key",
        # e.g. "X25519, 253 bits" or "ECDH, prime256v1, 256 bits".
        temp = grab(r"(?:Peer|Server) Temp Key:\s*(.+)$")
        if temp:
            parts = [p.strip() for p in temp.split(",")]
            group = parts[1] if parts[0] in ("ECDH", "DH") and len(parts) > 2 else parts[0]
    result = {
        "ok": bool(protocol and cipher and cipher != "(NONE)"),
        "command": " ".join(cmd),
        "protocol": protocol,
        "cipher": cipher,
        "group": group,
        "peer_signature_type": grab(r"Peer signature type:\s*(\S+)"),
        "peer_signing_digest": grab(r"Peer signing digest:\s*(\S+)"),
        "server_public_key_bits": grab(r"Server public key is (\d+) bit"),
        "certificates": [parse_certificate(p, openssl) for p in PEM_RE.findall(proc.stdout)],
    }
    if not result["ok"]:
        err = [line for line in out.splitlines() if "error" in line.lower() or "alert" in line.lower()]
        result["error"] = err[0] if err else "handshake failed"
    return result


# --------------------------------------------------------------------------
# CBOM builder
# --------------------------------------------------------------------------


class CbomBuilder:
    def __init__(self):
        self.components: dict[str, dict] = {}
        self.dependencies: dict[str, set[str]] = {}
        self.findings: list[dict] = []

    def _add(self, ref: str, component: dict) -> str:
        if ref not in self.components:
            component["bom-ref"] = ref
            self.components[ref] = component
        return ref

    def _depends(self, ref: str, *on: str) -> None:
        self.dependencies.setdefault(ref, set()).update(o for o in on if o)

    def _props(self, **kv) -> list[dict]:
        return [{"name": f"cbom:{k.replace('_', '-')}", "value": str(v).lower() if isinstance(v, bool) else str(v)}
                for k, v in kv.items() if v is not None]

    def _finding(self, source: str, asset: str, severity: str, issue: str, action: str) -> None:
        self.findings.append({"source": source, "asset": asset, "priority": severity, "issue": issue, "action": action})

    # ---- algorithm components -----------------------------------------

    def add_group(self, name: str, source: str) -> str:
        info = GROUPS.get(name)
        if info is None:
            pq = is_pq_name(name)
            info = {"primitive": "kem" if pq else "key-agree", "qsl": None if pq else 0, "classical": None}
        vulnerable = info["qsl"] == 0
        algp = {
            "primitive": info["primitive"],
            "executionEnvironment": "software-plain-ram",
            "cryptoFunctions": ["keygen", "encapsulate", "decapsulate"] if info["primitive"] == "kem" else ["keygen", "keyderive"],
        }
        if info.get("curve"):
            algp["curve"] = info["curve"]
        if info.get("classical"):
            algp["classicalSecurityLevel"] = info["classical"]
        if info["qsl"] is not None:
            algp["nistQuantumSecurityLevel"] = info["qsl"]
        ref = self._add(f"crypto/algorithm/{name}", {
            "type": "cryptographic-asset",
            "name": name,
            "cryptoProperties": {"assetType": "algorithm", "algorithmProperties": algp},
            "properties": self._props(quantum_vulnerable=vulnerable, hybrid=info.get("hybrid"),
                                      tls_codepoint=info.get("codepoint"), role="key-exchange"),
        })
        if vulnerable:
            self._finding(source, name, "high",
                          "Classical key exchange: recorded sessions are exposed to harvest now, decrypt later.",
                          "Enable hybrid X25519MLKEM768 on this endpoint (OpenSSL 3.5+, or the provider's PQ TLS policy).")
        return ref

    def add_symmetric(self, name: str) -> str:
        info = SYMMETRIC.get(name, {"primitive": "unknown", "classical": None, "qsl": None})
        algp = {"primitive": info["primitive"], "executionEnvironment": "software-plain-ram"}
        if info.get("mode"):
            algp["mode"] = info["mode"]
        algp["cryptoFunctions"] = ["digest"] if info["primitive"] == "hash" else ["encrypt", "decrypt"]
        if info.get("classical"):
            algp["classicalSecurityLevel"] = info["classical"]
        if info.get("qsl") is not None:
            algp["nistQuantumSecurityLevel"] = info["qsl"]
        return self._add(f"crypto/algorithm/{name}", {
            "type": "cryptographic-asset",
            "name": name,
            "cryptoProperties": {"assetType": "algorithm", "algorithmProperties": algp},
            "properties": self._props(quantum_vulnerable=False, note=info.get("note")),
        })

    def add_signature(self, name: str, source: str, role: str, long_lived: bool = False) -> str:
        a = signature_assessment(name)
        algp = {"primitive": "signature", "executionEnvironment": "software-plain-ram", "cryptoFunctions": ["sign", "verify"]}
        if a["qsl"] is not None:
            algp["nistQuantumSecurityLevel"] = a["qsl"]
        props = {"cryptoProperties": {"assetType": "algorithm", "algorithmProperties": algp}}
        oid = SIG_OIDS.get(name)
        if oid:
            props["cryptoProperties"]["oid"] = oid
        ref = self._add(f"crypto/algorithm/{name}", {
            "type": "cryptographic-asset",
            "name": name,
            **props,
            "properties": self._props(quantum_vulnerable=a["vulnerable"], family=a["family"], role=role),
        })
        if a["vulnerable"]:
            self._finding(source, name, "high" if long_lived else "medium",
                          f"Quantum-vulnerable signature ({a['family']}) used for {role}.",
                          "Plan migration to ML-DSA (FIPS 204) once clients and the CA support it; "
                          "prioritize long-lived roots and code signing.")
        return ref

    # ---- certificates ---------------------------------------------------

    def add_certificate(self, cert: dict, source: str) -> str:
        sig_ref = self.add_signature(cert["signature_algorithm"] or "unknown", source, "certificate signature",
                                     long_lived=bool(cert["self_signed"] and (cert["validity_days"] or 0) > 825))
        key_name = cert["public_key_algorithm"] or "unknown"
        key_label = key_name
        if key_name == "id-ecPublicKey" and cert["curve"]:
            key_label = f"EC-{cert['curve']}"
        elif key_name == "rsaEncryption" and cert["public_key_bits"]:
            key_label = f"RSA-{cert['public_key_bits']}"
        key_assess = signature_assessment(
            "ECDSA" if key_name == "id-ecPublicKey" else "RSA" if key_name == "rsaEncryption" else key_name)
        key_alg_ref = self._add(f"crypto/algorithm/{key_label}", {
            "type": "cryptographic-asset",
            "name": key_label,
            "cryptoProperties": {
                "assetType": "algorithm",
                "algorithmProperties": {
                    "primitive": "signature",
                    **({"curve": cert["curve"]} if cert["curve"] else {}),
                    **({"nistQuantumSecurityLevel": key_assess["qsl"]} if key_assess["qsl"] is not None else {}),
                    "cryptoFunctions": ["keygen", "sign", "verify"],
                },
                **({"oid": KEY_OIDS[key_name]} if key_name in KEY_OIDS else {}),
            },
            "properties": self._props(quantum_vulnerable=key_assess["vulnerable"], role="certificate public key"),
        })
        fp = (cert["sha256_fingerprint"] or uuid.uuid4().hex).replace(":", "").lower()
        pk_ref = self._add(f"crypto/key/{fp[:16]}", {
            "type": "cryptographic-asset",
            "name": f"public key of {cert['subject']}",
            "cryptoProperties": {
                "assetType": "related-crypto-material",
                "relatedCryptoMaterialProperties": {
                    "type": "public-key",
                    "algorithmRef": key_alg_ref,
                    **({"size": cert["public_key_bits"]} if cert["public_key_bits"] else {}),
                    "format": "PEM",
                },
            },
        })
        cert_ref = self._add(f"crypto/certificate/{fp[:16]}", {
            "type": "cryptographic-asset",
            "name": cert["subject"],
            "cryptoProperties": {
                "assetType": "certificate",
                "certificateProperties": {
                    "subjectName": cert["subject"],
                    "issuerName": cert["issuer"],
                    "notValidBefore": cert["not_before"],
                    "notValidAfter": cert["not_after"],
                    "signatureAlgorithmRef": sig_ref,
                    "subjectPublicKeyRef": pk_ref,
                    "certificateFormat": "X.509",
                    "certificateExtension": "pem",
                },
            },
            "properties": self._props(source=source, sha256_fingerprint=cert["sha256_fingerprint"],
                                      validity_days=cert["validity_days"], self_signed=cert["self_signed"]),
        })
        self._depends(cert_ref, sig_ref, pk_ref)
        self._depends(pk_ref, key_alg_ref)
        if cert["validity_days"] and cert["validity_days"] > 200 and not cert["self_signed"]:
            self._finding(source, cert["subject"], "low",
                          f"Certificate validity is {cert['validity_days']} days.",
                          "Public TLS certificates are limited to 200 days from March 15, 2026 (CA/B Forum SC-081); automate renewal.")
        return cert_ref

    # ---- endpoints -------------------------------------------------------

    def add_endpoint(self, target: str, probe: dict, pq_probe: dict | None) -> str | None:
        if not probe["ok"]:
            self._finding(target, target, "info", f"Handshake failed: {probe.get('error')}", "Check reachability.")
            return None
        version = (probe["protocol"] or "").replace("TLSv", "")
        refs = []
        suite_algs = []
        cipher = probe["cipher"]
        if cipher in TLS13_SUITES:
            s = TLS13_SUITES[cipher]
            suite_algs = [self.add_symmetric(s["aead"]), self.add_symmetric(s["hash"])]
            suite = {"name": cipher, "algorithms": suite_algs, "identifiers": [s["id"]]}
        else:
            for token, alg in (("AES256-GCM", "AES-256-GCM"), ("AES128-GCM", "AES-128-GCM"),
                               ("CHACHA20", "ChaCha20-Poly1305"), ("AES256-SHA", "AES-256-CBC"),
                               ("AES128-SHA", "AES-128-CBC")):
                if token in cipher:
                    suite_algs.append(self.add_symmetric(alg))
                    break
            for token, alg in (("SHA384", "SHA-384"), ("SHA256", "SHA-256")):
                if cipher.endswith(token):
                    suite_algs.append(self.add_symmetric(alg))
                    break
            suite = {"name": cipher, "algorithms": suite_algs}
            if not cipher.startswith(("ECDHE", "DHE")) and version != "1.3":
                self._finding(target, cipher, "high", "Static RSA key transport: no forward secrecy and quantum-vulnerable.",
                              "Disable non-ECDHE suites; move to TLS 1.3.")
        if version not in ("1.3",):
            self._finding(target, f"TLS {version}", "medium", "TLS 1.3 not negotiated.",
                          "Prefer TLS 1.3; hybrid ML-KEM groups are defined for TLS 1.3 only.")
        if probe["group"]:
            refs.append(self.add_group(probe["group"], target))
        if probe["peer_signature_type"]:
            refs.append(self.add_signature(probe["peer_signature_type"], target, "TLS handshake signature"))
        cert_refs = [self.add_certificate(c, target) for c in probe["certificates"]]
        # The PQ probe counts only if the handshake succeeded AND negotiated a
        # PQ group; a TLS 1.2 server can complete a handshake while ignoring
        # the offered group.
        pq_supported = None
        if pq_probe is not None:
            pq_supported = bool(pq_probe["ok"] and is_pq_name(pq_probe.get("group") or ""))
        proto_ref = self._add(f"crypto/protocol/tls/{target}", {
            "type": "cryptographic-asset",
            "name": f"TLS {version} at {target}",
            "cryptoProperties": {
                "assetType": "protocol",
                "protocolProperties": {
                    "type": "tls",
                    "version": version,
                    "cipherSuites": [suite],
                    "cryptoRefArray": refs + suite_algs + cert_refs,
                },
            },
            "properties": self._props(
                endpoint=target,
                negotiated_group=probe["group"],
                hybrid_pq_negotiated=is_pq_name(probe["group"] or ""),
                hybrid_pq_supported=pq_supported,
                probe_command=probe["command"],
            ),
        })
        self._depends(proto_ref, *(refs + suite_algs + cert_refs))
        if pq_supported is False:
            # The main finding for the classical group already exists; note that
            # the endpoint did not negotiate a PQ-only offer.
            detail = "refused the handshake" if not pq_probe["ok"] else f"negotiated {pq_probe.get('group') or 'no group'} instead"
            self._finding(target, "X25519MLKEM768", "high", f"Offered only X25519MLKEM768; endpoint {detail}.",
                          "Upgrade the TLS terminator (OpenSSL 3.5+, s2n-tls, BoringSSL) or enable the provider's PQ policy.")
        return proto_ref

    # ---- output ----------------------------------------------------------

    def bom(self, openssl_ver: str) -> dict:
        vulnerable = sorted({c["name"] for c in self.components.values()
                             if any(p["name"] == "cbom:quantum-vulnerable" and p["value"] == "true"
                                    for p in c.get("properties", []))})
        return {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "serialNumber": f"urn:uuid:{uuid.uuid4()}",
            "version": 1,
            "metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "tools": {"components": [{"type": "application", "name": TOOL_NAME, "version": TOOL_VERSION,
                                          "description": f"TLS and certificate CBOM scanner using {openssl_ver}"}]},
                "properties": [
                    {"name": "cbom:quantum-vulnerable-assets", "value": ", ".join(vulnerable) or "none"},
                    {"name": "cbom:finding-count", "value": str(len(self.findings))},
                ] + [
                    {"name": f"cbom:finding:{i + 1}",
                     "value": f"[{f['priority']}] {f['source']} {f['asset']}: {f['issue']} Action: {f['action']}"}
                    for i, f in enumerate(self.findings)
                ],
            },
            "components": list(self.components.values()),
            "dependencies": [{"ref": r, "dependsOn": sorted(d)} for r, d in self.dependencies.items()],
        }


def parse_target(t: str) -> tuple[str, int]:
    if t.startswith("["):  # [ipv6]:port
        host, _, port = t[1:].partition("]:")
        return host, int(port)
    host, _, port = t.rpartition(":")
    return (host, int(port)) if host else (t, 443)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Scan TLS endpoints and PEM certificates into a CycloneDX 1.6 CBOM.")
    ap.add_argument("--endpoint", action="append", default=[], help="host:port to probe (repeatable)")
    ap.add_argument("--servername", help="SNI name to send (default: the host)")
    ap.add_argument("--groups", help="client key exchange groups to offer, colon-separated (default: OpenSSL defaults)")
    ap.add_argument("--probe-pq", action="store_true", help="also test a handshake that offers only X25519MLKEM768")
    ap.add_argument("--cert-file", action="append", default=[], help="PEM certificate file (repeatable)")
    ap.add_argument("--cert-dir", help="directory of *.pem / *.crt files")
    ap.add_argument("--openssl", default=os.environ.get("OPENSSL", "openssl"), help="openssl binary (3.5+ for ML-KEM)")
    ap.add_argument("--timeout", type=float, default=10.0)
    ap.add_argument("--output", "-o", help="write CBOM JSON here (default stdout)")
    args = ap.parse_args(argv)

    if not args.endpoint and not args.cert_file and not args.cert_dir:
        ap.error("give at least one --endpoint, --cert-file, or --cert-dir")

    ver = openssl_version(args.openssl)
    b = CbomBuilder()
    for target in args.endpoint:
        host, port = parse_target(target)
        sni = args.servername or (host if not re.fullmatch(r"[\d.]+|[0-9a-fA-F:]+", host) else None)
        probe = probe_endpoint(host, port, sni, args.openssl, args.groups, args.timeout)
        pq = probe_endpoint(host, port, sni, args.openssl, "X25519MLKEM768", args.timeout) if args.probe_pq else None
        b.add_endpoint(f"{host}:{port}", probe, pq)

    files = list(args.cert_file)
    if args.cert_dir:
        files += sorted(glob.glob(os.path.join(args.cert_dir, "*.pem")) + glob.glob(os.path.join(args.cert_dir, "*.crt")))
    for path in files:
        with open(path, encoding="utf-8") as fh:
            for pem in PEM_RE.findall(fh.read()):
                b.add_certificate(parse_certificate(pem, args.openssl), path)

    bom = b.bom(ver)
    out = json.dumps(bom, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out + "\n")
    else:
        print(out)
    for f in b.findings:
        print(f"[{f['priority']}] {f['source']} {f['asset']}: {f['issue']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
