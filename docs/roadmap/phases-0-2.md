---
title: "Roadmap: phases 0 to 2"
parent: Phased roadmap
nav_order: 1
description: "Mobilize, know the data, and standards and keys: workstreams, activities, deliverables, entry and exit criteria."
---

# Roadmap: phases 0 to 2
{: .no_toc }

**Phases 0 to 2.** Mobilize the program, find and label the data, and set the cryptographic standard and key foundation that every later phase depends on.
{: .fs-5 .fw-300 }

## On this page
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Phase 0: Mobilize (months 0 to 3)

### Objectives

- Secure an executive sponsor (CISO) and co-sponsors (CIO, CDO or head of data governance, Chief Privacy Officer).
- Agree the program's business objectives, scope, and success measures.
- Produce a current-state assessment that is honest about gaps.
- Start quick wins that do not depend on classification.

### Workstreams

| Workstream | Lead | Output |
|---|---|---|
| Governance setup | Security architecture | Charter, steering committee, RACI |
| Current-state assessment | Security architecture with platform engineering | Assessment report and heat map |
| Regulatory baseline | Privacy and compliance | Obligations register (PCI DSS v4.0.1, GDPR, CCPA/CPRA, PIPL, LGPD, DPDP) |
| Quick wins | Platform engineering | Baseline guardrails in audit mode |

### Step-by-step activities

1. Draft the program charter: problem statement, scope (owned, managed, and franchised properties; which cloud accounts, subscriptions, projects, and tenancies), out-of-scope items, and decision rights.
2. Run stakeholder interviews: guest platform, loyalty, payments, property technology, data and analytics, HR, finance, franchise operations, legal, and privacy. Record where each team believes its sensitive data lives.
3. Collect existing artifacts: PCI Report on Compliance and scope diagrams, records of processing activities (GDPR Article 30), cloud account lists, CMDB exports, key management procedures, and any prior DLP deployment.
4. Assess current state against the protection profiles (PP-1, PP-2, PP-3) at a coarse level: which platforms have default encryption, which use customer-managed keys, where TLS versions are below 1.2, where secrets live in code.
5. Enable read-only posture tooling across clouds (AWS Security Hub and Config, Microsoft Defender for Cloud, Google Security Command Center, OCI Cloud Guard) if not already in place.
6. Deploy baseline guardrails in audit or detective mode: deny unencrypted storage creation, require TLS 1.2 minimum, flag public buckets.
7. Stand up the architecture review intake (a simple form) so new projects start using the classification scheme immediately, even before the inventory is complete.
8. Present the charter, assessment, and 24-month plan to the steering committee for approval.

### Deliverables

- Program charter and steering committee terms of reference.
- Current-state assessment with heat map by data domain and platform.
- Obligations register.
- Approved classification scheme (draft, finalized in Phase 1).
- Guardrails in audit mode; baseline findings report.

### Entry criteria

- Sponsor identified and willing to chair a monthly steering committee.
- Budget line for tooling discovery (licenses may already exist in Microsoft 365 E5, cloud-native services).

### Exit criteria

- Charter signed; RACI approved.
- Assessment accepted by the steering committee.
- Phase 1 and Phase 2 plans resourced with named leads.

### Dependencies

- Access to cloud organization-level read roles.
- Legal and privacy availability for the obligations register.

### Key risks

| Risk | Mitigation |
|---|---|
| Scope creep into general security posture | Charter limits scope to data protection, cryptography, and key management |
| Franchise properties treated as in-scope for controls the organization cannot enforce | Define the shared-responsibility boundary explicitly in the charter |
| Assessment becomes a long audit | Time-box to eight weeks; accept coarse ratings |

### Owners

CISO (accountable), security architecture (responsible), privacy, data governance, and platform engineering (consulted).

## Phase 1: Know the data (months 1 to 9)

### Objectives

- Build a data asset inventory that covers every data store holding C2 or C3 data.
- Classify each asset against the four-tier scheme (C0 to C3) and apply labels or tags.
- Assign an accountable data owner to each asset and map the main data flows.
- Produce a cryptographic inventory (CBOM) that lists algorithms, key lengths, protocols, and certificates in use.

### Workstreams

| Workstream | Tools | Output |
|---|---|---|
| Inventory | CMDB, cloud asset inventories (AWS Config, Azure Resource Graph, Cloud Asset Inventory, OCI Search) | Data asset register |
| Discovery | Amazon Macie, Microsoft Purview Data Map and Information Protection scanner, Google Sensitive Data Protection, OCI Data Safe, third-party (BigID, Varonis, Cyera, Securiti) | Findings per store |
| Classification and labeling | Purview sensitivity labels, cloud tags and labels | Labeled assets |
| Ownership and flows | Data catalog (Purview, Dataplex, or equivalent) | Owner register, flow diagrams |
| Crypto inventory | TLS scanners, certificate inventory, code scanning, vendor questionnaires | CBOM (CycloneDX) |

### Step-by-step activities

