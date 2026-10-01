---
title: "Protect a new table, step by step"
parent: Structured data protection patterns
grand_parent: "Phase 3: Structured data"
nav_order: 2
description: "The procedure for protecting a new table, from column classification to evidence, and the anti-patterns to avoid."
---

# Protect a new table, step by step
{: .no_toc }

**Phase 3: Structured data.** The repeatable procedure an engineering team follows to protect a new table, and the common mistakes the design review checks for.
{: .fs-5 .fw-300 }

## On this page
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Step-by-step: protect a new table

This procedure is used for every new table or collection, and for existing tables when they are brought into scope. It maps to the [security design review process]({% link docs/08-engineering/design-review.md %}).

### Step 1: classify every column

Record the classification per column, not per table. Use the discovery scanner ([code/discovery](https://github.com/steven-smith-itnet/data-protection-pqc-security-architecture/tree/main/code/discovery)) against sample data and confirm with the data owner.

| Column | Example | Tier | Label | Notes |
|---|---|---|---|---|
| `reservation_id` | `R8XK2Q` | C1 | Internal | Business key |
| `guest_name` | Maria Silva | C2 | `Confidential\Guest-PII` | Needed at front desk |
| `email` | m.silva@example.com | C2 | `Confidential\Guest-PII` | Lookup key for guest profile |
| `passport_number` | X1234567 | C3 | `Restricted\Guest-Identity` | Required by local registration law in some countries |
| `card_token` | tok_4f8a... | C2 | `Confidential\Guest-PII` (token, not PAN) | Gateway token; never PAN |
| `dietary_notes` | Severe nut allergy | C3 | `Restricted\Special-Category` | Health data |

### Step 2: choose the pattern per column

Apply the [label-to-control mapping]({% link docs/01-prerequisites/label-to-control.md %}) and the [encryption decision trees]({% link docs/08-engineering/decision-trees.md %}):

- C3 identifiers that must be recoverable: application-layer encryption or client-side encryption, plus a blind index if lookup is required.
- C3 values that only need to be matched, not recovered, in this system: HMAC surrogate only.
- PAN: never stored; tokenize at the gateway (see [Payment card data and PCI DSS]({% link docs/03-structured/payment-data-pci.md %})).
- C2 fields: CMK storage encryption plus dynamic masking for non-privileged roles.
- Free-text C3 fields such as `dietary_notes`: application-layer encryption; do not index.

### Step 3: pick keys

- Identify the KEK: the domain and environment CMK, for example the `guest` domain key in the `eu` residency region.
- Decide whether a separate field-type DEK is needed (different audiences for passport versus dietary data: yes).
- Create a separate HMAC key for blind indexes.
- Confirm the key policy separates key administrators from key users, and that only the application's workload identity can call `Decrypt`.
- Tag the key with the same `data-classification`, `data-domain`, and `data-residency` values as the table.

### Step 4: implement

Example DDL for SQL Server with Always Encrypted for the C3 columns and dynamic masking for C2:

```sql
CREATE TABLE dbo.GuestStay (
    StayId          UNIQUEIDENTIFIER NOT NULL PRIMARY KEY DEFAULT NEWSEQUENTIALID(),
    ReservationId   VARCHAR(12) NOT NULL,
    GuestName       NVARCHAR(200) MASKED WITH (FUNCTION = 'partial(1,"****",0)') NOT NULL,
    Email           NVARCHAR(320) MASKED WITH (FUNCTION = 'email()') NULL,
    PassportNumber  VARCHAR(20) COLLATE Latin1_General_BIN2
        ENCRYPTED WITH (COLUMN_ENCRYPTION_KEY = CEK_GuestIdentity,
                        ENCRYPTION_TYPE = DETERMINISTIC,
                        ALGORITHM = 'AEAD_AES_256_CBC_HMAC_SHA_256') NULL,
    DietaryNotes    NVARCHAR(1000)
        ENCRYPTED WITH (COLUMN_ENCRYPTION_KEY = CEK_SpecialCategory,
                        ENCRYPTION_TYPE = RANDOMIZED,
                        ALGORITHM = 'AEAD_AES_256_CBC_HMAC_SHA_256') NULL,
    CardToken       VARCHAR(64) NULL
);

ADD SENSITIVITY CLASSIFICATION TO dbo.GuestStay.PassportNumber
    WITH (LABEL = 'Restricted\Guest-Identity', INFORMATION_TYPE = 'National ID', RANK = CRITICAL);
ADD SENSITIVITY CLASSIFICATION TO dbo.GuestStay.Email
    WITH (LABEL = 'Confidential\Guest-PII', INFORMATION_TYPE = 'Contact Info', RANK = MEDIUM);
```

Tag the store:

```bash
aws rds add-tags-to-resource \
  --resource-name arn:aws:rds:eu-west-1:111122223333:db:guest-stay-prod \
  --tags Key=data-classification,Value=restricted Key=protection-profile,Value=pp3 \
         Key=data-domain,Value=guest Key=regulatory-scope,Value=gdpr \
         Key=data-residency,Value=eu Key=data-owner,Value=guest-platform
```

### Step 5: test

| Test | Method | Pass condition |
|---|---|---|
| DBA sees ciphertext | Connect as `sysadmin` without column encryption enabled; `SELECT PassportNumber` | Binary ciphertext returned |
| Non-privileged user sees masked values | Connect as `analyst` role; select `Email` | `mXXX@XXXX.com` pattern |
| SQL injection resistance | DAST against the endpoint; confirm any exfiltrated rows contain ciphertext for C3 columns | No cleartext C3 values |
| Key revocation | Disable CMK or revoke KMS grant in a non-production copy | Application fails closed; alert fires |
| Logs are clean | Search application and database logs for test passport values | Zero matches |
| Backups | Restore backup to an isolated server without key access | Restore fails or C3 columns remain ciphertext |
| Non-production | Inspect latest refresh of test environment | Masked or synthetic values only |

### Step 6: record evidence

Store in the evidence repository: the DDL, `sys.sensitivity_classifications` output, the key policy JSON, the KMS key rotation status, test results with dates, and the design review decision. These map to PCI DSS 3.5.1 and 3.6, GDPR Article 32, and internal standards through [compliance mapping]({% link docs/09-govern/compliance-mapping.md %}).

## Common anti-patterns

| Anti-pattern | Why it fails | Correct pattern |
|---|---|---|
| "TDE is on, so PCI 3.5.1 is met" | TDE decrypts for every query; auditors expect PAN unreadable to anyone without a business need | Tokenize PAN; PAN absent from the database |
| Encrypting with a key stored in the same table or config file as the data | One compromise yields both | KEK in KMS/HSM; DEK wrapped |
| Deterministic encryption on country or card brand | Frequency analysis reveals values | Randomized encryption or no encryption for low-sensitivity attributes |
| One HMAC key across all domains | Enables cross-domain correlation if leaked | Separate HMAC key per domain |
| Masking as the only C3 control | Bypassed by owners, exports, and inference | Encryption or tokenization, masking as an additional view control |
| Unmasked production refresh to test | Test environments have weaker access | Static masking or synthetic data during refresh |

## Related pages

- [Structured data protection patterns]({% link docs/03-structured/protection-patterns.md %})
- [Search, joins, and key granularity]({% link docs/03-structured/patterns/search-and-key-granularity.md %})
- [Label-to-control mapping]({% link docs/01-prerequisites/label-to-control.md %})
- [Security design review process]({% link docs/08-engineering/design-review.md %})
