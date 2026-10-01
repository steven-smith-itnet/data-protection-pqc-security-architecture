---
title: Phased roadmap
nav_order: 3
description: "The program plan: eight phases from mobilization to post-quantum completion, with activities, deliverables, entry and exit criteria, dependencies, risks, and owners."
has_children: true
---

# Phased roadmap
{: .no_toc }

**Phases 0 to 7: the full program.** This page sequences the data protection and post-quantum program so that knowing the data comes before protecting it, and every control deployment has a measurable entry and exit gate.
{: .fs-5 .fw-300 }

## On this page
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## How to read this roadmap

The roadmap is organized as eight phases (0 to 7). The phases overlap on purpose. A global hospitality organization cannot wait for a complete, perfect data inventory before it encrypts anything, and it cannot wait for every system to be protected before it starts post-quantum planning. The rule the roadmap enforces is narrower: **a control that depends on knowing the data (a label, a classification, an owner, a data flow) is not deployed to a scope until that scope has passed the Phase 1 exit gate.** Controls that do not depend on classification, such as platform default encryption at rest, TLS 1.2 minimums, and secrets scanning, start in Phase 0 as quick wins.

Timings are indicative. "Month 0" is the date the program charter is signed. The Gantt chart uses an illustrative start date of January 2027 so the bars render; replace it with the real start date.

| Phase | Name | Indicative timing | Focus |
|---|---|---|---|
| 0 | Mobilize | Months 0 to 3 | Charter, sponsors, objectives, scope, current-state assessment |
| 1 | Know the data | Months 1 to 9 | Data asset inventory, discovery, classification, labeling/metadata, ownership, data flows, cryptographic inventory (CBOM) |
| 2 | Standards and keys | Months 3 to 12 | Crypto standard, key management architecture, HSM, key custody, PKI, secrets, guardrails |
| 3 | Structured data | Months 6 to 24 | Databases, warehouses, lakes: TDE, field-level encryption, tokenization, FPE, masking, PCI |
| 4 | Unstructured data | Months 6 to 24 | Files, SharePoint/OneDrive, object storage, email, backups, logs, media: labels, persistent encryption, DLP |
| 5 | Transit and in use | Months 9 to 24 | TLS 1.3, mTLS, service mesh, confidential computing, retention, crypto-shredding |
| 6 | Post-quantum cryptography | Month 6 onward, to 2035 | Hybrid PQ TLS first, then high-value signing and long-lived data, completion by 2035 |
| 7 | Engineering enablement and governance | Continuous | Design review, patterns, paved roads, policy as code, metrics |

## Program timeline

```mermaid
gantt
    title Data protection and PQC program (illustrative start January 2027)
    dateFormat YYYY-MM-DD
    axisFormat %Y-%m
    section Phase 0
    Mobilize                          :p0, 2027-01-01, 2027-04-01
    section Phase 1
    Inventory and discovery           :p1a, 2027-02-01, 2027-07-01
    Classification and labeling       :p1b, 2027-03-01, 2027-10-01
    Crypto inventory (CBOM)           :p1c, 2027-03-01, 2027-10-01
    section Phase 2
    Crypto standard and key architecture :p2a, 2027-04-01, 2027-10-01
    HSM, PKI, secrets, guardrails     :p2b, 2027-06-01, 2028-01-01
    section Phase 3
    Structured data wave 1 (PCI, guest) :p3a, 2027-07-01, 2028-04-01
    Structured data wave 2 (analytics, HR) :p3b, 2028-01-01, 2029-01-01
    section Phase 4
    M365 labels and DLP               :p4a, 2027-07-01, 2028-07-01
    Object storage, backups, logs     :p4b, 2027-10-01, 2029-01-01
    section Phase 5
    TLS 1.3, mTLS, service mesh       :p5a, 2027-10-01, 2028-10-01
    Confidential computing, crypto-shredding :p5b, 2028-04-01, 2029-01-01
    section Phase 6
    PQC planning and hybrid TLS       :p6a, 2027-07-01, 2029-01-01
    Signing, long-lived data (continues to 2035) :p6b, 2029-01-01, 2030-12-31
    section Phase 7
    Engineering enablement and governance :p7, 2027-01-01, 2030-12-31
```

The chart stops at 2030 for readability. Phase 6 continues to 2035, and Phase 7 is permanent.

## Dependency model: inventory and classification gate control deployment

The most common failure in data protection programs is deploying controls to data nobody has classified. The result is either over-protection (external keys on a lunch-menu bucket, with the availability risk that brings) or under-protection (payment data sitting in a C1 file share because the share was never scanned). The dependency diagram below is the rule set the program office uses to schedule work.

```mermaid
flowchart LR
    A["Phase 0<br/>Charter and scope"] --> B["Data asset inventory"]
    B --> C["Discovery scans<br/>(Macie, Purview, SDP, Data Safe)"]
    C --> D["Classification C0 to C3"]
    D --> E["Labels and tags<br/>(data-classification, protection-profile)"]
    D --> F["Owners and data flows"]
    A --> G["Crypto inventory (CBOM)"]
    H["Phase 2<br/>Crypto standard and key architecture"] --> I["Key hierarchy and KMS/HSM"]
    E --> J{"Scope passed<br/>Phase 1 gate?"}
    F --> J
    I --> J
    J -- yes --> K["Phase 3 and 4<br/>PP-2 and PP-3 controls"]
    J -- no --> L["PP-1 baseline only<br/>(quick wins)"]
    G --> M["Phase 6<br/>PQC prioritization"]
    F --> M
    K --> N["Phase 7<br/>Guardrails enforce tags"]
    E --> N
```