1. Export all data stores from cloud asset inventories and the CMDB into a single register. Include databases, object storage, file shares, SaaS applications (PMS, CRS, CRM, HR/payroll), and backup targets.
2. Rank stores by likely sensitivity using system purpose. PMS, CRS, POS, payment gateway integration, loyalty, CRM, and HR are ranked first.
3. Run discovery scans on the first-ranked stores. Use sampling for large structured stores to control cost, and full scans for file shares that are likely to hold passport scans.
4. Review findings with data owners. Confirm or override the recommended tier. Record the reason for overrides.
5. Apply tags using the shared schema: `data-classification`, `protection-profile`, `data-domain`, `regulatory-scope`, `data-residency`, `data-owner`, `retention-class`.
6. Publish Purview sensitivity labels (`Public`, `Internal`, `Confidential\Guest-PII`, `Confidential\Employee`, `Confidential\Business`, `Restricted\PCI`, `Restricted\Guest-Identity`, `Restricted\Special-Category`, `Restricted\Secrets`) to pilot groups with default labeling off and recommended labeling on.
7. Map data flows for the top ten systems: reservation to PMS, PMS to data lake, POS to payment gateway, loyalty to CRM, property ID scanners to PMS, and franchise data exchanges.
8. Build the CBOM: scan external and internal TLS endpoints, export certificate inventories from public and private CAs, list KMS and HSM keys with algorithm and creation date, and send a cryptography questionnaire to the top 20 vendors.
9. Report classification coverage weekly to the steering committee.

### Deliverables

- Data asset register with tier, owner, and residency for each C2/C3 store.
- Label taxonomy published; tags applied to in-scope cloud resources.
- Data flow diagrams for priority systems.
- CBOM and a list of quantum-vulnerable assets.

### Entry criteria

- Classification scheme approved in draft (Phase 0).
- Scanner licenses and read access granted.

### Exit criteria (the Phase 1 gate, applied per scope)

- At least 95 percent of known data stores in the scope are in the register.
- Every C2/C3 store has a tier, an owner, and tags.
- Data flows for the scope are documented.
- CBOM exists for the scope's external endpoints.

### Dependencies

- Phase 0 approval; cooperation from data owners; privacy review of scanner configurations (scanners read personal data).

### Key risks

| Risk | Mitigation |
|---|---|
| Scanner cost on large stores | Sampling, incremental scans, prioritization by rank |
| False positives erode trust | Tune classifiers (Luhn validation for PAN, checksum validation for national IDs) |
| Owners refuse accountability | Steering committee assigns default owner by system |
| Scanners themselves become a data exposure | Scanner findings are C3; store with PP-3 controls |

### Owners

Data governance (accountable for classification), security architecture (responsible for tooling and CBOM), data owners (responsible for confirming tier).

## Phase 2: Standards and keys (months 3 to 12)

### Objectives

- Publish the cryptographic standard: approved algorithms, key sizes, modes, protocols, and cryptoperiods.
- Design the key management architecture: key hierarchy, KMS per cloud, HSM choices, custody options, and separation of duties.
- Establish PKI and certificate lifecycle automation ready for short certificate lifetimes.
- Consolidate secrets into approved secrets managers.
- Convert standards into guardrails (policy as code).

### Step-by-step activities

1. Draft the crypto standard aligned to NIST SP 800-57 Part 1 Rev. 5 and SP 800-131A. Approve AES-256-GCM for data at rest, TLS 1.2 minimum with TLS 1.3 preferred, and a plan for ML-KEM and ML-DSA (FIPS 203 and 204).
2. Define the key hierarchy: root keys in HSM, KEKs per data domain and environment in cloud KMS, DEKs per object or record.
3. Choose per-cloud KMS tiers by profile: provider-managed for PP-1, customer-managed keys (HSM-backed where offered) for PP-2, single-tenant HSM or external keys only where justified for PP-3.
4. Decide on a cross-cloud key manager (for example Thales CipherTrust, Fortanix DSM, Entrust KeyControl, or HashiCorp Vault) for on-prem and multi-cloud key lifecycle visibility.
5. Define key admin and key user roles in each cloud and assign them to separate groups.
6. Design PKI: private CA hierarchy, ACME automation for public certificates in response to CA/Browser Forum ballot SC-081 (200-day maximum from March 15, 2026, 100 days from March 15, 2027, 47 days from March 15, 2029).
7. Inventory secrets in code (secret scanning) and move them into AWS Secrets Manager, Azure Key Vault, Google Secret Manager, OCI Vault secrets, or HashiCorp Vault.
8. Write guardrails: SCPs, Azure Policy, GCP organization policies, OCI security zones, and OPA/Rego checks on Terraform plans. Move from audit to deny in stages.

### Deliverables

Crypto standard; key management architecture document; key custody decision records; PKI design; secrets standard; guardrail library with test evidence.

### Entry criteria

Phase 0 complete; draft classification scheme; CBOM work started.

### Exit criteria

Standard approved; KMS/HSM deployed per cloud with role separation; at least one paved-road Terraform module per cloud that creates a tagged key and encrypted storage; guardrails in deny mode for new resources in production.

### Dependencies

HSM procurement lead times (on-prem HSMs and single-tenant cloud HSMs can take one to two quarters to contract and deploy); identity platform readiness for role separation.

### Key risks

| Risk | Mitigation |
|---|---|
| External key custody chosen without availability planning | Require an availability design and a tested outage runbook before any external key store goes live |
| Guardrails break deployment pipelines | Audit mode first, exception process, staged rollout |
| Certificate outages as lifetimes shorten | ACME automation and expiry monitoring before March 2027 |

### Owners

Security architecture (accountable), platform engineering and PKI team (responsible), key custodians (consulted).

## Related pages

- [Phased roadmap]({% link docs/roadmap.md %}): timeline, dependency model, first 90 days
- [Roadmap: phases 3 to 5]({% link docs/roadmap/phases-3-5.md %})
- [Phase 1: Know the data]({% link docs/01-prerequisites/index.md %})
- [Phase 2: Standards and keys]({% link docs/02-standards/index.md %})
