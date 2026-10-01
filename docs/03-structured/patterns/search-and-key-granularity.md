---
title: Search, joins, and key granularity
parent: Structured data protection patterns
grand_parent: "Phase 3: Structured data"
nav_order: 1
description: "Performance, search, join, and index effects of each encryption layer, searchable encryption options, and key granularity choices."
---

# Search, joins, and key granularity
{: .no_toc }

**Phase 3: Structured data.** What each protection layer costs in search, joins, indexing, and performance, the options for searching encrypted data, and how finely to divide keys.
{: .fs-5 .fw-300 }

## On this page
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Performance, search, join, and index implications

Moving up the stack increases protection and decreases what the database can do with the data.

| Layer | CPU and latency overhead | Equality search | Range and sort | LIKE and full text | Joins | Indexes | Schema changes |
|---|---|---|---|---|---|---|---|
| 1 to 3 (SED, volume, FS) | Negligible to low (AES-NI; CTE agent adds some I/O overhead) | Unaffected | Unaffected | Unaffected | Unaffected | Unaffected | None |
| 4 TDE | Low; vendor guidance is typically a few percent, higher for I/O-heavy workloads; backup compression may be affected on some older engine versions | Unaffected | Unaffected | Unaffected | Unaffected | Unaffected | None |
| 5 Tablespace | Low | Unaffected | Unaffected | Unaffected | Unaffected | Unaffected | Move objects to encrypted tablespace |
| 6 Column native | Moderate per row | Only with no-salt or deterministic option | No, unless decrypted in query | No | Only on deterministic values | Limited (Oracle requires `NO SALT` to index) | Column type often changes to binary |
| 7 App-layer, randomized | Moderate, in the app tier; KMS calls must be cached | No | No | No | No | No (ciphertext is random) | Column becomes `VARBINARY`/`BYTEA`, larger |
| 7 App-layer, deterministic | Moderate | Yes | No | No | Yes, if same key on both sides | Yes (equality) | As above |
| 8 Always Encrypted, deterministic | Moderate, in driver | Yes | No | No | Yes, same CEK | Yes | Requires BIN2 collation for strings |
| 8 Always Encrypted with enclaves, randomized | Higher, enclave round trips | Yes | Yes | Yes (LIKE) | Limited | Yes, enclave-enabled indexes | Enclave attestation setup |
| 8 MongoDB Queryable Encryption | Higher; extra metadata collections, storage growth | Yes | Yes (range, MongoDB 8.0+) | Preview features only (verify) | No | Managed internally | Encrypted fields fixed at collection creation |
| 9 Tokenization | Network call to vault per tokenize/detokenize unless cached or vaultless | Yes (deterministic tokens) | Only with order-preserving tokens (avoid) | No | Yes (deterministic tokens) | Yes | Usually none if format-preserving |
| 10 Dynamic masking | Negligible | Yes (on real value, which is the inference risk) | Yes | Yes | Yes | Yes | None |

Practical rules the organization applies:

- **Cache data keys, not plaintext.** Application-layer encryption calls KMS once per data key, not once per row. Use the AWS Encryption SDK caching, the AWS KMS Hierarchical keyring, or an equivalent local DEK cache with short TTL.
- **Size the columns.** AES-256-GCM ciphertext adds a 12-byte nonce and a 16-byte tag, plus any envelope header. Base64 encoding adds a further third. A `VARCHAR(20)` passport number becomes roughly 80 to 100 bytes, more with an envelope header.
- **Do not encrypt primary keys or foreign keys.** Use a surrogate identifier (UUID) as the key and encrypt the sensitive natural value.
- **Never use deterministic encryption on low-cardinality columns** (country, gender, card brand). Frequency analysis reveals the values.

## Searchable encryption options

When a C3 field must be searched, the organization chooses one of the following, in order of preference.

