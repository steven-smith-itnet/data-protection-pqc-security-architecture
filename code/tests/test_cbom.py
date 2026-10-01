import json
import re
import shutil
import socket
import subprocess
import time

import pytest

import cbom_scan as cb

OPENSSL = shutil.which("openssl")


def _openssl_35():
    if not OPENSSL:
        return False
    m = re.search(r"OpenSSL (\d+)\.(\d+)", subprocess.run([OPENSSL, "version"], capture_output=True, text=True).stdout)
    return bool(m) and (int(m.group(1)), int(m.group(2))) >= (3, 5)


needs_openssl35 = pytest.mark.skipif(not _openssl_35(), reason="OpenSSL 3.5+ required for ML-KEM groups")


def test_parse_target():
    assert cb.parse_target("example.org:8443") == ("example.org", 8443)
    assert cb.parse_target("example.org") == ("example.org", 443)
    assert cb.parse_target("[::1]:4433") == ("::1", 4433)


@pytest.mark.parametrize("name,vuln", [
    ("ecdsa_secp256r1_sha256", True), ("rsa_pss_rsae_sha256", True), ("sha256WithRSAEncryption", True),
    ("ED25519", True), ("mldsa65", False), ("ML-DSA-87", False), ("SLH-DSA-SHA2-128s", False),
])
def test_signature_assessment(name, vuln):
    assert cb.signature_assessment(name)["vulnerable"] is vuln


def test_pq_name_detection():
    assert cb.is_pq_name("X25519MLKEM768") and cb.is_pq_name("SecP256r1MLKEM768")
    assert not cb.is_pq_name("X25519") and not cb.is_pq_name("secp384r1")


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def tls_servers(tmp_path_factory):
    d = tmp_path_factory.mktemp("tls")
    subprocess.run([OPENSSL, "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256", "-nodes",
                    "-days", "7", "-subj", "/CN=test.example", "-keyout", d / "k.pem", "-out", d / "c.pem"],
                   check=True, capture_output=True)
    procs, ports = [], {}
    for name, groups in (("pq", "X25519MLKEM768"), ("classical", "X25519")):
        port = _free_port()
        procs.append(subprocess.Popen([OPENSSL, "s_server", "-accept", str(port), "-cert", d / "c.pem",
                                       "-key", d / "k.pem", "-groups", groups, "-www", "-quiet"],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        ports[name] = port
    time.sleep(0.8)
    yield ports, d / "c.pem"
    for p in procs:
        p.terminate()
        p.wait(timeout=5)


@needs_openssl35
def test_probe_hybrid_pq_endpoint(tls_servers):
    ports, _ = tls_servers
    r = cb.probe_endpoint("127.0.0.1", ports["pq"], "test.example", OPENSSL, None, 10)
    assert r["ok"] and r["protocol"] == "TLSv1.3" and r["group"] == "X25519MLKEM768"
    assert r["certificates"][0]["public_key_algorithm"] == "id-ecPublicKey"
    assert r["certificates"][0]["public_key_bits"] == 256


@needs_openssl35
def test_probe_classical_endpoint_and_cbom(tls_servers):
    ports, _ = tls_servers
    target = f"127.0.0.1:{ports['classical']}"
    probe = cb.probe_endpoint("127.0.0.1", ports["classical"], "test.example", OPENSSL, None, 10)
    pq = cb.probe_endpoint("127.0.0.1", ports["classical"], "test.example", OPENSSL, "X25519MLKEM768", 10)
    assert probe["group"] == "X25519" and not pq["ok"]
    b = cb.CbomBuilder()
    b.add_endpoint(target, probe, pq)
    bom = b.bom("test")
    assert bom["bomFormat"] == "CycloneDX" and bom["specVersion"] == "1.6"
    comps = {c["bom-ref"]: c for c in bom["components"]}
    x = comps["crypto/algorithm/X25519"]
    assert x["cryptoProperties"]["algorithmProperties"]["nistQuantumSecurityLevel"] == 0
    assert {"name": "cbom:quantum-vulnerable", "value": "true"} in x["properties"]
    proto = comps[f"crypto/protocol/tls/{target}"]
    assert proto["cryptoProperties"]["protocolProperties"]["cipherSuites"][0]["identifiers"]
    assert {"name": "cbom:hybrid-pq-supported", "value": "false"} in proto["properties"]
    assert any(f["priority"] == "high" and f["asset"] == "X25519" for f in b.findings)


@needs_openssl35
def test_cli_writes_cbom_for_endpoint_and_cert(tls_servers, tmp_path):
    ports, cert = tls_servers
    out = tmp_path / "cbom.json"
    rc = cb.main(["--endpoint", f"127.0.0.1:{ports['pq']}", "--servername", "test.example", "--probe-pq",
                  "--cert-file", str(cert), "-o", str(out)])
    assert rc == 0
    bom = json.loads(out.read_text())
    names = {c["name"] for c in bom["components"]}
    assert "X25519MLKEM768" in names and "AES-256-GCM" in names
    kem = next(c for c in bom["components"] if c["name"] == "X25519MLKEM768")
    assert kem["cryptoProperties"]["algorithmProperties"]["primitive"] == "kem"
    assert kem["cryptoProperties"]["algorithmProperties"]["nistQuantumSecurityLevel"] == 3


@needs_openssl35
def test_mldsa_certificate_parsed(tmp_path):
    subprocess.run([OPENSSL, "req", "-x509", "-newkey", "ML-DSA-65", "-nodes", "-days", "7", "-subj", "/CN=pq.example",
                    "-keyout", tmp_path / "k.pem", "-out", tmp_path / "c.pem"], check=True, capture_output=True)
    cert = cb.parse_certificate((tmp_path / "c.pem").read_text(), OPENSSL)
    assert cert["signature_algorithm"] == "ML-DSA-65" and cert["public_key_algorithm"] == "ML-DSA-65"
    b = cb.CbomBuilder()
    b.add_certificate(cert, "c.pem")
    assert b.findings == []  # nothing quantum-vulnerable
