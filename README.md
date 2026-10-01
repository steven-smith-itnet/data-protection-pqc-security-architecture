# Data Protection and Post-Quantum Encryption Architecture

A phased reference architecture for protecting enterprise data in a global hospitality
organization: data inventory, classification, and labeling; encryption and key management for
structured and unstructured data on-prem and in AWS, Microsoft Azure, Google Cloud, and Oracle
Cloud Infrastructure; and the migration to post-quantum cryptography (PQC).

**Read the site: <https://steven-smith-itnet.github.io/data-protection-pqc-security-architecture/>**

**Executive briefing (slides): <https://steven-smith-itnet.github.io/data-protection-pqc-security-architecture/slides/>**

---

## What this covers

| Phase | Section | Contents |
|:--|:--|:--|
| 0 | Start here | Scenario, business objectives, threats and regulatory drivers, hospitality data landscape |
| All | Phased roadmap | Timeline, workstreams, deliverables, entry and exit criteria |
| 1 | Know the data | Data asset inventory and discovery, classification scheme, labeling and metadata, label-to-control mapping, data ownership and flows, cryptographic inventory (CBOM) |
| 2 | Standards and keys | Cryptographic standard, key management architecture, BYOK/HYOK/external keys, HSMs, PKI, secrets management |
| 3 | Structured data | Encryption layers, tokenization, FPE, masking, PCI DSS v4.0.1, on-prem databases, cloud databases, lakes and warehouses |
| 4 | Unstructured data | Persistent label-based encryption, Microsoft 365, file shares and NAS, object storage, email, backups, logs, media, DLP and CASB |
| 5 | Transit and in use | TLS 1.3, mTLS, confidential computing, retention and crypto-shredding |
| 6 | Post-quantum cryptography | Quantum threat, FIPS 203/204/205 and timelines, migration program, crypto agility, vendor readiness, OpenSSL 3.5 lab |
| Ref | Cloud provider playbooks | AWS, Azure, Google Cloud, OCI, and multi-cloud key management, each with Good, Better, Best options |
| 7 | Engineering enablement | Design review, decision trees, reference architectures, policy as code, code lab, cheat sheet |
| 7 | Govern and measure | Operating model and RACI, monitoring and detection, compliance mapping, metrics, risks |

## Protection profiles

| Profile | Rating | Data tier | Summary |
|:--|:--|:--|:--|
| PP-1 Baseline | Good | Public, Internal | Provider-managed keys, default encryption, TLS 1.2+, logging |
| PP-2 Enhanced | Better | Confidential | Customer-managed keys per domain, rotation, separation of duties, masking, DLP |
| PP-3 Maximum | Best | Restricted | Field-level encryption or tokenization, HSM or external keys where justified, persistent file encryption, mTLS, crypto-shredding, PQC priority |

## Code

The [`code/`](code/) directory holds working tools that implement the architecture. See
[`code/README.md`](code/README.md) for how to run each one.

| Path | What it does |
|:--|:--|
| [`code/discovery/`](code/discovery/) | Scanner for card numbers (Luhn), IBANs, and identity data; recommends tier, label, and profile |
| [`code/classification/`](code/classification/) | Machine-readable label-to-control policy and a resolver that turns tags into required controls |
| [`code/envelope/`](code/envelope/) | AES-256-GCM envelope encryption with an algorithm-agile header; AWS KMS, Azure Key Vault, and Google Cloud KMS adapters |
| [`code/tokenization/`](code/tokenization/) | Vault tokenization and keyed-hash surrogates |
| [`code/crypto-shredding/`](code/crypto-shredding/) | Per-subject data keys; erasure by key destruction |
| [`code/cbom/`](code/cbom/) | TLS and certificate scanner that emits a CycloneDX CBOM and flags quantum-vulnerable algorithms |
| [`code/pqc-lab/`](code/pqc-lab/) | OpenSSL 3.5 ML-KEM, ML-DSA, SLH-DSA, and hybrid `X25519MLKEM768` TLS, with captured output |
| [`code/terraform/`](code/terraform/) | Label-driven key and storage modules for AWS, Azure, Google Cloud, and OCI |
| [`code/policy/`](code/policy/) | SCPs, Azure Policy, GCP organization policies, and OPA/Rego with tests |

## Companion guides

- [AWS KMS and CloudHSM key management guide](https://github.com/steven-smith-itnet/aws-kms-cloudhsm-key-management-guide)
- [Azure Key Vault and Managed HSM key management guide](https://github.com/steven-smith-itnet/azure-key-vault-managed-hsm-key-management-guide)
- [Google Cloud KMS and Cloud HSM key management guide](https://github.com/steven-smith-itnet/gcp-cloud-kms-hsm-key-management-guide)

## Building locally

```bash
cd /home/ssmith/repos/data-protection-pqc-security-architecture
bundle install
bundle exec jekyll serve --host 127.0.0.1 --port 8002
```

Open <http://127.0.0.1:8002/data-protection-pqc-security-architecture/>. The
configured `baseurl` serves the site under that path, so opening
<http://127.0.0.1:8002/> returns `ERROR '/' not found`.

A missing `/favicon.ico` is a browser request for an optional tab icon and does
not prevent the site from loading. Sass deprecation warnings from Just the Docs
also do not indicate a failed build; `sass.quiet_deps` suppresses warnings from
the theme's dependencies. Restart Jekyll after changing `_config.yml`.

The site is built and deployed by [`.github/workflows/pages.yml`](.github/workflows/pages.yml) on
every push to `main`.

## Disclaimer

The organization described is a composite scenario and does not describe any real company.
This is an independent reference architecture based on public standards and vendor
documentation; it is not affiliated with or endorsed by any hospitality company, cloud provider,
or vendor. Cloud features and regulatory timelines change often; verify against current official
documentation before use.
