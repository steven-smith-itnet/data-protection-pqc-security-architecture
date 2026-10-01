---
title: "PQC migration: data, payments, devices, and testing"
parent: PQC migration program
grand_parent: "Phase 6: Post-quantum cryptography"
nav_order: 2
description: "Steps 8 to 12 of the PQC migration: key wrapping for stored data, payment dependencies, property hardware, testing, and success metrics."
---

# PQC migration: data, payments, devices, and testing
{: .no_toc }

**Phase 6: Post-quantum cryptography.** Steps 8 to 12 of the migration: stored data and key wrapping, payment ecosystem dependencies, long-lived property hardware, testing, and how success is measured.
{: .fs-5 .fw-300 }

## On this page
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Step 8: Databases, backups, and key wrapping

**What:** Confirm which at-rest protections are already quantum-safe and fix the ones that are not.

The rule: **symmetric encryption at rest is fine; asymmetric wrapping of the symmetric key is not.** If a data key is wrapped with RSA and the wrapped key travels with the data (in a backup file, a database file, or an exported object), an adversary who steals the files now and obtains a CRQC later can recover the RSA private key from the public key, unwrap the DEK, and decrypt. This is harvest now, decrypt later applied to stored data.

| System | Typical design | Quantum exposure | Action |
|---|---|---|---|
| Cloud KMS envelope encryption (AWS KMS symmetric keys, Cloud KMS, Azure Key Vault with AES wrap) | AES-256 DEK wrapped by an AES-256 KMS key | None at rest; the KMS API call is protected by TLS | Ensure SDK and endpoint use hybrid PQ TLS where available |
| Azure SQL and SQL Managed Instance TDE with customer-managed key | DEK wrapped by an RSA key (TDE protector) in Key Vault or Managed HSM | DEK wrap is RSA | Track provider roadmap for a PQC or symmetric protector; limit backup exposure; P2 |
| SQL Server on-prem TDE and backup encryption | DEK protected by a certificate (RSA) or an asymmetric key via EKM | RSA | Plan migration with Microsoft's roadmap; protect backups with an additional symmetric layer (for example, storage-level encryption with a separate AES key) |
| Oracle TDE | Master encryption key (AES) in wallet or Oracle Key Vault | Master key symmetric; check wallet protection and OKV transport | Low; verify OKV TLS support |
| Backup products | Varies: some protect backup keys with RSA key pairs | Possibly RSA | Ask via questionnaire (question 14) |
| BYOK key import into cloud KMS | Key material wrapped with an RSA-OAEP wrapping key from the provider for transport | Captured import traffic exposes key material | Prefer generating keys in the provider HSM; track provider support for PQC import wrapping (verify) |
| S/MIME and some file encryption tools | Content key wrapped with recipient's RSA key | RSA | Label-based encryption (Purview) uses service-side symmetric keys; review DKE design |
| Application-layer field encryption (AWS Encryption SDK, Database Encryption SDK) | AES DEKs wrapped by KMS symmetric keys, or raw RSA keyrings | Only with RSA keyrings | Replace raw RSA keyrings with KMS or AES keyrings |

The repository's envelope implementation ([code/envelope](https://github.com/steven-smith-itnet/data-protection-pqc-security-architecture/tree/main/code/envelope)) uses symmetric KEKs. The algorithm identifier recorded in each envelope header lets a later re-wrap change the KEK algorithm without touching data, as described in [Crypto agility and hybrid designs]({% link docs/06-pqc/crypto-agility.md %}#algorithm-agile-envelope-header).

Re-wrapping is cheap with envelope encryption because only the wrapped DEK changes; the bulk data is not re-encrypted. Plan re-wrap jobs per key hierarchy, record progress in the CBOM, and verify with sampling.

## Step 9: Payment ecosystem dependencies

The organization does not control most of the cryptography in the card payment chain. It does control where it sends card data and which vendors it chooses.

| Component | Cryptography | Who controls it | Organization action |
|---|---|---|---|
| P2PE terminals at front desk, restaurants, spa | Symmetric (DUKPT, AES or TDES) for PAN and PIN encryption | P2PE solution provider | Confirm AES DUKPT; quantum impact is low for symmetric schemes |
| Terminal remote key loading | Often ANSI X9 TR-34, which uses RSA to distribute keys to terminals | Solution provider, payment HSM | Ask provider for its PQC plan for remote key loading (verify industry status) |
| Payment gateway and tokenization APIs | TLS | Gateway | Require hybrid TLS support via questionnaire; enable hybrid in the organization's outbound clients |
| Hosted payment pages and iframes | TLS from guest browser to provider | Provider | Provider's CDN determines hybrid support |
| Network tokens and card-on-file | Card network cryptography | Card networks | Monitor; out of the organization's control |
| EMV card authentication | RSA-based offline authentication on chip cards | Issuers and card networks | Out of scope; industry roadmap |
| Payment HSMs (Azure Payment HSM, AWS Payment Cryptography, on-prem) | Symmetric for PIN and card data; RSA for some key exchange | Organization or provider | Track vendor firmware roadmap |

PCI DSS v4.0.1 requirement **12.3.3** requires documenting cipher suites and protocols in use and having a plan to respond to anticipated changes in cryptographic vulnerabilities, reviewed at least every 12 months. The PQC plan for the cardholder data environment is maintained as part of that annual review. See [Payment card data and PCI DSS]({% link docs/03-structured/payment-data-pci.md %}).