| Option | How it works | Leakage | Supported by | Use in the organization |
|---|---|---|---|---|
| Search on a different field | Look up by reservation ID or loyalty number, then decrypt the sensitive field | None beyond the lookup key | Any | First choice. Most "search by passport number" requirements disappear under review |
| Blind index (keyed hash) | Store `HMAC-SHA256(k_index, normalize(value))` in a separate indexed column, possibly truncated | Equality: identical values produce identical hashes. Truncation adds deliberate false positives that reduce leakage | Any database; application code; [code/tokenization](https://github.com/steven-smith-itnet/data-protection-pqc-security-architecture/tree/main/code/tokenization) | Default for guest email and phone lookup in C3 contexts, and for passport-number duplicate detection |
| Deterministic encryption | Same plaintext and key produce the same ciphertext (AES-SIV, Always Encrypted deterministic) | Equality and frequency | Always Encrypted, BigQuery `DETERMINISTIC_ENCRYPT`, Tink deterministic AEAD, GCP Sensitive Data Protection | When the value must also be recoverable from the same column and a separate index column is impractical |
| AWS Database Encryption SDK beacons | Standard beacons are truncated HMACs of an attribute; compound beacons combine parts of several fields; the beacon length is chosen to balance false positives and leakage | Equality on beacon, tuned by beacon length | DynamoDB with the AWS Database Encryption SDK | DynamoDB-based guest profile and digital key services |
| Enclave-based computation | Database decrypts inside an attested enclave for comparisons | Access pattern leakage; relies on enclave trust | Always Encrypted with secure enclaves | SQL Server and Azure SQL workloads needing LIKE or range on C3 columns |
| Structured encryption | Encrypted equality and range tokens managed by the driver | Documented in vendor papers; equality and range | MongoDB Queryable Encryption | MongoDB-based services needing encrypted range queries |
| Order-preserving or order-revealing encryption | Ciphertexts sort like plaintexts | Substantial; reveals order and often approximate values | Some products | Not approved |

### Blind index example (PostgreSQL)

```sql
-- Table stores ciphertext produced by the application and a blind index
CREATE TABLE guest_identity (
    guest_id          uuid PRIMARY KEY,
    passport_ct       bytea NOT NULL,         -- AES-256-GCM envelope ciphertext from the app
    passport_bidx     char(16) NOT NULL,      -- first 16 hex chars of HMAC-SHA256(k_index, normalized value)
    issuing_country   char(2) NOT NULL,
    key_version       smallint NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_guest_identity_bidx ON guest_identity (passport_bidx);

-- Lookup: the application computes the blind index and filters false positives after decrypting
SELECT guest_id, passport_ct, key_version
FROM guest_identity
WHERE passport_bidx = $1;
```

The HMAC key for the blind index is a separate key from the encryption key, held in KMS or the secrets manager, and scoped per data domain. Truncating to 64 bits (16 hex characters) keeps false positives rare for a guest table in the tens of millions while avoiding a perfect one-to-one mapping. The application decrypts candidate rows and compares the cleartext to remove collisions.

## Key granularity: per tenant, per column, per record

| Model | Description | Blast radius | Crypto-shredding | Operational cost | Use in the organization |
|---|---|---|---|---|---|
| Key per database or store | One TDE or CMK key per database | Whole store | Whole store only | Lowest | PP-2 default for C2 stores |
| Key per domain and environment | One CMK per `data-domain` per environment (for example `guest-prod-eu`) | Domain within an environment | Domain only | Low | Mandatory baseline for PP-2 |
| Key per column or field type | Separate keys for passport, card, health data | One field type | Field type | Moderate; more KMS grants | PP-3 for fields with different access audiences (front desk versus spa) |
| Key per tenant | Separate key per franchise owner, brand, or legal entity | One tenant | Tenant offboarding by key deletion | Moderate to high; key count grows with tenants | Multi-tenant platforms serving franchised properties; regional residency |
| Key per data subject | One DEK per guest, wrapped by a domain KEK | One guest | Erasure of one guest (see [Retention, deletion, and crypto-shredding]({% link docs/05-transit-in-use/retention-crypto-shredding.md %})) | High; needs a key table and careful caching | Selected C3 stores where right-to-erasure must reach backups |

The recommended combination for C3 guest identity data is **per-domain, per-region KEK in an HSM-backed KMS, per-field-type DEKs, and per-subject DEKs only where erasure from immutable backups is a stated requirement.** Key per tenant is used where franchise contracts or residency require separation.

Key separation rule: the key used for blind indexes or HMAC surrogates is never the key used for encryption, and never shared across data domains, so a leaked index key does not allow decryption and a leaked loyalty-domain key does not allow correlation with payment tokens.

## Related pages

- [Structured data protection patterns]({% link docs/03-structured/protection-patterns.md %}): the layer stack and threat matrix
- [Protect a new table, step by step]({% link docs/03-structured/patterns/protect-a-new-table.md %})
- [Tokenization, FPE, and masking]({% link docs/03-structured/tokenization-fpe-masking.md %})
- [Key management architecture]({% link docs/02-standards/key-management.md %})
