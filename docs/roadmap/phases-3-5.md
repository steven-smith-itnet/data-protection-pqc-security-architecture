---
title: "Roadmap: phases 3 to 5"
parent: Phased roadmap
nav_order: 2
description: "Structured data, unstructured data, and transit and in use: workstreams, activities, deliverables, entry and exit criteria."
---

# Roadmap: phases 3 to 5
{: .no_toc }

**Phases 3 to 5.** Apply the protection profiles to structured data, unstructured data, and data in transit and in use.
{: .fs-5 .fw-300 }

## On this page
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Phase 3: Structured data (months 6 to 24)

### Objectives

Apply PP-2 and PP-3 controls to databases, warehouses, and lakes in priority order: payment data first, then guest identity data, then guest profile and loyalty, then HR and finance.

### Workstreams

| Workstream | Lead | Output |
|---|---|---|
| PCI scope reduction | Payments engineering | Updated cardholder data environment (CDE) diagram |
| Database encryption baseline | Database platform team | TDE with CMK evidence per database |
| Application-layer protection | Application teams with security architecture | Field-level encryption and tokenization integrations |
| Analytics protection | Data platform team | Label-driven masking and column security |
| Non-production data | Test data management | Masked or synthetic datasets |

### Step-by-step activities

1. Reduce PCI scope before encrypting: confirm P2PE at properties, hosted payment pages for web booking, and gateway tokens for card-on-file. Remove stored PAN where a token will do.
2. Enable TDE with customer-managed keys on every C2 and C3 database (PP-2 baseline).
3. Apply dynamic masking for non-privileged roles on C2 columns.
4. For C3 fields (passport number, national ID, bank account, health and accessibility data), implement field-level encryption or tokenization in the application tier using the paved-road libraries.
5. Implement keyed hashes or deterministic tokens where equality search or joins are required, and document the trade-off.
6. Label warehouse columns (BigQuery policy tags, Snowflake or Databricks tags, Purview classifications) and enforce masking policies from labels.
7. Migrate non-production environments to synthetic or masked data.

### Deliverables

Encrypted and masked data stores with evidence; tokenization service; per-application encryption design records; updated PCI scope documentation.

### Entry criteria

Scope passed the Phase 1 gate; keys available from Phase 2.

### Exit criteria

100 percent CMK coverage on C2/C3 databases; field-level protection on all C3 fields in wave 1 systems; no production C3 data in non-production.

### Dependencies

Application release schedules; vendor support for PMS and POS encryption options; tokenization service capacity.

### Key risks

Search and join breakage from field-level encryption; performance regressions; vendor-hosted systems where the organization cannot control encryption. Mitigation: design review, deterministic options where justified, and contractual controls for SaaS.

### Owners

Application teams (responsible), security architecture (accountable for patterns), data owners (approve trade-offs).

## Phase 4: Unstructured data (months 6 to 24)

### Objectives

Protect files, collaboration content, object storage, email, backups, logs, and media with labels, persistent encryption, and DLP.

### Workstreams

| Workstream | Lead | Output |
|---|---|---|
| Microsoft 365 labeling | Microsoft 365 platform team | Label policies and auto-labeling rules |
| DLP and CASB | Security operations | Tuned DLP policy set |
| On-prem files | Infrastructure team | Scanned and remediated shares |
| Object storage | Cloud platform teams | CMK-enforced buckets and containers |
| Backups, logs, media | Backup, observability, and CCTV owners | Key separation, redaction, retention |

### Step-by-step activities

1. Publish sensitivity labels to all users with recommended labeling; enable auto-labeling for `Restricted\PCI` and `Restricted\Guest-Identity` patterns in SharePoint, OneDrive, and Exchange.
2. Configure labels with encryption for Restricted labels; evaluate DKE only for the narrow set of content that justifies it.
3. Run DLP policies in monitor mode for 30 to 60 days, tune, then move to block for C3.
4. Scan on-prem file shares with the Purview Information Protection scanner or an equivalent tool and move ID scans to the approved retention store.
5. Enforce SSE-KMS, CMK, or CMEK on object storage by tag, with bucket-level default encryption and S3 Bucket Keys for cost control.
6. Encrypt backups with separate keys from production and verify restore.
7. Remove PII from logs at the source; apply log redaction and short retention.

