# PQC lab: OpenSSL 3.5 ML-KEM, ML-DSA, SLH-DSA, and hybrid TLS

Scripts that exercise the NIST post-quantum algorithms (FIPS 203, 204, 205) and the hybrid TLS 1.3
key exchange `X25519MLKEM768` using the OpenSSL command line. Every file under `output/` is real
captured output from running these scripts; nothing in it was edited by hand.

The walkthrough with explanations is on the site: *Phase 6: Post-quantum cryptography > Hands-on
PQC lab* (`docs/06-pqc/pqc-lab.md`).

## Requirements

- OpenSSL 3.5 or later on `PATH` (or set `OPENSSL=/path/to/openssl`). OpenSSL 3.5 is the first
  release with ML-KEM, ML-DSA, and SLH-DSA in the default provider.
- bash, coreutils, `xxd`, `bc`, `awk`, `sed`.
- Step 6 opens a TCP listener on `localhost:14433` (override with `PORT=`).

The captured outputs were produced with OpenSSL 3.5.5 (Ubuntu package `3.5.5-1ubuntu3.6`) on
Linux, Intel Core i7-8700K.

## Scripts

| Script | What it demonstrates | Output |
|---|---|---|
| `01-list-algorithms.sh` | OpenSSL version, KEM algorithms, ML-DSA/SLH-DSA signature algorithms, TLS 1.3 groups | `output/01-list-algorithms.txt` |
| `02-mlkem-encap-decap.sh` | ML-KEM-768 keygen, encapsulate, decapsulate, matching shared secrets, tampered ciphertext | `output/02-mlkem-encap-decap.txt` |
| `03-mldsa-sign-verify.sh` | ML-DSA-65 keygen, sign, verify, tampered message rejected | `output/03-mldsa-sign-verify.txt` |
| `04-slhdsa-sign-verify.sh` | SLH-DSA-SHA2-128s and -128f sign and verify, signature size and signing time | `output/04-slhdsa-sign-verify.txt` |
| `05-mldsa-certificate.sh` | Self-signed ML-DSA-65 CA certificate, inspection, verification, size vs ECDSA and RSA | `output/05-mldsa-certificate.txt` |
| `06-hybrid-tls.sh` | Local `s_server`/`s_client` handshakes: hybrid vs classical, ML-DSA vs ECDSA certificate, HelloRetryRequest fallback, ClientHello size | `output/06-hybrid-tls.txt` |
| `07-size-comparison.sh` | Public key, private key, ciphertext, and signature sizes measured from generated files | `output/07-size-comparison.txt` |
| `08-speed.sh` | Short `openssl speed` run: ML-KEM vs X25519 vs RSA-3072, ML-DSA vs ECDSA vs Ed25519 | `output/08-speed.txt` |
| `run-all.sh` | Runs 01 to 08 and rewrites `output/` | |
| `common.sh` | Shared helpers (temp directory, command echo, version check) | |

## Running

```bash
cd code/pqc-lab
./run-all.sh              # all steps, refreshes output/
./02-mlkem-encap-decap.sh # a single step, prints to the terminal
SECS=5 ./08-speed.sh      # longer benchmark
```

## Key handling

All keys, certificates, ciphertexts, and shared secrets are **throwaway lab material**. Each
script creates a private temporary directory with `mktemp -d`, works inside it, and deletes it on
exit (`trap ... EXIT`). No private key is written into this repository. Do not reuse anything from
this lab for a real system.

## Notes on reading the output

- Shared secrets, serial numbers, and key bytes differ on every run. Sizes do not (except DER
  encoded ECDSA signatures, which vary by a byte or two).
- DER sizes include ASN.1 and SubjectPublicKeyInfo wrapping, so they are about 22 bytes larger
  than the raw FIPS 203/204 sizes (for example, ML-KEM-768: 1,184-byte raw key, 1,206-byte DER).
- In this OpenSSL build the ML-KEM and ML-DSA private key files contain both the seed and the
  expanded private key, which is why they are larger than the FIPS raw private key sizes.
- `openssl speed` numbers depend on CPU, build flags, and load. Use them as relative indicators
  only.