{: .verify }
The PCI Security Standards Council and ANSI X9 have discussed quantum readiness. Check for current PCI guidance on post-quantum cryptography before the annual 12.3.3 review.

## Step 10: IoT, door locks, and property hardware

Property hardware has the longest service lives in the estate and the least cryptographic flexibility. It also spans owned, managed, and franchised properties, which means the organization often sets standards rather than owning the hardware.

| Device class | Typical lifetime | Crypto concern | Action |
|---|---|---|---|
| Guest room door locks and encoders | 10 to 15 years | Firmware signature verification key; mobile key BLE protocol (often ECC) | PQC or hash-based firmware signing and updatable root of trust in RFP requirements now; mobile key protocol roadmap from lock vendor |
| Building management systems (HVAC, lighting) | 15 years or more | Firmware signing; BACnet Secure Connect uses TLS | Require vendor roadmap; segment networks |
| CCTV and NVRs | 7 to 10 years | Firmware signing; TLS to VMS | Replace in refresh cycle with PQC-capable models |
| POS terminals and kitchen displays | 5 to 7 years | Terminal OS TLS; vendor-controlled | Normal refresh with questionnaire |
| Guest Wi-Fi controllers and access points | 5 to 7 years | Management plane TLS, RADIUS | Vendor firmware updates |
| Kiosks and digital key issuance | 5 years | TLS to cloud | Normal refresh |

Mitigations when devices cannot be upgraded before 2035:

- **Network segmentation** so that device management traffic does not cross untrusted networks.
- **Gateway termination:** terminate device protocols at a property gateway and carry traffic to the cloud over hybrid PQ TLS or VPN.
- **Exception register entry** with a named owner, replacement date, and compensating controls.
- **Brand standards for franchised properties:** add PQC-capable firmware requirements to the brand technology standards so that franchisee purchases converge.

## Step 11: Testing

PQC changes message sizes and CPU cost. Test before enabling at scale.

| Test | What to look for | How |
|---|---|---|
| Handshake success | Hybrid negotiated with supported clients; classical fallback with others | `openssl s_client -groups`, `curl --curves`, synthetic monitors |
| ClientHello size and middleboxes | The hybrid ClientHello is about 1.4 KB (lab: 1,415 bytes vs 239 bytes classical) and, with other extensions, may exceed one TCP segment. Some middleboxes, firewalls, and IDS/IPS that expect the ClientHello in a single packet drop or mishandle it | Test through every proxy, firewall, WAF, and TLS inspection device in the path; check for connection resets and timeouts |
| HelloRetryRequest cost | Clients that send only a hybrid key share to a classical server incur an extra round trip | Lab step 6 fallback case shows the extra ClientHello and ServerHello |
| Server CPU | ML-KEM is fast (lab: roughly 20,000 to 30,000 operations per second per core for ML-KEM-768), but the hybrid adds work to every handshake | Load test at peak handshake rate; watch CPU on load balancers |
| Certificate chain size (for signature migration) | ML-DSA-65 certificate 5,620 bytes vs 482 for ECDSA in the lab; chains may exceed initial congestion windows and some device buffers | Test with ML-DSA chains in a lab before any pilot |
| TLS inspection | Inspection proxies must support the hybrid group or they force classical key exchange, removing the protection | Inventory inspection points; get vendor dates |
| Client compatibility | Old Java, .NET, embedded clients | Synthetic tests from each client platform |
| Monitoring | Logs and metrics record the negotiated group | Add negotiated group to access logs (for example, NGINX `$ssl_curve` if supported by the build; verify) |

{: .warning }
TLS inspection devices that do not support the hybrid group will negotiate classical key exchange with the client and with the server. The connection works, so the failure is silent. Record inspection points in the CBOM and treat them as hybrid blockers.

## Step 12: Success metrics

| Metric | Definition | Target |
|---|---|---|
| CBOM coverage | Percentage of C2/C3 systems with complete crypto records | 100% by end of 2027 |
| Edge hybrid coverage | Percentage of internet-facing hostnames that negotiate `X25519MLKEM768` | 90% by end of 2027 |
| Hybrid traffic share | Percentage of external TLS handshakes using a hybrid group (from edge logs) | Tracks client adoption; report trend |
| Internal hybrid coverage | Percentage of service mesh and internal TLS endpoints offering hybrid | 80% by 2029 |
| RSA-wrapped C3 keys | Count of C3 DEKs or protectors wrapped only by RSA or ECC | Zero by 2030 |
| Vendor readiness | Percentage of P1/P2 vendors with a committed PQC date | 100% by 2028 |
| Long-lived roots | Percentage of roots of trust with lifetime past 2035 that are PQC or hash-based | 100% by 2031 |
| 112-bit algorithms | Count of RSA-2048 and P-256 uses in C2/C3 scope | Zero by 2030 or on the exception register |
| Exceptions | Open PQC exceptions past target date | Trending to zero by 2035 |

Metrics feed the program dashboard described in [Metrics and KPIs]({% link docs/09-govern/metrics-kpis.md %}).

## Related pages

- [PQC migration program]({% link docs/06-pqc/migration-program.md %})
- [PQC migration: transport and PKI]({% link docs/06-pqc/migration/transport-and-pki.md %})
- [Vendor and cloud PQC readiness]({% link docs/06-pqc/provider-readiness.md %})
- [Payment card data and PCI DSS]({% link docs/03-structured/payment-data-pci.md %})
- [Key management architecture]({% link docs/02-standards/key-management.md %})
