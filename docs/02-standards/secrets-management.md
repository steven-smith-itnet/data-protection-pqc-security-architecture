---
title: Secrets management
parent: "Phase 2: Standards and keys"
nav_order: 6
description: "Cloud secret stores and HashiCorp Vault, rotation, workload identity federation to remove static credentials, secret scanning, and Kubernetes secrets encryption."
---

# Secrets management
{: .no_toc }

**Phase 2: Standards and keys.** This page removes passwords, API keys, and connection strings from code, pipelines, and configuration, first by eliminating them with workload identity federation and then by storing and rotating the ones that remain.
{: .fs-5 .fw-300 }

## On this page
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## The problem

Secrets are classified `Restricted\Secrets` (C3). A leaked database password or cloud access key gives an attacker the same access as the application, and bypasses every encryption control on the data it can read. In hospitality environments, secrets are commonly found in:

- PMS and POS interface configuration files on property servers.
- Integration credentials for OTAs, GDS, payment gateways, and loyalty partners.
- CI/CD pipeline variables and infrastructure-as-code state files.
- Container images, Helm values files, and Kubernetes Secrets stored base64-encoded (which is encoding, not encryption).
- Shared service-account passwords used by multiple teams and never rotated.

The organization's approach has three layers, in order of preference:

1. **Eliminate** the secret by using federated, short-lived identity (workload identity federation, managed identities, IAM roles).
2. **Generate dynamically** where a secret is still needed (for example, a database credential created per session with a short lease).
3. **Store and rotate** the static secrets that remain in an approved secrets manager, encrypted with a CMK.

```mermaid
flowchart TD
    A["Workload needs to call a service"] --> B{"Does the target accept<br/>federated identity?<br/>(cloud APIs, Entra ID, OIDC)"}
    B -- "Yes" --> WIF["Workload identity federation<br/>No secret stored"]
    B -- "No" --> C{"Can credentials be<br/>generated on demand?<br/>(database, cloud, PKI)"}
    C -- "Yes" --> DYN["Dynamic secret<br/>(Vault database engine,<br/>RDS IAM auth, short lease)"]
    C -- "No" --> D["Static secret in secrets manager<br/>CMK-encrypted, rotated,<br/>access logged"]
    D --> E{"Rotation automated?"}
    E -- "No" --> F["Exception with expiry<br/>and rotation plan"]
```

## Approved secret stores

| Store | Scope | Encryption | Rotation | Notes |
|---|---|---|---|---|
| **AWS Secrets Manager** | AWS workloads | AWS KMS; CMK required for C3 | Built-in rotation via Lambda functions; managed rotation for RDS, Aurora, Redshift, and DocumentDB master credentials | Resource policies; cross-account access; replication to other Regions |
| **AWS Systems Manager Parameter Store (SecureString)** | Non-sensitive configuration and low-risk secrets | AWS KMS | No built-in rotation | Allowed for C1/C2 configuration only; not for C3 secrets |
| **Azure Key Vault secrets** | Azure workloads | Key Vault (HSM-backed in Premium) | Event Grid `SecretNearExpiry` event triggers an Azure Function that rotates | RBAC roles Key Vault Secrets User / Secrets Officer; Key Vault references in App Service and Functions |
| **Google Cloud Secret Manager** | Google Cloud workloads | Google default encryption or CMEK | Rotation schedule publishes Pub/Sub notifications; a Cloud Run or Cloud Functions handler performs rotation | Regional secrets and user-managed replication for residency |
| **OCI Vault secrets** | OCI workloads | OCI Vault master encryption key | Automatic rotation for supported targets (for example Autonomous Database) and function-based rotation (verify current support) | Secret bundles with versions |
| **HashiCorp Vault** (Enterprise or HCP Vault Dedicated) | Cross-cloud and on-prem; properties and data centers | Seal wrapped by cloud KMS or HSM (auto-unseal) | Dynamic secrets engines; static role rotation | Business Source License since 2023; OpenBao is a community fork under MPL (evaluate support model) |
| **CyberArk, Delinea, BeyondTrust (PAM)** | Human privileged accounts, break-glass, property server local admin | Vendor | Password rotation for privileged accounts | For human access; not a replacement for workload secrets |

