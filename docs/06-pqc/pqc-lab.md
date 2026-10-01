---
title: Hands-on PQC lab
parent: "Phase 6: Post-quantum cryptography"
nav_order: 6
description: "Reproducible OpenSSL 3.5 lab for ML-KEM, ML-DSA, SLH-DSA, ML-DSA certificates, and hybrid X25519MLKEM768 TLS, with real captured output."
---

# Hands-on PQC lab
{: .no_toc }

**Phase 6: Post-quantum cryptography.** Demonstrates with real commands and real output that the NIST PQC algorithms and hybrid TLS work today with a standard OpenSSL build, and measures what they cost.
{: .fs-5 .fw-300 }

## On this page
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## About this lab

Every output block on this page was produced by running the scripts in [code/pqc-lab](https://github.com/steven-smith-itnet/data-protection-pqc-security-architecture/tree/main/code/pqc-lab) and is copied from the captured files in [code/pqc-lab/output](https://github.com/steven-smith-itnet/data-protection-pqc-security-architecture/tree/main/code/pqc-lab/output). Long hexadecimal values are trimmed where marked; nothing else is edited. Shared secrets, serial numbers, and key bytes will differ on each run; sizes will not.

| Item | Value |
|---|---|
| OpenSSL | 3.5.5 (27 Jan 2026), Ubuntu package `3.5.5-1ubuntu3.6` |
| OS | Linux 7.0 (Ubuntu), x86-64 |
| CPU | Intel Core i7-8700K @ 3.70GHz |
| Captured | 2026-09-30 |

{: .important }
All keys and certificates in this lab are throwaway lab material. Each script works in a private temporary directory created with `mktemp -d` and deletes it on exit, so no private key is written to the repository. Do not reuse anything from this lab for a real system.

```mermaid
flowchart LR
    S1["1. List algorithms"] --> S2["2. ML-KEM-768<br/>encap and decap"]
    S2 --> S3["3. ML-DSA-65<br/>sign and verify"]
    S3 --> S4["4. SLH-DSA<br/>sign and verify"]
    S4 --> S5["5. ML-DSA-65<br/>certificate"]
    S5 --> S6["6. Hybrid TLS 1.3<br/>X25519MLKEM768"]
    S6 --> S7["7. Size comparison"]
    S7 --> S8["8. Speed comparison"]
```

### What each step proves

| Step | Question for the organization | Result in brief |
|---|---|---|
| 1 | Does a standard OpenSSL build support the NIST algorithms and hybrid TLS groups? | Yes: ML-KEM-512/768/1024, ML-DSA-44/65/87, all 12 SLH-DSA sets, 4 hybrid KEMs |
| 2 | Does ML-KEM produce a matching shared secret, and how does it behave under tampering? | Secrets match; tampered ciphertext silently yields a different secret |
| 3 | Can ML-DSA replace ECDSA for signing? | Yes; signatures are 3,309 bytes |
| 4 | Is SLH-DSA practical? | For low-volume signing only; 7,856-byte signatures, about 0.86 seconds to sign (128s) |
| 5 | Can the organization issue ML-DSA certificates today? | Yes, with standard tooling; certificate is 5,620 bytes vs 482 for ECDSA |
| 6 | Does hybrid TLS negotiate and fall back cleanly? | Yes; the ClientHello grows from 239 to 1,415 bytes |
| 7 | What are the real key and signature sizes? | Match FIPS values plus DER overhead |
| 8 | What does PQC cost in CPU? | ML-KEM is as fast as X25519 or faster; ML-DSA signing is slower than ECDSA |

### Running it

```bash
git clone https://github.com/steven-smith-itnet/data-protection-pqc-security-architecture.git
cd data-protection-pqc-security-architecture/code/pqc-lab
openssl version            # must be 3.5 or later
./run-all.sh               # runs steps 01 to 08 and rewrites output/
```

All scripts use `set -euo pipefail` and source a shared `common.sh` that creates the temporary working directory, prints each command before running it, and checks the OpenSSL version.

## Step 1: List the PQC algorithms

Script: `01-list-algorithms.sh`. Output: `output/01-list-algorithms.txt`.

```
==== OpenSSL version ====
OpenSSL 3.5.5 27 Jan 2026 (Library: OpenSSL 3.5.5 27 Jan 2026)

==== KEM algorithms (ML-KEM and hybrid TLS KEMs) ====

$ openssl list -kem-algorithms
  { 1.2.840.113549.1.1.1, 2.5.8.1.1, RSA, rsaEncryption } @ default
  { 1.2.840.10045.2.1, EC, id-ecPublicKey } @ default
  { 1.3.101.110, X25519 } @ default
  { 1.3.101.111, X448 } @ default
  { 2.16.840.1.101.3.4.4.1, id-alg-ml-kem-512, ML-KEM-512, MLKEM512 } @ default
  { 2.16.840.1.101.3.4.4.2, id-alg-ml-kem-768, ML-KEM-768, MLKEM768 } @ default
  { 2.16.840.1.101.3.4.4.3, id-alg-ml-kem-1024, ML-KEM-1024, MLKEM1024 } @ default
  X25519MLKEM768 @ default
  X448MLKEM1024 @ default
  SecP256r1MLKEM768 @ default
  SecP384r1MLKEM1024 @ default

==== PQC signature algorithms (ML-DSA and SLH-DSA only) ====

$ openssl list -signature-algorithms | grep -Ei 'ml-dsa|slh-dsa'
  { 2.16.840.1.101.3.4.3.17, id-ml-dsa-44, ML-DSA-44, MLDSA44 } @ default
  { 2.16.840.1.101.3.4.3.18, id-ml-dsa-65, ML-DSA-65, MLDSA65 } @ default
  { 2.16.840.1.101.3.4.3.19, id-ml-dsa-87, ML-DSA-87, MLDSA87 } @ default
  { 2.16.840.1.101.3.4.3.20, id-slh-dsa-sha2-128s, SLH-DSA-SHA2-128s } @ default
  { 2.16.840.1.101.3.4.3.21, id-slh-dsa-sha2-128f, SLH-DSA-SHA2-128f } @ default
  { 2.16.840.1.101.3.4.3.22, id-slh-dsa-sha2-192s, SLH-DSA-SHA2-192s } @ default
  { 2.16.840.1.101.3.4.3.23, id-slh-dsa-sha2-192f, SLH-DSA-SHA2-192f } @ default
  { 2.16.840.1.101.3.4.3.24, id-slh-dsa-sha2-256s, SLH-DSA-SHA2-256s } @ default
  { 2.16.840.1.101.3.4.3.25, id-slh-dsa-sha2-256f, SLH-DSA-SHA2-256f } @ default
  { 2.16.840.1.101.3.4.3.26, id-slh-dsa-shake-128s, SLH-DSA-SHAKE-128s } @ default
  { 2.16.840.1.101.3.4.3.27, id-slh-dsa-shake-128f, SLH-DSA-SHAKE-128f } @ default
  { 2.16.840.1.101.3.4.3.28, id-slh-dsa-shake-192s, SLH-DSA-SHAKE-192s } @ default
  { 2.16.840.1.101.3.4.3.29, id-slh-dsa-shake-192f, SLH-DSA-SHAKE-192f } @ default
  { 2.16.840.1.101.3.4.3.30, id-slh-dsa-shake-256s, SLH-DSA-SHAKE-256s } @ default
  { 2.16.840.1.101.3.4.3.31, id-slh-dsa-shake-256f, SLH-DSA-SHAKE-256f } @ default

==== TLS 1.3 groups offered by this build ====

$ openssl list -tls-groups -tls1_3
secp256r1:secp384r1:secp521r1:x25519:x448:brainpoolP256r1tls13:brainpoolP384r1tls13:brainpoolP512r1tls13:ffdhe2048:ffdhe3072:ffdhe4096:ffdhe6144:ffdhe8192:MLKEM512:MLKEM768:MLKEM1024:SecP256r1MLKEM768:X25519MLKEM768:SecP384r1MLKEM1024
```

What to notice:

- The object identifiers under `2.16.840.1.101.3.4.4` (ML-KEM) and `2.16.840.1.101.3.4.3.17` to `.31` (ML-DSA and SLH-DSA) are the NIST-assigned OIDs. These are the values a CBOM scanner looks for in certificates and keys.
- `X448MLKEM1024` is available as a KEM but does not appear in this build's TLS 1.3 group list. The three hybrid TLS groups are `X25519MLKEM768`, `SecP256r1MLKEM768`, and `SecP384r1MLKEM1024`, matching the IETF ECDHE-MLKEM draft.
- Pure ML-KEM groups (`MLKEM512`, `MLKEM768`, `MLKEM1024`) are also available for TLS. The organization does not use them yet; hybrid is the standard.

## Step 2: ML-KEM-768 encapsulation and decapsulation

Script: `02-mlkem-encap-decap.sh`. Output: `output/02-mlkem-encap-decap.txt`.

In OpenSSL 3.5 the KEM operations are `openssl pkeyutl -encap` (with the recipient's public key, writing the ciphertext with `-out` and the sender's copy of the shared secret with `-secret`) and `openssl pkeyutl -decap` (with the private key, reading the ciphertext with `-in` and writing the recovered secret with `-out`).

```
==== Generate an ML-KEM-768 key pair (throwaway, in a temp dir) ====

$ openssl genpkey -algorithm ML-KEM-768 -out mlkem768.key

$ openssl pkey -in mlkem768.key -pubout -out mlkem768.pub

$ openssl pkey -pubin -in mlkem768.pub -text -noout   (first lines only)
ML-KEM-768 Public-Key:
ek:
    d5:87:c5:e0:e7:c2:9a:e4:69:e9:d0:be:89:7c:6e:
    ec:40:7a:b7:c1:0a:41:f2:59:12:44:08:18:46:c5:
    ... (81 lines in total; encapsulation key trimmed) ...

==== Sender: encapsulate to the public key ====

$ openssl pkeyutl -encap -pubin -inkey mlkem768.pub -out ct.bin -secret ss_sender.bin

==== Receiver: decapsulate the ciphertext with the private key ====

$ openssl pkeyutl -decap -inkey mlkem768.key -in ct.bin -out ss_receiver.bin

==== Sizes (bytes) ====
ciphertext        1088
sender secret     32
receiver secret   32
public key (DER)  1206

==== Compare shared secrets ====
sender   : 06f09086c2982b80c4e3b2cead387c834f3f1a5cb70b3ec3f62ff01423e206c8
receiver : 06f09086c2982b80c4e3b2cead387c834f3f1a5cb70b3ec3f62ff01423e206c8
RESULT: shared secrets MATCH

==== Negative test: decapsulate a ciphertext with one flipped byte ====

$ openssl pkeyutl -decap -inkey mlkem768.key -in ct_tampered.bin -out ss_tampered.bin
tampered : b552af8b64816df89aa5407e76db2a7968b5638fcbba7dd4ae1b7f344baabab0
RESULT: tampered ciphertext yields an unrelated secret (implicit rejection); no error is raised
```

What to notice:

- The ciphertext is exactly **1,088 bytes** and the shared secret **32 bytes**, as specified in FIPS 203 for ML-KEM-768. The public key is 1,206 bytes in DER, which is the 1,184-byte encapsulation key plus 22 bytes of SubjectPublicKeyInfo wrapping.
- The sender and receiver derive the same 32-byte secret. In a real protocol that secret is fed into a KDF to derive symmetric keys; it is never used directly as a data key without a KDF.
- **Implicit rejection:** decapsulating a tampered ciphertext does not produce an error. It returns a pseudorandom value that does not match. The failure shows up later, when the derived key fails to authenticate data (for example, an AES-GCM tag check or a TLS Finished message). Engineers writing tests should not expect `decap` to fail on bad input.

{: .note }
A KEM is not interchangeable with Diffie-Hellman in code: there is no "peer public key" on the decapsulating side, and the encapsulating side cannot choose the secret. Code that wraps an existing key with a KEM must use the KEM output as input to a KDF and then wrap the existing key with AES key wrap or an AEAD.

## Step 3: ML-DSA-65 sign and verify

Script: `03-mldsa-sign-verify.sh`. Output: `output/03-mldsa-sign-verify.txt`.

```
==== Generate an ML-DSA-65 key pair (throwaway, in a temp dir) ====

$ openssl genpkey -algorithm ML-DSA-65 -out mldsa65.key

$ openssl pkey -in mldsa65.key -pubout -out mldsa65.pub

==== Sign the message (ML-DSA signs the raw message; no separate digest step) ====

$ openssl pkeyutl -sign -rawin -inkey mldsa65.key -in message.txt -out message.sig
signature bytes: 3309

==== Verify with the public key ====

$ openssl pkeyutl -verify -rawin -pubin -inkey mldsa65.pub -in message.txt -sigfile message.sig
Signature Verified Successfully

==== Tamper test: change one character of the message and verify again ====

$ openssl pkeyutl -verify -rawin -pubin -inkey mldsa65.pub -in message_tampered.txt -sigfile message.sig
40B705C8D9710000:error:030000EA:digital envelope routines:EVP_DigestVerify:provider signature failure:../crypto/evp/m_sigver.c:779:ML-DSA-65 digest_verify:
Signature Verification Failure
exit code: 1 (non-zero means verification failed, as expected)
```

What to notice:

- The signature is exactly **3,309 bytes**, the FIPS 204 size for ML-DSA-65, compared with 64 bytes for Ed25519 and about 72 bytes for ECDSA P-256.
- `-rawin` passes the whole message to the algorithm. This is pure ML-DSA, which hashes internally. Pre-hashing with `-digest` would require HashML-DSA, a different variant with different signatures. Systems that sign digests (for example, some HSM integrations and code signing tools) must record which variant they use.
- Changing one character (`LAB01` to `LAB02`) causes verification to fail with a non-zero exit code, which scripts and pipelines can rely on.

## Step 4: SLH-DSA sign and verify

Script: `04-slhdsa-sign-verify.sh`. Output: `output/04-slhdsa-sign-verify.txt`.

The scenario is signing a door lock firmware manifest, the use case where a hash-based signature is most attractive.

```
==== SLH-DSA-SHA2-128s ====

$ openssl genpkey -algorithm SLH-DSA-SHA2-128s -out slh.key

$ openssl pkey -in slh.key -pubout -out slh.pub

$ openssl pkeyutl -sign -rawin -inkey slh.key -in manifest.txt -out manifest.sig
signature bytes: 7856   sign wall time: 0.86 s

$ openssl pkeyutl -verify -rawin -pubin -inkey slh.pub -in manifest.txt -sigfile manifest.sig
Signature Verified Successfully

==== SLH-DSA-SHA2-128f ====

$ openssl genpkey -algorithm SLH-DSA-SHA2-128f -out slh.key

$ openssl pkey -in slh.key -pubout -out slh.pub

$ openssl pkeyutl -sign -rawin -inkey slh.key -in manifest.txt -out manifest.sig
signature bytes: 17088   sign wall time: 0.05 s

$ openssl pkeyutl -verify -rawin -pubin -inkey slh.pub -in manifest.txt -sigfile manifest.sig
Signature Verified Successfully
```

What to notice:

- The "small" parameter set (128s) produces **7,856-byte** signatures and took **0.86 seconds** to sign on this CPU (wall time including process start-up). The "fast" set (128f) signs in about **0.05 seconds** but produces **17,088-byte** signatures.
- The public key is only 32 bytes (50 bytes in DER, see step 7), which suits constrained verifiers that store a root key in a small secure element.
- For firmware released a few times a year, signing time is irrelevant and the conservative security basis (hash functions only) is valuable. For TLS or high-volume API signing, SLH-DSA is not suitable.
- SLH-DSA is stateless, unlike LMS and XMSS, so it does not carry the state-reuse risk. OpenSSL 3.5 does not provide LMS or XMSS signing in the command line tool; stateful signing belongs in an HSM with state management anyway.

## Step 5: ML-DSA-65 self-signed certificate

Script: `05-mldsa-certificate.sh`. Output: `output/05-mldsa-certificate.txt`.

```
==== Self-signed ML-DSA-65 certificate (lab root, 30 days) ====

$ openssl req -x509 -new -newkey ML-DSA-65 -nodes -keyout lab-root.key -out lab-root.crt -days 30 -subj '/O=Example Hospitality Lab/CN=PQC Lab Root ML-DSA-65' -addext basicConstraints=critical,CA:TRUE -addext keyUsage=critical,keyCertSign,cRLSign
-----

==== Inspect the certificate (public key hex trimmed) ====

$ openssl x509 -in lab-root.crt -noout -text | (trimmed)
Certificate:
    Data:
        Version: 3 (0x2)
        Serial Number:
            27:d0:4e:cf:72:94:e2:ad:7f:c6:99:c8:87:d4:6f:c6:ad:dc:41:a4
        Signature Algorithm: ML-DSA-65
        Issuer: O=Example Hospitality Lab, CN=PQC Lab Root ML-DSA-65
        Validity
            Not Before: Sep 30 22:25:08 2026 GMT
            Not After : Oct 30 22:25:08 2026 GMT
        Subject: O=Example Hospitality Lab, CN=PQC Lab Root ML-DSA-65
        Subject Public Key Info:
            Public Key Algorithm: ML-DSA-65
                ML-DSA-65 Public-Key:
                pub:
                    86:7d:0f:0b:71:e4:7a:69:ea:08:d7:97:e6:8b:e5:
                ... (public key bytes trimmed) ...
        X509v3 extensions:
            X509v3 Subject Key Identifier:
                27:AA:E5:D2:41:1E:17:F5:1D:F8:10:9B:3E:E6:79:A9:21:1D:3B:18
            X509v3 Authority Key Identifier:
                27:AA:E5:D2:41:1E:17:F5:1D:F8:10:9B:3E:E6:79:A9:21:1D:3B:18
            X509v3 Basic Constraints: critical
                CA:TRUE
            X509v3 Key Usage: critical
                Certificate Sign, CRL Sign
    Signature Algorithm: ML-DSA-65
    Signature Value:
        f7:3e:1c:be:7c:d5:ec:57:62:df:82:62:27:d3:b8:8f:3c:3d:
        ... (signature bytes trimmed) ...

==== Verify the self-signature ====

$ openssl verify -CAfile lab-root.crt lab-root.crt
lab-root.crt: OK

==== Certificate size comparison (DER bytes) ====
ECDSA P-256 cert          482 bytes
RSA-3072 cert            1129 bytes
ML-DSA-65 cert           5620 bytes
```

What to notice:

- Standard `openssl req -x509` issues an ML-DSA certificate with no special options. The signature algorithm and public key algorithm both show `ML-DSA-65`.
- A minimal ML-DSA-65 certificate is **5,620 bytes**, about **11.7 times** an equivalent ECDSA P-256 certificate (482 bytes) and **5 times** RSA-3072 (1,129 bytes). A TLS chain of leaf plus intermediate, both ML-DSA-65, would carry roughly 11 KB of certificates plus a 3,309-byte CertificateVerify signature, before any Certificate Transparency SCTs. Step 6 shows the effect: the handshake with an ML-DSA certificate read 10,229 bytes versus 1,867 with ECDSA.
- These sizes are why the organization migrates key exchange first and treats PQC certificates on public endpoints as ecosystem-dependent. Internally, where the organization controls both ends, ML-DSA certificates are practical now.

## Step 6: Hybrid TLS 1.3 handshake with X25519MLKEM768

Script: `06-hybrid-tls.sh`. Output: `output/06-hybrid-tls.txt`.

The script starts `openssl s_server` on `localhost:14433` with a throwaway certificate, connects with `openssl s_client`, records the handshake messages with `-msg`, and extracts the negotiated parameters. It runs four cases.

```
==== Hybrid PQ: X25519MLKEM768 key exchange, ML-DSA-65 server certificate ====

$ openssl s_server -accept 14433 -cert srv.crt -key srv.key -tls1_3 -groups X25519MLKEM768 -www -quiet &
$ echo Q | openssl s_client -connect localhost:14433 -tls1_3 -groups X25519MLKEM768 -CAfile srv.crt -servername localhost -msg
  (handshake messages)
    >>> TLS 1.3, Handshake [length 0587], ClientHello
    <<< TLS 1.3, Handshake [length 04ba], ServerHello
  (negotiated parameters)
    Negotiated TLS1.3 group: X25519MLKEM768
    New, TLSv1.3, Cipher is TLS_AES_256_GCM_SHA384
    Peer signature type: mldsa65
    Server public key is 15616 bit
    SSL handshake has read 10229 bytes and written 1500 bytes
    Verification: OK

==== Classical comparison: X25519 key exchange, ML-DSA-65 server certificate ====

$ openssl s_server -accept 14433 -cert srv.crt -key srv.key -tls1_3 -groups X25519 -www -quiet &
$ echo Q | openssl s_client -connect localhost:14433 -tls1_3 -groups X25519 -CAfile srv.crt -servername localhost -msg
  (handshake messages)
    >>> TLS 1.3, Handshake [length 00ef], ClientHello
    <<< TLS 1.3, Handshake [length 007a], ServerHello
  (negotiated parameters)
    New, TLSv1.3, Cipher is TLS_AES_256_GCM_SHA384
    Peer signature type: mldsa65
    Peer Temp Key: X25519, 253 bits
    Server public key is 15616 bit
    SSL handshake has read 9141 bytes and written 324 bytes
    Verification: OK

==== Most common near-term deployment: X25519MLKEM768 with an ECDSA P-256 certificate ====

$ openssl s_server -accept 14433 -cert srv-ec.crt -key srv-ec.key -tls1_3 -groups X25519MLKEM768:X25519 -www -quiet &
$ echo Q | openssl s_client -connect localhost:14433 -tls1_3 -groups X25519MLKEM768:X25519 -CAfile srv-ec.crt -servername localhost -msg
  (handshake messages)
    >>> TLS 1.3, Handshake [length 0591], ClientHello
    <<< TLS 1.3, Handshake [length 04ba], ServerHello
  (negotiated parameters)
    Negotiated TLS1.3 group: X25519MLKEM768
    New, TLSv1.3, Cipher is TLS_AES_256_GCM_SHA384
    Peer signature type: ecdsa_secp256r1_sha256
    Peer signing digest: SHA256
    Server public key is 256 bit
    SSL handshake has read 1867 bytes and written 1510 bytes
    Verification: OK

==== Fallback: client offers hybrid then X25519, server supports only X25519 ====

$ openssl s_server -accept 14433 -cert srv-ec.crt -key srv-ec.key -tls1_3 -groups X25519 -www -quiet &
$ echo Q | openssl s_client -connect localhost:14433 -tls1_3 -groups X25519MLKEM768:X25519 -CAfile srv-ec.crt -servername localhost -msg
  (handshake messages)
    >>> TLS 1.3, Handshake [length 0591], ClientHello
    <<< TLS 1.3, Handshake [length 0058], ServerHello
    >>> TLS 1.3, Handshake [length 00f1], ClientHello
    <<< TLS 1.3, Handshake [length 007a], ServerHello
  (negotiated parameters)
    New, TLSv1.3, Cipher is TLS_AES_256_GCM_SHA384
    Peer signature type: ecdsa_secp256r1_sha256
    Peer signing digest: SHA256
    Peer Temp Key: X25519, 253 bits
    Server public key is 256 bit
    SSL handshake has read 872 bytes and written 1756 bytes
    Verification: OK

==== ClientHello and ServerHello sizes: hybrid vs classical key share ====
group             ClientHello bytes  ServerHello bytes
X25519                          239                122
X25519MLKEM768                 1415               1210
Sizes are handshake message bodies as reported by s_client -msg (record headers excluded).
```

How to read the four cases:

| Case | Key exchange | Authentication | What it shows |
|---|---|---|---|
| 1 | `X25519MLKEM768` | ML-DSA-65 | A fully post-quantum handshake is possible today with OpenSSL 3.5 on both ends. The client read 10,229 bytes, dominated by the ML-DSA certificate and signature |
| 2 | `X25519` (reported as `Peer Temp Key: X25519, 253 bits`) | ML-DSA-65 | Key exchange and authentication are independent choices; this handshake is still exposed to harvest now, decrypt later |
| 3 | `X25519MLKEM768` | ECDSA P-256 | **The configuration the organization deploys at the edge now.** Protects against HNDL; handshake read only 1,867 bytes |
| 4 | Falls back to `X25519` | ECDSA P-256 | A client that offers hybrid still connects to a classical-only server. The two ClientHello and ServerHello pairs show a HelloRetryRequest: the client sent only a hybrid key share, the server asked for X25519, costing one extra round trip |

What to notice:

- The negotiated group appears as `Negotiated TLS1.3 group: X25519MLKEM768`. When classical key exchange is used, OpenSSL reports `Peer Temp Key: X25519` instead. These are the strings to look for when testing endpoints (see [PQC migration program]({% link docs/06-pqc/migration-program.md %}#step-2-cryptographic-inventory-and-cbom)).
- The hybrid **ClientHello is 1,415 bytes** against 239 for classical: 1,216 of those bytes are the key share (1,184-byte ML-KEM-768 encapsulation key plus 32-byte X25519 share). The **ServerHello is 1,210 bytes** against 122, carrying the 1,088-byte ML-KEM ciphertext plus the 32-byte X25519 share. With the TLS record header and typical browser extensions (SNI, ALPN, GREASE), a real hybrid ClientHello can exceed a single TCP segment, which is the source of the middlebox issues described in the migration program's testing section.
- `Server public key is 15616 bit` in cases 1 and 2 is OpenSSL reporting the ML-DSA-65 public key length in bits: 1,952 bytes times 8.
- The fallback case is why the organization configures servers with both hybrid and classical groups during the transition (`X25519MLKEM768:X25519:P-256`), and why hybrid-only client configurations are avoided until partners support hybrid.

## Step 7: Key and signature sizes measured from files

Script: `07-size-comparison.sh`. Output: `output/07-size-comparison.txt`.

```
Algorithm              PubKey DER  PrivKey DER     Sig/CT bytes
---------              ----------  -----------     ------------
Key establishment
RSA-3072 (OAEP)               422         1767         384 (ct)
X25519                         44           48  32 (peer share)
ML-KEM-512                    822         1730         768 (ct)
ML-KEM-768                   1206         2498        1088 (ct)
ML-KEM-1024                  1590         3266        1568 (ct)

Signatures
RSA-3072                      422         1768        384 (sig)
ECDSA P-256                    91          121         72 (sig)
Ed25519                        44           48         64 (sig)
ML-DSA-44                    1334         2626       2420 (sig)
ML-DSA-65                    1974         4098       3309 (sig)
ML-DSA-87                    2614         4962       4627 (sig)
SLH-DSA-SHA2-128s              50           84       7856 (sig)
SLH-DSA-SHA2-128f              50           84      17088 (sig)

Note: ECDSA signatures are DER-encoded and vary by a byte or two between runs.
Note: OpenSSL 3.5 ML-KEM/ML-DSA private key DER may contain both seed and expanded key.
```

Reconciliation with FIPS sizes:

| Algorithm | FIPS public key | Measured DER | DER overhead | FIPS ciphertext or signature | Measured |
|---|---|---|---|---|---|
| ML-KEM-512 | 800 | 822 | 22 | 768 | 768 |
| ML-KEM-768 | 1,184 | 1,206 | 22 | 1,088 | 1,088 |
| ML-KEM-1024 | 1,568 | 1,590 | 22 | 1,568 | 1,568 |
| ML-DSA-44 | 1,312 | 1,334 | 22 | 2,420 | 2,420 |
| ML-DSA-65 | 1,952 | 1,974 | 22 | 3,309 | 3,309 |
| ML-DSA-87 | 2,592 | 2,614 | 22 | 4,627 | 4,627 |
| SLH-DSA-SHA2-128s | 32 | 50 | 18 | 7,856 | 7,856 |
| SLH-DSA-SHA2-128f | 32 | 50 | 18 | 17,088 | 17,088 |

Every measured ciphertext and signature matches the standard exactly. The private key files are larger than the FIPS private key sizes because this OpenSSL build stores both the seed and the expanded key. For example, ML-DSA-65: 32-byte seed plus 4,032-byte expanded key is 4,064 bytes, plus 34 bytes of PKCS#8 wrapping gives the measured 4,098. ML-KEM-768: 64-byte seed plus 2,400-byte decapsulation key is 2,464, plus 34 gives 2,498. The private key format matters when moving keys between OpenSSL, HSMs, and cloud KMS, which may accept seed-only, expanded-only, or both.

## Step 8: Speed comparison

Script: `08-speed.sh`. Output: `output/08-speed.txt`. Two seconds per test, single thread.

```
==== CPU ====
model name	: Intel(R) Core(TM) i7-8700K CPU @ 3.70GHz

==== Key establishment: ML-KEM vs X25519 vs RSA-3072 (2s per test) ====

$ openssl speed -seconds 2 -kem-algorithms ML-KEM-512 ML-KEM-768 ML-KEM-1024
                               keygen    encaps    decaps keygens/s  encaps/s  decaps/s
                 ML-KEM-512 0.000034s 0.000023s 0.000036s   29803.6   42654.6   27601.5
                 ML-KEM-768 0.000054s 0.000033s 0.000048s   18645.9   29973.6   20627.8
                ML-KEM-1024 0.000077s 0.000042s 0.000063s   13038.3   23726.9   15766.5

$ openssl speed -seconds 2 ecdhx25519 rsa3072
                   sign    verify    encrypt   decrypt   sign/s verify/s  encr./s  decr./s
rsa  3072 bits 0.001524s 0.000031s 0.000033s 0.001547s    656.0  32501.0  30355.1    646.5
                              op      op/s
 253 bits ecdh (X25519)   0.0000s  33480.4
                               keygen    encaps    decaps keygens/s  encaps/s  decaps/s
                    rsa3072 0.182727s 0.000034s 0.001537s       5.5   29201.5     650.8
                               keygen     signs    verify keygens/s    sign/s  verify/s
                    rsa3072 0.142667s 0.001544s 0.000032s       7.0     647.7   31474.0

==== Signatures: ML-DSA vs ECDSA P-256 vs Ed25519 (2s per test) ====

$ openssl speed -seconds 2 -signature-algorithms ML-DSA-44 ML-DSA-65 ML-DSA-87
                               keygen     signs    verify keygens/s    sign/s  verify/s
                  ML-DSA-44 0.000116s 0.000666s 0.000129s    8584.8    1501.5    7761.0
                  ML-DSA-65 0.000200s 0.001017s 0.000198s    5001.0     982.9    5060.3
                  ML-DSA-87 0.000292s 0.001236s 0.000324s    3429.6     809.0    3082.5

$ openssl speed -seconds 2 ecdsap256 ed25519
                              sign    verify    sign/s verify/s
 256 bits ecdsa (nistp256)   0.0000s   0.0001s  45824.5  16110.1
                              sign    verify    sign/s verify/s
 253 bits EdDSA (Ed25519)   0.0000s   0.0001s  25281.9   9400.5
```

Interpretation for the TLS server side, per handshake (operations per second on one core of this CPU):

| Server-side operation | Classical | Hybrid or PQC | Observation |
|---|---|---|---|
| Key exchange | X25519: about 33,500 ops/s | ML-KEM-768 encaps: about 30,000/s, plus the X25519 operation | Hybrid roughly doubles key exchange work, but both components are fast; unlikely to be the bottleneck |
| Server signature (CertificateVerify) | ECDSA P-256 sign: about 45,800/s | ML-DSA-65 sign: about 980/s | ML-DSA-65 signing was more than 40 times slower than ECDSA P-256 in this build; matters for servers that do many full handshakes when ML-DSA certificates arrive |
| RSA-3072 decrypt or sign, for comparison | about 650/s | | ML-DSA-65 signing is in the same range as RSA-3072 signing, which many servers run today |
| Client verification | ECDSA P-256 verify: about 16,100/s | ML-DSA-65 verify: about 5,060/s | Client-side cost acceptable |

{: .note }
These numbers come from a distribution build of OpenSSL on a 2017 desktop CPU during a short run, with no attempt to pin frequency or isolate cores. Treat them as relative indicators. Optimized implementations (for example, those with AVX2 paths in other libraries) report substantially faster ML-DSA signing. Benchmark the organization's actual load balancer and proxy platforms before capacity planning.

## Findings from the lab

| Finding | Consequence for the program |
|---|---|
| OpenSSL 3.5 supports ML-KEM, ML-DSA, SLH-DSA, and hybrid TLS groups with no extra providers | Upgrading self-managed proxies to OpenSSL 3.5 is the main enabler for hybrid TLS on infrastructure the organization runs |
| Hybrid key exchange adds about 1.2 KB to the ClientHello and 1.1 KB to the ServerHello | Test middleboxes and TLS inspection; bandwidth impact is negligible |
| Fallback to classical works with one extra round trip | Keep classical groups configured on servers during transition |
| ML-DSA certificates work with standard tooling but are about 11 times larger than ECDSA | Pilot internally; defer public endpoints until the ecosystem is ready |
| ML-DSA signing is much slower than ECDSA in this build | Capacity-test TLS terminators before ML-DSA server certificates; key exchange cost is not a concern |
| SLH-DSA is slow to sign and produces large signatures | Suitable only for low-volume, long-lived roots such as firmware |
| ML-KEM decapsulation does not error on tampered input | Test suites and error handling must not rely on a decap error |

## Key takeaways for engineering teams

- OpenSSL 3.5 is the practical baseline: it provides ML-KEM, ML-DSA, SLH-DSA, and `X25519MLKEM768` out of the box, and the commands on this page run as shown.
- Check for `Negotiated TLS1.3 group: X25519MLKEM768` in `s_client` output to confirm hybrid; `Peer Temp Key: X25519` means classical.
- Hybrid key exchange costs little CPU and about 1 KB each way; the operational risk is middleboxes, not performance.
- PQC signatures and certificates are large, and ML-DSA signing is slower; plan certificate migration separately and test chain sizes.
- Keep lab keys out of repositories: generate into a temporary directory and delete on exit, as these scripts do.

## Related pages

- [PQC standards and timelines]({% link docs/06-pqc/standards-timelines.md %})
- [PQC migration program]({% link docs/06-pqc/migration-program.md %})
- [Crypto agility and hybrid designs]({% link docs/06-pqc/crypto-agility.md %})
- [Encryption in transit]({% link docs/05-transit-in-use/in-transit.md %})
- [Code and tooling lab]({% link docs/08-engineering/code-lab.md %})

## Sources

- OpenSSL 3.5 manual, `openssl-pkeyutl`: <https://docs.openssl.org/3.5/man1/openssl-pkeyutl/>
- OpenSSL 3.5 manual, `openssl-s_client`: <https://docs.openssl.org/3.5/man1/openssl-s_client/>
- OpenSSL 3.5 release notes: <https://openssl-library.org/news/openssl-3.5-notes/>
- FIPS 203, 204, 205: <https://csrc.nist.gov/projects/post-quantum-cryptography>
- Lab scripts and captured output: <https://github.com/steven-smith-itnet/data-protection-pqc-security-architecture/tree/main/code/pqc-lab>
