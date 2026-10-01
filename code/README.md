# Code and tooling lab

Working code that backs the reference architecture at
https://steven-smith-itnet.github.io/data-protection-pqc-security-architecture/. Each tool implements one
control from the architecture so that the design can be tested, not only described. All sample data is
synthetic: public test card numbers (for example 4111111111111111), `example.com` addresses, and
fictional identities.

The documentation page for this directory is "Code and tooling lab" under Phase 7: Engineering
enablement (`docs/08-engineering/code-lab.md`). It includes captured output from every command below.

## Layout

| Path | Phase | What it does |
|---|---|---|
| `discovery/` | 1 Know the data | PII and payment card scanner: Luhn, IIN, IBAN mod-97, SSN range rules, keyword heuristics; recommends tier, label, protection profile, and tags |
| `classification/` | 1 Know the data | `label_policy.yaml` (tier to label to profile to controls, per data state and per cloud) and `resolve_controls.py` |
| `envelope/` | 2 Standards and keys | AES-256-GCM envelope encryption with a versioned, algorithm-agile header; local, AWS KMS, Azure Key Vault, and Google Cloud KMS KEK adapters |
| `tokenization/` | 3 Structured data | SQLite vault tokenizer (random, last-four-preserving, never Luhn-valid tokens, role-checked detokenization) and HMAC-SHA-256 surrogates |
| `crypto-shredding/` | 5 Transit and in use | Per-data-subject DEKs; erasure by key destruction, including backup copies |
| `cbom/` | 1 and 6 | TLS endpoint and certificate scanner (OpenSSL 3.5) that writes CycloneDX 1.6 CBOM JSON and flags quantum-vulnerable algorithms |
| `terraform/{aws,azure,gcp,oci}/` | 2, 3, 4 | Label-driven key and storage modules with tag-schema validation |
| `policy/aws-scp/` | 7 | Service control policies |
| `policy/azure-policy/` | 7 | Azure Policy definitions |
| `policy/gcp-org-policy/` | 7 | Organization policy constraints |
| `policy/opa/` | 7 | Rego policies over Terraform plan JSON, with tests and real plan fixtures |
| `tests/` | all | pytest suite for the Python tools |
| `pqc-lab/` | 6 | OpenSSL 3.5 ML-KEM, ML-DSA, SLH-DSA, and hybrid TLS scripts (see its own README) |

## Setup

