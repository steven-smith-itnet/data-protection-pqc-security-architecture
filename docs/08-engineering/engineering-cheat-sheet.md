---
title: Engineering cheat sheet
parent: "Phase 7: Engineering enablement"
nav_order: 6
description: "A quick reference by data class: what engineers must do at rest, in transit, in logs, and in non-production, which key and library to use, and what not to do."
---

# Engineering cheat sheet
{: .no_toc }

**Phase 7: Engineering enablement and governance.** A quick reference that answers "what must I do with this data" for each classification tier, with default libraries and code snippets per language.
{: .fs-5 .fw-300 }

## On this page
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Step 1: find the tier

Use the highest tier of any data element the component touches. If a service stores a guest's name (C2) and passport number (C3), the service is C3.

| Tier | Label | Examples | Profile |
|---|---|---|---|
| C0 Public | `Public` | Published rates, property descriptions, press releases | PP-1 |
| C1 Internal | `Internal` | Procedures, non-sensitive operational metrics, org charts | PP-1 |
| C2 Confidential | `Confidential\Guest-PII`, `Confidential\Employee`, `Confidential\Business` | Guest name, email, phone, address, stay history, preferences, loyalty profile, reservations, non-sensitive HR records, contracts, revenue data | PP-2 |
| C3 Restricted | `Restricted\PCI`, `Restricted\Guest-Identity`, `Restricted\Special-Category`, `Restricted\Secrets` | PAN, passport and national ID, biometrics, bank accounts, health/accessibility/allergy data, precise geolocation, children's data, credentials, keys, M&A data | PP-3 |

## Step 2: apply the rules for the tier

### Rules by data class

| Area | C0 / C1 (PP-1) | C2 (PP-2) | C3 (PP-3) |
|---|---|---|---|
| Tags | `data-classification`, `protection-profile=pp1`, `data-owner` | All tags in the schema | All tags; `regulatory-scope` and `data-residency` mandatory |
| At rest | Platform default encryption | Customer-managed key for the domain and environment (for example `guest-prod-pp2`) | Application-layer encryption or tokenization of C3 fields with the PP-3 key, on top of CMK storage |
| In transit, external | TLS 1.2+ | TLS 1.2+, prefer 1.3; hybrid PQ at the edge where supported | TLS 1.3; hybrid PQ where supported |
| In transit, internal | TLS 1.2+ | TLS on every hop, including to databases and caches | mTLS between services |
| Identity | Standard IAM | Workload identity; key use only (no admin); quarterly access review | As C2 plus just-in-time access for humans; decrypt permission on the PP-3 key for named service roles only |
| Logs | No secrets | No C2 values: log IDs, not names or emails | No C3 values, not even masked; no ciphertext of C3 fields in logs |
| Events and messages | No restrictions beyond secrets | C2 allowed in encrypted topics with CMK | No C3 in events; send a reference ID and let authorized consumers call the owning service |
| Caches | No restrictions | Encrypted cache (TLS and at-rest encryption), TTL set | Do not cache plaintext C3; cache ciphertext if necessary |
| Non-production | Copies allowed | Masked or synthetic data only | Synthetic only; production C3 in non-production needs an approved exception |
| Search and analytics | Unrestricted | Masked for non-privileged roles | Blind index for exact match; no plaintext C3 in the data lake curated zone |
| Deletion | Standard | Retention job per `retention-class` | Retention job plus crypto-shredding where designed |
| DLP | None | Monitor mode | Block mode |
| Review path | Self-service | Lightweight review | Full review |

### Which key

| Situation | Key |
|---|---|
| C0/C1 storage | Provider-managed key (no action needed) |
| C2 storage (databases, buckets, disks, topics) | Domain PP-2 CMK, created by the paved-road module, for example `alias/guest-prod-pp2` |
| C3 application-layer encryption | Domain PP-3 key, separate from the PP-2 key, for example `alias/guest-prod-pp3` |
| Blind index or keyed hash | Separate HMAC key per purpose (KMS HMAC key, or a secret held in the secrets manager) |
| Tokenization | The tokenization service's keys; applications never hold them |
| Non-production | Separate keys per environment; never share a production key with test |
| Region | Keys in the same region as the data, and per `data-residency` |

