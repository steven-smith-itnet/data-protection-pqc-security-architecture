---
title: "Roadmap: phases 6 and 7"
parent: Phased roadmap
nav_order: 3
description: "Post-quantum cryptography and engineering enablement and governance: workstreams, activities, deliverables, entry and exit criteria."
---

# Roadmap: phases 6 and 7
{: .no_toc }

**Phases 6 and 7.** Migrate to post-quantum cryptography by 2035, and run the continuous engineering enablement and governance that keeps the program in place.
{: .fs-5 .fw-300 }

## On this page
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Phase 6: Post-quantum cryptography (month 6 onward, to 2035)

### Objectives

Protect against harvest-now-decrypt-later risk by moving key exchange to hybrid post-quantum first, then migrate signatures for long-lived roots of trust, then complete migration by 2035 in line with NIST IR 8547 (initial public draft), NSA CNSA 2.0 for any national-security-adjacent obligations, the EU coordinated roadmap, and UK NCSC guidance.

### Workstreams

| Workstream | Lead | Output |
|---|---|---|
| Inventory and prioritization | Security architecture | Ranked quantum-vulnerable asset list |
| Edge and transit | Platform and network engineering | Hybrid PQ TLS on external endpoints |
| Signing and PKI | PKI team | PQC signing pilot and PKI migration plan |
| Vendors | Procurement and third-party risk | Contract clauses and roadmaps |
| Long-lived data | Data platform | Re-encryption plan for archives with shelf life past 2035 |

### Step-by-step activities

1. Use the CBOM to list quantum-vulnerable algorithms by system and rank systems with Mosca's inequality (data shelf life plus migration time compared with time to a cryptographically relevant quantum computer).
2. Enable `X25519MLKEM768` hybrid key exchange on external TLS endpoints where the load balancer or CDN supports it. Many browsers already offer it by default.
3. Require crypto agility in new designs: algorithm identifiers in ciphertext headers, configurable providers, no hard-coded curves.
4. Add PQC requirements to vendor contracts and questionnaires.
5. Pilot ML-DSA signing for internal code signing and firmware for property IoT where vendors support it; evaluate LMS/XMSS for firmware per SP 800-208.
6. Plan PKI migration: new PQC or composite roots once standards and client support mature.

{: .verify }
Cloud and vendor PQC capabilities change frequently. As of mid-2026, AWS KMS offers ML-DSA signing keys, Google Cloud KMS offers quantum-safe signatures, and Microsoft SymCrypt includes ML-KEM and ML-DSA. Confirm current status before committing a design.

### Deliverables

PQC migration plan; Mosca-ranked system list; vendor PQC readiness register; hybrid TLS rollout evidence; crypto-agility requirement in the design standard.

### Entry criteria

CBOM for external endpoints (Phase 1); crypto standard includes ML-KEM and ML-DSA (Phase 2).

### Exit criteria (by milestone)

| Milestone | Target |
|---|---|
| All external guest-facing TLS endpoints hybrid-PQ capable | 2028 |
| All new systems crypto-agile by design review gate | 2028 |
| High-value signing (code, firmware) on PQC or hybrid | 2030 |
| No RSA/ECC at 112-bit security in use | 2030 (per NIST IR 8547 draft deprecation) |
| All quantum-vulnerable public-key algorithms retired | 2035 |

### Dependencies

Library and platform support (OpenSSL 3.5 or later, AWS-LC, SymCrypt, BoringSSL); load balancer, CDN, and HSM vendor support; client support at properties and in partner systems.

### Key risks

| Risk | Mitigation |
|---|---|
| Middleboxes fail on larger TLS handshakes | Test through property firewalls and inspection proxies before enabling |
| HSM firmware lacks PQC algorithms | Include PQC in HSM refresh requirements |
| Standards still moving (FN-DSA, HQC) | Use only final FIPS 203, 204, and 205 algorithms in production |

### Owners

Security architecture (accountable), PKI, platform, and application teams (responsible), procurement (vendor clauses).

## Phase 7: Engineering enablement and governance (continuous)

### Objectives

Make the secure path the easy path: design review, reference architectures, decision trees, paved-road modules, policy as code, and metrics.

### Workstreams

| Workstream | Lead | Output |
|---|---|---|
| Design review | Security architecture | Security requirements packages |
| Patterns and paved roads | Security architecture with platform engineering | Reference architectures, modules, libraries |
| Policy as code | Platform engineering | Guardrail library and tests |
| Champions | Engineering leadership | Trained champion per team |
| Metrics | Governance | Monthly dashboard |

### Step-by-step activities

1. Run the security design review process with classification-based triage.
2. Publish reference architectures and decision trees.
3. Maintain paved-road Terraform modules and libraries.
4. Operate a security champions program in engineering teams.
5. Report metrics monthly to the steering committee and quarterly to the board.

### Deliverables

Design review process and SLAs; reference architectures; decision trees; paved-road modules; guardrail library; metrics dashboard.

### Entry and exit criteria

Phase 7 is continuous. It starts in Phase 0 with the intake form and never exits. It is measured by design review coverage (percentage of new C2/C3 projects reviewed before build), paved-road adoption, and guardrail exception counts.

### Dependencies and key risks

Depends on engineering leadership support and on security architecture capacity. The main risk is that review becomes a bottleneck; mitigation is classification-based triage, self-service for C0/C1, and published patterns that remove the need for a bespoke review.

### Owners

Security architecture (accountable), engineering leads (responsible for adoption), governance (metrics).

## Related pages

- [Phased roadmap]({% link docs/roadmap.md %})
- [Roadmap: phases 3 to 5]({% link docs/roadmap/phases-3-5.md %})
- [Phase 6: Post-quantum cryptography]({% link docs/06-pqc/index.md %})
- [Phase 7: Engineering enablement]({% link docs/08-engineering/index.md %})
- [Govern and measure]({% link docs/09-govern/index.md %})