{: .note }
The choice between cloud-native stores and HashiCorp Vault is a trade-off. Cloud-native stores integrate with each cloud's IAM and managed services with no infrastructure to run, but produce four different operating models. Vault gives one API and policy model across clouds and on-prem, and dynamic secrets for many targets, at the cost of operating a critical, highly available cluster. The organization uses cloud-native stores for cloud-native workloads and Vault for on-prem, property, and cross-cloud integration secrets.

## Workload identity federation: eliminate the secret

The most effective secrets control is not having the secret. Every cloud now lets workloads obtain short-lived credentials by presenting a platform-issued identity token, with no long-lived key to leak.

| Platform | Mechanism | What replaces the static credential |
|---|---|---|
| AWS EC2, Lambda, ECS | IAM roles (instance profile, execution role, task role) | Temporary STS credentials |
| Amazon EKS | EKS Pod Identity (agent-based association of IAM role to service account) or IAM Roles for Service Accounts (IRSA, OIDC-based) | Temporary STS credentials per pod |
| Azure VMs, App Service, Functions, Container Apps | Managed identities | Entra ID access tokens |
| AKS | Microsoft Entra Workload ID (federated identity credential on a user-assigned managed identity, bound to a Kubernetes service account) | Entra ID tokens |
| GKE | Workload Identity Federation for GKE | Google access tokens for the Kubernetes service account principal |
| Google Cloud (other runtimes) | Attached service accounts | Google access tokens |
| OCI | Instance principals, resource principals, OKE workload identity | OCI security tokens |
| CI/CD (GitHub Actions, GitLab, Azure DevOps) | OIDC federation to AWS IAM, Entra ID, Google Workload Identity Federation | Short-lived cloud credentials per pipeline run |
| Cross-cloud | AWS IAM Roles Anywhere (X.509), Google Workload Identity Federation trusting AWS or Azure, Entra federated credentials trusting other issuers | Short-lived credentials based on the other cloud's identity |

### EKS Pod Identity

```bash
# Associate an IAM role with a Kubernetes service account in an EKS cluster
aws eks create-pod-identity-association \
  --cluster-name guest-prod-euw1 \
  --namespace guest-booking \
  --service-account booking-api \
  --role-arn arn:aws:iam::111122223333:role/guest-booking-api-prod
```

The IAM role's trust policy allows the `pods.eks.amazonaws.com` service principal to call `sts:AssumeRole` and `sts:TagSession`. Pod Identity adds session tags (cluster, namespace, service account) that can be used in IAM and KMS policy conditions.

### AKS workload identity

```bash
# Federate a user-assigned managed identity with a Kubernetes service account
az identity federated-credential create \
  --name booking-api-fic \
  --identity-name mi-guest-booking-api \
  --resource-group rg-guest-prod-weu \
  --issuer "$(az aks show -g rg-guest-prod-weu -n aks-guest-prod-weu --query oidcIssuerProfile.issuerUrl -o tsv)" \
  --subject system:serviceaccount:guest-booking:booking-api \
  --audience api://AzureADTokenExchange
```

The service account is annotated with `azure.workload.identity/client-id`, and pods carry the label `azure.workload.identity/use: "true"`.

### GKE Workload Identity Federation

```bash
# Grant a Kubernetes service account direct access to a secret (principal identifier form)
gcloud secrets add-iam-policy-binding booking-api-ota-key \
  --project=guest-prod-euw1 \
  --role=roles/secretmanager.secretAccessor \
  --member="principal://iam.googleapis.com/projects/123456789012/locations/global/workloadIdentityPools/guest-prod-euw1.svc.id.goog/subject/ns/guest-booking/sa/booking-api"
```

### GitHub Actions OIDC to AWS

{% raw %}
```yaml
permissions:
  id-token: write
  contents: read
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::111122223333:role/gha-guest-booking-deploy
          aws-region: eu-west-1
      - run: aws sts get-caller-identity
      - run: echo "Deploying ${{ github.sha }}"
```
{% endraw %}


The IAM role trust policy restricts `token.actions.githubusercontent.com:sub` to the specific repository and environment (for example `repo:example-org/guest-booking:environment:prod`), so another repository cannot assume it.

## Dynamic secrets

Where a target does not accept federated identity, generate credentials per workload or per session.