### Deliverables

Label policies, auto-labeling rules, DLP policy set, object storage guardrails, backup key design, log hygiene standard.

### Entry criteria

Label taxonomy approved (Phase 1); Microsoft 365 licensing confirmed for auto-labeling and DLP; object storage keys available (Phase 2).

### Exit criteria

Auto-labeling active for C3 patterns; DLP in block for C3 exfiltration channels; all C2/C3 buckets on customer-managed keys.

### Dependencies

Phase 1 discovery of file shares and SharePoint sites; eDiscovery and legal hold configuration; service desk readiness for user questions.

### Key risks

Encrypted labels break workflows (search, eDiscovery, third-party apps); DLP false positives disrupt front-desk operations. Mitigation: pilot groups, super-user configuration for eDiscovery, staged enforcement.

### Owners

Microsoft 365 platform team and storage platform teams (responsible), data governance (accountable for labels), security operations (DLP triage).

## Phase 5: Transit and in use (months 9 to 24)

### Objectives

Enforce TLS 1.2 minimum and TLS 1.3 preference everywhere; implement mTLS for service-to-service C2/C3 traffic; adopt confidential computing where it reduces risk; build retention-driven deletion and crypto-shredding.

### Workstreams

| Workstream | Lead | Output |
|---|---|---|
| TLS hygiene | Network and platform engineering | Remediated endpoints |
| Service mesh and mTLS | Kubernetes platform team | Strict mTLS in in-scope namespaces |
| Property connectivity | Property technology | TLS 1.3 PMS and POS integrations |
| Confidential computing | Security architecture | Evaluation and pilot |
| Retention and crypto-shredding | Data platform with privacy | Deletion service and evidence |

### Step-by-step activities

1. Scan all endpoints (from the CBOM) and remediate TLS below 1.2 and weak cipher suites.
2. Deploy a service mesh with mTLS (strict mode) for Kubernetes workloads processing C2/C3 data.
3. Replace property-to-cloud VPN-only links with TLS 1.3 connections, with hybrid PQ key exchange where both ends support it.
4. Evaluate confidential VMs or enclaves for tokenization, key-handling services, and analytics on C3 data.
5. Implement per-subject or per-tenant keys where crypto-shredding is the chosen deletion method, and connect deletion to retention schedules.

### Deliverables

TLS remediation report; mesh configuration and policy; confidential computing decision record; crypto-shredding design and test evidence.

### Entry criteria

CBOM for internal endpoints (Phase 1); data flow maps for C2/C3 flows; PKI capable of issuing workload certificates at scale (Phase 2).

### Exit criteria

No TLS below 1.2 on C2/C3 paths; mTLS strict for in-scope namespaces; crypto-shredding tested end to end for at least one guest data domain.

### Dependencies

Legacy property systems and vendor appliances that cannot run TLS 1.3; retention schedules approved by legal.

### Key risks

| Risk | Mitigation |
|---|---|
| mTLS strict mode breaks legacy clients | Permissive mode first, telemetry on plaintext connections |
| Crypto-shredding destroys data under legal hold | Deletion service checks the `retention-class` and legal hold flags before destroying a key |
| Confidential computing adds cost without clear risk reduction | Use only where the threat model includes privileged cloud or host operators |

### Owners

Platform engineering and network engineering (responsible), security architecture (accountable).

## Related pages

- [Phased roadmap]({% link docs/roadmap.md %})
- [Roadmap: phases 0 to 2]({% link docs/roadmap/phases-0-2.md %})
- [Roadmap: phases 6 and 7]({% link docs/roadmap/phases-6-7.md %})
- [Phase 3: Structured data]({% link docs/03-structured/index.md %})
- [Phase 4: Unstructured data]({% link docs/04-unstructured/index.md %})
- [Phase 5: Transit and in use]({% link docs/05-transit-in-use/index.md %})