```bash
cd code
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

External tools: OpenSSL 3.5 or later (CBOM scanner and its tests), Terraform 1.6 or later, OPA 1.x.
The tests that need OpenSSL 3.5 skip themselves on older versions.

## Run the tests

```bash
cd code
python -m pytest tests -q
```

## Tool by tool

### Discovery scanner

```bash
python discovery/pii_scanner.py discovery/samples --pretty
python discovery/pii_scanner.py /path/to/export --jurisdictions gdpr,ccpa --fail-on C3 -o report.json
```

Output is JSON per file: findings by type with count, confidence, and masked samples (a PAN is never
printed in full; at most the first six and last four digits), plus the recommended tier, label,
protection profile, and tag values. `--fail-on C2|C3` exits with status 2 so the scanner can gate a
pipeline. `--loyalty-regex` sets the loyalty-number pattern (the default matches a fictional
`LOY` + 9 digit format). A captured report is in `discovery/sample-output/samples-report.json`.

Limits: regex and checksum detection only. Passport detection is a keyword-proximity heuristic and is
reported as low confidence; a tier driven only by low-confidence findings is marked `needs_review`.
Production discovery uses Purview, Macie, Sensitive Data Protection, or Data Safe.

### Label-to-control resolver

```bash
python classification/resolve_controls.py data-classification=restricted data-domain=payment regulatory-scope=pci_gdpr
python classification/resolve_controls.py data-classification=confidential data-domain=guest --cloud azure --json
```

Validates tags against the schema in `label_policy.yaml` (allowed values, lowercase, `regulatory-scope`
atoms joined by `_`, profile not weaker than the classification, `pci` only on restricted data) and
prints the control set. Exit status 1 on any validation error. The tests check that the tag values in
the YAML, the Terraform validation blocks, and the OPA policy are identical.

### Envelope encryption

```bash
python envelope/envelope_encryption.py   # demo: encrypt, decrypt, rotate KEK, re-wrap
```

Blob format: `"DPE"` magic, format version, header length, canonical JSON header (`alg`, `kek`, `wdek`,
`nonce`, `ctx`), then ciphertext. The encryption context is bound as AAD. Re-wrapping under a new KEK
changes only the header; the ciphertext bytes stay the same (tested).

The AWS, Azure, and Google Cloud adapters import their SDKs lazily. **They have not been run against
real cloud services in this repository** (no credentials in the build environment). The tests exercise
their call wiring with stub clients only.

### Tokenization and surrogates

```bash
python tokenization/vault_tokenizer.py
python tokenization/keyed_hash.py
```

Vault tokens are random, keep the last four digits, and are forced to fail the Luhn check, so they are
never mistaken for a PAN (the tests confirm the discovery scanner does not flag them). The vault stores
the PAN encrypted with AES-256-GCM and indexes it by HMAC-SHA-256, never a plain hash. Surrogates use
per-purpose HMAC keys derived with HKDF, so datasets join within a purpose but not across purposes.

### Crypto-shredding

```bash
python crypto-shredding/crypto_shred.py
```

Each data subject has a DEK wrapped by a KEK. Shredding one subject nulls the wrapped DEK
(`PRAGMA secure_delete` is on, and a test confirms the wrapped key bytes are gone from the database
file). Copies of that subject's ciphertext, including backups, become unreadable; other subjects are
unaffected.

### CBOM scanner

```bash
python cbom/cbom_scan.py --endpoint example.org:443 --probe-pq -o cbom.json
python cbom/cbom_scan.py --cert-dir /etc/ssl/private-ca -o certs-cbom.json
./cbom/run_local_demo.sh    # reproduces cbom/sample-output/ against local openssl s_server instances
```

Captures protocol, cipher suite, negotiated group (for example `X25519MLKEM768`), handshake signature
scheme, and certificate signature algorithm and key. `--probe-pq` repeats the handshake offering only
`X25519MLKEM768` to test support. Output validates against the official CycloneDX 1.6 schema; see
`cbom/validate_cbom.py` for how to fetch the schema and check.

Only scan endpoints you own or are authorized to test.

### Terraform modules

Each module takes a `datasets` map whose values carry the tag schema. Validation blocks reject values
outside the schema. The protection profile decides the encryption:

| Profile | AWS | Azure | Google Cloud | OCI |
|---|---|---|---|---|
| pp1 | SSE-S3 | Microsoft-managed keys | Google default encryption | Oracle-managed keys |
| pp2 | SSE-KMS, domain KMS key, Bucket Keys | CMK (RSA-HSM, Key Vault Premium) | CMEK, HSM protection level | Vault key, HSM protection mode |
| pp3 | pp2, optional CloudHSM or XKS key store, SSE-KMS header required | pp2 plus infrastructure encryption | pp2 plus versioning | pp2 in a virtual private vault, versioning |

All keys rotate automatically and have a deletion window or soft-delete period. Admin and user
permissions are separate. Provider versions are pinned in each `versions.tf`.

```bash
cd terraform/aws && terraform init -backend=false && terraform validate
```

`terraform/aws/examples/offline-plan` and `examples/noncompliant-plan` plan without an AWS account
(placeholder credentials, all AWS calls skipped) to produce the plan JSON used by the OPA tests. Never
run `terraform apply` in those directories.

### Guardrails

```bash
cd policy/opa && opa test . -v
opa eval -d data_protection.rego -i fixtures/aws_noncompliant/plan.json data.terraform.data_protection.deny
```

Notes on the cloud guardrails:

- `deny-s3-put-without-sse-kms.json` denies any `PutObject` that does not send the
  `x-amz-server-side-encryption` header with `aws:kms` or `aws:kms:dsse`. Uploads that rely on bucket
  default encryption without the header are also denied, so clients must send the header.
- `deny-rds-unencrypted.json` denies create calls that set `StorageEncrypted` to false. It does not
  deny calls that omit the parameter; pair it with an AWS Config rule for detection.
- `require-data-classification-tag.json` covers services whose create calls accept request tags.
  S3 buckets are covered by the OPA policy and AWS Config instead.
- Azure definitions start in `Audit` where existing resources need remediation, then move to `Deny`.
- Replace `ORG_ID`, `FOLDER_ID`, and `KMS_PROJECT_ID` in the Google Cloud policy files before use.