| Target | Mechanism |
|---|---|
| Amazon RDS / Aurora (MySQL, PostgreSQL) | IAM database authentication: the application requests a 15-minute auth token with its IAM role |
| Azure SQL, PostgreSQL, MySQL flexible server | Entra ID authentication with managed identity |
| Cloud SQL | IAM database authentication; Cloud SQL Auth Proxy |
| On-prem Oracle, SQL Server, PostgreSQL | HashiCorp Vault database secrets engine creating per-lease users |
| Cloud provider credentials for third-party tools | Vault AWS, Azure, and GCP secrets engines |
| Certificates | Vault PKI engine, cert-manager, SPIRE |

HashiCorp Vault database secrets engine example for an on-prem PostgreSQL reporting database:

{% raw %}
```bash
vault secrets enable database

vault write database/config/revenue-dw \
  plugin_name=postgresql-database-plugin \
  connection_url="postgresql://{{username}}:{{password}}@revenue-dw.dc1.example.internal:5432/revenue?sslmode=verify-full" \
  allowed_roles="revenue-readonly" \
  username="vault_admin" \
  password="$(cat /run/secrets/revenue_dw_admin)"

vault write database/roles/revenue-readonly \
  db_name=revenue-dw \
  creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT SELECT ON ALL TABLES IN SCHEMA reporting TO \"{{name}}\";" \
  default_ttl=1h max_ttl=8h

# Rotate the root credential so only Vault knows it
vault write -f database/rotate-root/revenue-dw

# An application obtains a lease
vault read database/creds/revenue-readonly
```
{% endraw %}

### Vault Transit: encryption as a service

Vault's Transit secrets engine performs encryption, decryption, signing, and HMAC without releasing keys to the application. It is an alternative to cloud KMS for on-prem and property applications. Transform (Enterprise) adds tokenization and FPE, discussed in [Tokenization, FPE, and masking]({% link docs/03-structured/tokenization-fpe-masking.md %}).

```bash
vault secrets enable transit
vault write -f transit/keys/guest-passport type=aes256-gcm96
vault write transit/encrypt/guest-passport plaintext=$(printf 'X1234567' | base64) context=$(printf 'guest-8812' | base64)
```

{: .note }
The `context` parameter applies only to keys created with `derived=true`; it is shown here to illustrate binding a subject identifier. For a non-derived key, omit it.

## Rotation

| Secret type | Rotation approach | Target frequency |
|---|---|---|
| Cloud access keys (AWS IAM user keys, Azure client secrets, GCP service account keys) | Eliminate; where unavoidable, rotate via automation and alert on age | Prohibited for new use; existing keys rotated every 90 days |
| Database master credentials | Managed rotation (Secrets Manager for RDS; Vault root rotation) | 30 to 90 days; nobody knows the master password |
| Application database users | Dynamic credentials or managed rotation with alternating users | Hours (dynamic) or 30 days |
| Third-party API keys (OTA, GDS, payment gateway) | Rotation function using the partner's API where available; otherwise scheduled manual rotation with dual control | 90 days or per partner contract |
| TLS private keys | Certificate renewal with new key | Per certificate lifetime |
| Encryption keys | KMS rotation (see [Key management architecture]({% link docs/02-standards/key-management.md %})) | Per cryptoperiod |
| Break-glass passwords | PAM checkout with automatic rotation after use | After every use |

AWS Secrets Manager managed rotation for an RDS master user:

```bash
# Let RDS manage the master password in Secrets Manager with a CMK
aws rds modify-db-instance \
  --db-instance-identifier guest-profile-prod-euw1 \
  --manage-master-user-password \
  --master-user-secret-kms-key-id alias/guest-prod-euw1-secrets \
  --apply-immediately

# Rotate a custom secret every 30 days with an existing rotation Lambda
aws secretsmanager rotate-secret \
  --secret-id prod/guest-booking/ota-api-key \
  --rotation-lambda-arn arn:aws:lambda:eu-west-1:111122223333:function:rotate-ota-api-key \
  --rotation-rules AutomaticallyAfterDays=30
```

Google Cloud Secret Manager with a rotation schedule (Secret Manager sends notifications; the subscriber performs rotation):