| Dependency | Why it gates | What happens without it |
|---|---|---|
| Inventory before discovery | Scanners need a target list and credentials | Scans miss shadow data stores; coverage metric is meaningless |
| Classification before PP-2/PP-3 | The protection profile is derived from the tier | Keys and controls are chosen by guesswork |
| Tags before guardrails | Policy as code keys off `data-classification` and `protection-profile` | Guardrails either block everything or nothing |
| Owners before field-level encryption | Someone must approve the change to application code and accept the search/join trade-off | Engineering teams refuse the change or it stalls |
| Data flows before transit controls | mTLS and hybrid PQ TLS are prioritized by the flows that carry C2/C3 data | Effort goes to low-value internal hops |
| Crypto standard before key deployment | Algorithms, key sizes, and cryptoperiods must be fixed first | Keys are created inconsistently and must be rebuilt |
| CBOM before PQC migration | You cannot migrate what you have not found | PQC effort targets the visible endpoints only |

## Phase detail

The workstreams, step-by-step activities, deliverables, entry and exit criteria, dependencies, risks, and owners for each phase are on three sub-pages:

| Page | Phases |
|:--|:--|
| [Roadmap: phases 0 to 2]({% link docs/roadmap/phases-0-2.md %}) | 0 Mobilize, 1 Know the data, 2 Standards and keys |
| [Roadmap: phases 3 to 5]({% link docs/roadmap/phases-3-5.md %}) | 3 Structured data, 4 Unstructured data, 5 Transit and in use |
| [Roadmap: phases 6 and 7]({% link docs/roadmap/phases-6-7.md %}) | 6 Post-quantum cryptography, 7 Engineering enablement and governance |

## First 90 days for the architect

| Days | Focus | Concrete outputs |
|---|---|---|
| 1 to 30 | Listen and map | 25 to 30 stakeholder interviews; list of top 20 systems by sensitivity; review of PCI scope and existing key management; draft classification scheme |
| 31 to 60 | Decide and start | Charter drafted; current-state heat map; guardrails in audit mode in all clouds; design review intake live; first discovery scans on PMS integration stores, CRM, and the data lake |
| 61 to 90 | Commit and deliver | Steering committee approval; crypto standard draft; key hierarchy design; first paved-road module; first CBOM of external endpoints; quick-win report |

## Quick wins

These do not depend on classification and deliver measurable risk reduction in the first quarter.

| Quick win | Effort | Risk reduced |
|---|---|---|
| Enable default encryption and block public access on all object storage | Low | Accidental exposure of guest files |
| Enforce TLS 1.2 minimum on storage accounts, load balancers, and databases | Low | Downgrade and weak cipher exposure |
| Secret scanning in all repositories with push protection | Low | Credentials in code |
| Alert on KMS key disable or scheduled deletion | Low | Destructive or ransomware-style key actions |
| Turn on S3 Bucket Keys for SSE-KMS buckets | Low | KMS cost, which unlocks broader CMK adoption |
| Certificate expiry monitoring for public endpoints | Low | Outages as lifetimes shorten |
| Stop storing ID scans in shared mailboxes and file shares at properties | Medium | Passport data sprawl |

## Maturity progression: Good, better, best over time

```mermaid
flowchart LR
    G["Good (PP-1)<br/>Months 0 to 6<br/>Default encryption, TLS 1.2+,<br/>audit logging, guardrails in audit"] --> B["Better (PP-2)<br/>Months 6 to 18<br/>CMK per domain, TDE with CMK,<br/>masking, DLP monitor then block,<br/>hybrid PQ TLS on edge"]
    B --> T["Best (PP-3) for C3<br/>Months 12 to 30<br/>Field-level encryption, tokenization,<br/>HSM or external keys where justified,<br/>mTLS, crypto-shredding, PQC priority"]
```

| Dimension | Good | Better | Best |
|---|---|---|---|
| Keys | Provider-managed | Customer-managed per domain and environment | Single-tenant HSM or external keys for justified C3 |
| Structured data | Platform encryption at rest | TDE with CMK, dynamic masking | Field-level encryption or tokenization in the app |
| Unstructured data | Default storage encryption | Labels, auto-labeling, DLP monitor | Label-based persistent encryption, DLP block, DKE where justified |
| Transit | TLS 1.2+ | TLS 1.3 preferred, hybrid PQ on edge | mTLS, hybrid PQ internally |
| Governance | Audit mode guardrails | Deny guardrails keyed on tags | Continuous metrics, automated exceptions expiry |
| PQC | Inventory | Hybrid key exchange on external endpoints | PQC signing for roots of trust, long-lived data re-encryption |

Best is not the goal for every asset. External keys add availability risk and cost; field-level encryption breaks search and joins. The profile follows the classification, not ambition.

## Key takeaways for engineering teams

- Classification gates control selection: expect the design review to ask for your data's tier and tags before discussing encryption.
- Baseline controls (default encryption, TLS 1.2+, secrets out of code) apply now and do not wait for the program.
- C3 data will need application-layer protection; plan the search and join trade-offs early.
- Guardrails move from audit to deny in stages; use the paved-road modules to stay ahead of them.
- New designs must be crypto-agile so the PQC migration is a configuration change, not a rewrite.

## Related pages

- [Business objectives]({% link docs/00-start/objectives.md %})
- [Phase 1: Know the data]({% link docs/01-prerequisites/index.md %})
- [Phase 2: Standards and keys]({% link docs/02-standards/index.md %})
- [PQC migration program]({% link docs/06-pqc/migration-program.md %})
- [Phase 7: Engineering enablement]({% link docs/08-engineering/index.md %})
- [Metrics and KPIs]({% link docs/09-govern/metrics-kpis.md %})