Never create keys by hand in the console. Use the paved-road modules in [`code/terraform/`](https://github.com/steven-smith-itnet/data-protection-pqc-security-architecture/tree/main/code/terraform), which apply tags, rotation, and role separation.

## Default libraries

The organization standardizes on a small number of libraries so that reviews are faster and upgrades (including to PQC) happen in one place.

| Language | Field-level and envelope encryption | Local primitives (when a KMS-integrated library does not fit) | FIPS notes |
|---|---|---|---|
| Java | AWS Encryption SDK for Java; AWS Database Encryption SDK for DynamoDB; Google Tink | JCA `AES/GCM/NoPadding` with a FIPS-validated provider (for example BC-FJA or the provider bundled with the platform) | Use a FIPS 140-3 validated provider where FIPS is required |
| Python | AWS Encryption SDK for Python; Tink for Python | `cryptography` (`AESGCM`) | Validation depends on the OpenSSL build underneath |
| .NET | AWS Encryption SDK for .NET; Azure SDK Key Vault keys client for wrap/unwrap | `System.Security.Cryptography.AesGcm` | Uses the OS crypto (CNG on Windows, OpenSSL on Linux) |
| Go | Tink for Go; check whether an AWS Encryption SDK release for Go covers your needs (verify) | `crypto/aes` with `cipher.NewGCM` | Go 1.24 introduced a native FIPS 140-3 module mode (verify validation status) |
| JavaScript / TypeScript | AWS Encryption SDK for JavaScript | Node.js `crypto` with `aes-256-gcm` | Depends on the Node.js OpenSSL build |
| Any (non-FIPS contexts) | n/a | libsodium (`crypto_aead_xchacha20poly1305_ietf`, `crypto_secretbox`) | Not FIPS-validated; not for PCI or FIPS-required systems |

{: .verify }
Library availability, versions, and FIPS validation status change. Check the current validated modules list on the NIST CMVP site before claiming FIPS compliance.

### Why these libraries

- **AWS Encryption SDK** implements envelope encryption, key commitment, encryption context, and a portable message format. It works with AWS KMS keyrings and also with raw AES keyrings, so it can be used outside AWS.
- **Tink** provides misuse-resistant primitives (you ask for an AEAD, not a cipher mode) and integrates with Cloud KMS, AWS KMS, and HashiCorp Vault.
- **Platform primitives** (JCA, `AesGcm`, `cryptography`) are acceptable when a team needs a specific format, but the team then owns nonce generation, key handling, and format versioning. Expect a longer review.

## Snippets

### Python: AWS Encryption SDK with encryption context

```python
import aws_encryption_sdk
from aws_encryption_sdk import CommitmentPolicy

client = aws_encryption_sdk.EncryptionSDKClient(
    commitment_policy=CommitmentPolicy.REQUIRE_ENCRYPT_REQUIRE_DECRYPT
)
key_provider = aws_encryption_sdk.StrictAwsKmsMasterKeyProvider(
    key_ids=["arn:aws:kms:eu-west-1:111122223333:alias/guest-prod-pp3"]
)

context = {"guest_id": "G-102938", "field": "passport_number", "data-domain": "guest"}

ciphertext, _ = client.encrypt(
    source=b"X12345678", key_provider=key_provider, encryption_context=context
)

plaintext, header = client.decrypt(source=ciphertext, key_provider=key_provider)
# Verify the context on decrypt: the SDK authenticates it, but the application
# must check that it is the context it expected.
assert all(header.encryption_context.get(k) == v for k, v in context.items())
```

{: .note }
KMS key ARNs normally reference a key ID. Some SDK operations accept alias ARNs for encryption but require a key ARN for strict decryption; check the SDK documentation for the version in use.

### Python: Tink AEAD

```python
import tink
from tink import aead

aead.register()

# In production the keyset is wrapped by a KMS key (KMS envelope AEAD);
# a cleartext keyset is shown here only to illustrate the primitive.
keyset_handle = tink.new_keyset_handle(aead.aead_key_templates.AES256_GCM)
primitive = keyset_handle.primitive(aead.Aead)

associated_data = b"guest_id=G-102938|field=allergy"
ciphertext = primitive.encrypt(b"peanut; shellfish", associated_data)
plaintext = primitive.decrypt(ciphertext, associated_data)
```

### Python: HMAC blind index for exact-match search

```python
import hmac
import hashlib
import unicodedata


def normalize_document_number(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    return "".join(ch for ch in value.upper() if ch.isalnum())


def blind_index(value: str, key: bytes, purpose: str) -> str:
    msg = f"{purpose}:{normalize_document_number(value)}".encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()

# Store blind_index(...) in an indexed column; store the AEAD ciphertext separately.
# The HMAC key is fetched from the secrets manager and is not the encryption key.
```

### Java: JCA AES-256-GCM

```java
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import java.security.SecureRandom;
import java.nio.ByteBuffer;

public final class FieldCipher {
    private static final SecureRandom RNG = new SecureRandom();
    private static final int IV_LEN = 12;
    private static final int TAG_BITS = 128;

    public static byte[] encrypt(SecretKey dek, byte[] plaintext, byte[] aad) throws Exception {
        byte[] iv = new byte[IV_LEN];
        RNG.nextBytes(iv);
        Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
        c.init(Cipher.ENCRYPT_MODE, dek, new GCMParameterSpec(TAG_BITS, iv));
        c.updateAAD(aad);
        byte[] ct = c.doFinal(plaintext);
        // Format: version (1 byte) | iv | ciphertext+tag. The version byte allows algorithm changes later.
        return ByteBuffer.allocate(1 + IV_LEN + ct.length).put((byte) 1).put(iv).put(ct).array();
    }
}
```

The DEK is generated by KMS (`GenerateDataKey` or the equivalent) and only its wrapped form is stored. Never reuse an IV with the same key; random 96-bit IVs are safe for a bounded number of messages per key, which is another reason to use per-record or per-object DEKs.

### .NET: AesGcm

```csharp
using System.Security.Cryptography;

public static byte[] Encrypt(byte[] key, byte[] plaintext, byte[] associatedData)
{
    var nonce = RandomNumberGenerator.GetBytes(AesGcm.NonceByteSizes.MaxSize); // 12 bytes
    var ciphertext = new byte[plaintext.Length];
    var tag = new byte[16];
    using var aes = new AesGcm(key, tag.Length);
    aes.Encrypt(nonce, plaintext, ciphertext, tag, associatedData);

    var output = new byte[1 + nonce.Length + ciphertext.Length + tag.Length];
    output[0] = 1; // format version
    nonce.CopyTo(output, 1);
    ciphertext.CopyTo(output, 1 + nonce.Length);
    tag.CopyTo(output, 1 + nonce.Length + ciphertext.Length);
    return output;
}
```

### Go: AES-256-GCM

```go
package fieldcrypto

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
)

func Encrypt(dek, plaintext, aad []byte) ([]byte, error) {
	block, err := aes.NewCipher(dek) // 32-byte key selects AES-256
	if err != nil {
		return nil, err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, err
	}
	nonce := make([]byte, gcm.NonceSize())
	if _, err := rand.Read(nonce); err != nil {
		return nil, err
	}
	out := append([]byte{1}, nonce...) // format version, then nonce
	return gcm.Seal(out, nonce, plaintext, aad), nil
}
```

### Log redaction (Python logging filter)

```python
import logging
import re

PATTERNS = [
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "[REDACTED-PAN]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[REDACTED-EMAIL]"),
]


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for pattern, replacement in PATTERNS:
            msg = pattern.sub(replacement, msg)
        record.msg, record.args = msg, ()
        return True
```

Pattern redaction is a safety net, not the control. The control is structured logging with an allow-list of fields.

## What not to do

| Do not | Why | Instead |
|---|---|---|
| Write your own cipher mode, padding, or key derivation | Subtle errors break confidentiality or integrity | Use AEAD from an approved library |
| Use AES-ECB, AES-CBC without a MAC, or unauthenticated CTR | No integrity; ECB leaks patterns | AES-256-GCM or the library default AEAD |
| Hard-code keys, or put keys in environment variables in container images | Keys leak with the image or repository | KMS for KEKs; secrets manager for HMAC keys |
| Use the same key for storage encryption and application-layer encryption | Anyone with storage access can use the key to decrypt fields | Separate PP-2 and PP-3 keys |
| Use unkeyed SHA-256 of emails or ID numbers as pseudonyms | Easily reversed by dictionary attack | HMAC with a managed key |
| Log request bodies | Captures names, emails, sometimes PAN | Log IDs and outcomes |
| Store PAN, even encrypted, "for convenience" | Expands PCI scope | Gateway tokens |
| Copy production databases to test | C2/C3 in weakly controlled environments | Masked or synthetic data |
| Grant `kms:*` or `Key Vault Crypto Officer` to application identities | Application can disable or delete keys | Encrypt/decrypt only |
| Pin a specific curve or algorithm with no version field | Blocks PQC migration | Store an algorithm/version identifier with ciphertext |
| Disable certificate validation to fix a TLS error | Removes authentication | Fix the trust store or certificate |
| Use deterministic encryption on low-cardinality fields | Frequency analysis reveals values | Randomized AEAD; masking |

## Before you ship

1. All resources tagged; guardrails and CI checks pass.
2. Keys created by the paved-road module; application identity has use-only permissions.
3. C3 fields encrypted or tokenized in the application; tested by reading the raw column.
4. TLS 1.2+ on all hops; mTLS for C3 service-to-service.
5. Logs checked for C2/C3 values.
6. Non-production data is masked or synthetic.
7. Retention and deletion implemented.
8. Key unavailability behavior tested.
9. Ciphertext format includes a version identifier.

## Key takeaways for engineering teams

- The highest tier a component touches decides its rules.
- C3 fields are protected in the application with a PP-3 key separate from the storage key.
- Use the approved libraries; they handle nonces, key commitment, and formats.
- Keep C2/C3 values out of logs, events, and non-production.
- Store a version identifier with every ciphertext so algorithms can change.

## Related pages

- [Encryption decision trees]({% link docs/08-engineering/decision-trees.md %})
- [Code and tooling lab]({% link docs/08-engineering/code-lab.md %})
- [Cryptographic standards]({% link docs/02-standards/crypto-standards.md %})
- [Secrets management]({% link docs/02-standards/secrets-management.md %})
- [Crypto agility and hybrid designs]({% link docs/06-pqc/crypto-agility.md %})

## Sources

- AWS Encryption SDK developer guide: <https://docs.aws.amazon.com/encryption-sdk/latest/developer-guide/introduction.html>
- Google Tink: <https://developers.google.com/tink>
- libsodium documentation: <https://doc.libsodium.org/>
- NIST Cryptographic Module Validation Program: <https://csrc.nist.gov/projects/cryptographic-module-validation-program>