```bash
gcloud secrets create ota-api-key \
  --project=guest-prod-euw1 \
  --replication-policy=user-managed --locations=europe-west1,europe-west4 \
  --kms-key-name=projects/guest-keys-prod/locations/europe-west1/keyRings/guest-prod/cryptoKeys/secrets \
  --topics=projects/guest-prod-euw1/topics/secret-rotation \
  --rotation-period=2592000s --next-rotation-time="2026-11-01T00:00:00Z" \
  --labels=data-classification=restricted,data-domain=guest
```

{: .verify }
With user-managed replication, CMEK is specified per replica location. Confirm the flag form for multiple replica keys in the current `gcloud secrets create` reference.

## Secret scanning

Detection is required because prevention is never complete.

| Control | Where | Behavior |
|---|---|---|
| GitHub secret scanning and push protection | All organization GitHub repositories | Blocks pushes containing supported secret patterns; alerts on historical findings; partner program notifies providers (for example AWS) who may revoke exposed keys |
| gitleaks in pre-commit and CI | Developer workstations and all pipelines, including non-GitHub repositories | Fails the build on findings; custom rules for organization-specific formats |
| Cloud-native detection | AWS (exposed key notifications and quarantine policy), Google Cloud (service account key exposure detection), Microsoft Defender for Cloud | Alert and, for AWS, attach a quarantine policy to exposed keys |
| Container image scanning | Registry scanning (Amazon Inspector, Defender for Containers, Artifact Analysis, Trivy) | Detect secrets baked into images |
| Property server sweeps | Endpoint agent or scheduled scan of PMS/POS interface configuration directories | Find plaintext integration credentials on property systems |

A gitleaks configuration that extends the defaults with an organization-specific pattern:

```toml
# .gitleaks.toml
[extend]
useDefault = true

[[rules]]
id = "example-loyalty-partner-key"
description = "Loyalty partner API key"
regex = '''lpk_(live|test)_[A-Za-z0-9]{32}'''
keywords = ["lpk_live", "lpk_test"]

[allowlist]
paths = ['''docs/examples/.*''']
```

```bash
# Pre-commit usage and CI usage
gitleaks git --staged --redact --config .gitleaks.toml
gitleaks git --redact --report-format sarif --report-path gitleaks.sarif
```

{: .verify }
gitleaks v8.19 and later changed the CLI to `gitleaks git` and `gitleaks dir` subcommands (older versions used `gitleaks detect` and `gitleaks protect`). Confirm the version pinned in the pipeline image.

When a secret is found, the response is always **revoke and rotate first**, then remove from history. Removing a commit does not un-leak a secret that has been cloned, cached, or indexed.

## Kubernetes secrets

Kubernetes Secrets are base64-encoded in the API and stored in etcd. Without additional controls anyone with etcd or backup access can read them.

| Control | Detail |
|---|---|
| Encryption at rest with KMS provider v2 | The API server envelope-encrypts Secrets with a DEK wrapped by an external KMS plugin (stable since Kubernetes 1.29). Managed services expose this as a setting: EKS envelope encryption with an AWS KMS key, AKS KMS etcd encryption with Key Vault, GKE application-layer secrets encryption with Cloud KMS. |
| External Secrets Operator (ESO) | Synchronizes secrets from AWS Secrets Manager, Key Vault, Secret Manager, OCI Vault, or Vault into Kubernetes Secrets, so the source of truth stays in the managed store |
| Secrets Store CSI Driver | Mounts secrets from the external store as files in the pod without creating a Kubernetes Secret (optional sync) |
| RBAC | `get`, `list`, and `watch` on Secrets restricted to the workloads that need them; `list` on Secrets is equivalent to reading all of them |
| Avoid in Git | Never commit Secret manifests with values; if GitOps requires encrypted secrets in Git, use SOPS with a KMS key or Sealed Secrets |

Self-managed cluster encryption configuration using KMS v2:

```yaml
apiVersion: apiserver.config.k8s.io/v1
kind: EncryptionConfiguration
resources:
  - resources:
      - secrets
    providers:
      - kms:
          apiVersion: v2
          name: vault-kms-plugin
          endpoint: unix:///var/run/kmsplugin/socket.sock
          timeout: 3s
      - identity: {}
```

EKS equivalent at cluster creation or later:

```bash
aws eks associate-encryption-config \
  --cluster-name guest-prod-euw1 \
  --encryption-config '[{"resources":["secrets"],"provider":{"keyArn":"arn:aws:kms:eu-west-1:111122223333:alias/guest-prod-euw1-k8s"}}]'
```

External Secrets Operator using AWS Secrets Manager with Pod Identity or IRSA:

```yaml
apiVersion: external-secrets.io/v1
kind: SecretStore
metadata:
  name: aws-sm
  namespace: guest-booking
spec:
  provider:
    aws:
      service: SecretsManager
      region: eu-west-1
---
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: ota-api-key
  namespace: guest-booking
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: aws-sm
    kind: SecretStore
  target:
    name: ota-api-key
    creationPolicy: Owner
  data:
    - secretKey: apiKey
      remoteRef:
        key: prod/guest-booking/ota-api-key
        property: api_key
```

{: .verify }
External Secrets Operator promoted its API to `external-secrets.io/v1` in 2025; older clusters use `v1beta1`. Match the API version to the installed operator.

## Property and on-prem considerations

- PMS and POS vendor interfaces often require a stored credential on a property server. Store it in the OS credential store (Windows DPAPI-protected credential manager, or a Vault agent with AppRole and response wrapping), not in an INI file.
- Franchised properties operate their own systems. The organization's franchise technology standards should require a secrets manager or PAM for any credential that reaches organization systems, and the credentials the organization issues to franchisees should be per-property and revocable.
- Break-glass local administrator passwords on property servers are managed by Windows LAPS (with passwords stored in Entra ID or AD) and rotated after use.

## Good, better, best

| Level | Approach | Trade-offs |
|---|---|---|
| **Good** | All static secrets in a cloud secrets manager or Vault with CMK encryption; secret scanning on all repositories; no secrets in code | Secrets still exist and must be rotated; rotation often manual |
| **Better** | Workload identity federation for all cloud-native workloads and CI/CD; automated rotation for database and partner credentials; Kubernetes KMS encryption plus ESO; push protection enforced | Requires changes to application authentication; older SDKs and vendor products may not support federation |
| **Best** | No long-lived credentials for workloads: dynamic secrets for databases, SPIFFE/mTLS for service-to-service, HSM-backed Vault seal; secret age and count reported as KPIs | Operational dependency on Vault/SPIRE availability; vendor products at properties lag behind |

## Key takeaways for engineering teams

- Before storing a secret, ask whether you can federate identity instead. For cloud APIs and CI/CD the answer is almost always yes.
- Never put secrets in code, images, Helm values, Terraform variables, or pipeline logs. Push protection will block you; the gitleaks CI step will fail the build.
- Static secrets live in the approved store for your platform, encrypted with a CMK, with a rotation function.
- Kubernetes Secrets require KMS encryption and should be sourced from a managed store through External Secrets Operator or the CSI driver.
- If a secret leaks, revoke and rotate first. History rewriting is cleanup, not remediation.

## Related pages

- [Key management architecture]({% link docs/02-standards/key-management.md %})
- [Certificates and PKI]({% link docs/02-standards/certificates-pki.md %})
- [Guardrails and policy as code]({% link docs/08-engineering/policy-as-code.md %})
- [Monitoring and detection]({% link docs/09-govern/monitoring-detection.md %})
- [Engineering cheat sheet]({% link docs/08-engineering/engineering-cheat-sheet.md %})

## Sources

- AWS Secrets Manager rotation: <https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotating-secrets.html>
- EKS Pod Identity: <https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html>
- Microsoft Entra Workload ID for AKS: <https://learn.microsoft.com/azure/aks/workload-identity-overview>
- GKE Workload Identity Federation: <https://cloud.google.com/kubernetes-engine/docs/concepts/workload-identity>
- Google Cloud Secret Manager rotation: <https://cloud.google.com/secret-manager/docs/secret-rotation>
- HashiCorp Vault database secrets engine: <https://developer.hashicorp.com/vault/docs/secrets/databases>
- Kubernetes KMS provider: <https://kubernetes.io/docs/tasks/administer-cluster/kms-provider/>
- External Secrets Operator: <https://external-secrets.io/>
- GitHub secret scanning: <https://docs.github.com/code-security/secret-scanning>
- gitleaks: <https://github.com/gitleaks/gitleaks>
