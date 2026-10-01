---
title: Labeling, tagging, and metadata
parent: "Phase 1: Know the data"
nav_order: 3
description: "How classification becomes machine-readable metadata: Purview sensitivity labels, cloud tags and labels with enforcement, column-level tags, and object metadata, with syntax for each."
---

# Labeling, tagging, and metadata
{: .no_toc }

**Phase 1: Know the data.** Turns the classification scheme into machine-readable labels and tags on files, resources, columns, and objects, and enforces their presence so that automation can read them.
{: .fs-5 .fw-300 }

## On this page
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Why metadata is the interface

A classification that exists only in a spreadsheet cannot select a key, trigger masking, or block an email. Metadata attached to the data itself can. This page describes the four layers where the organization records classification, and how each is enforced.

| Layer | Carrier | Read by | Examples |
|---|---|---|---|
| Documents and email | Microsoft Purview sensitivity labels embedded in file metadata and message headers | Office apps, Purview DLP, Defender for Cloud Apps, Purview scanner, third-party DLP via MIP SDK | A passport scan PDF labeled `Restricted\Guest-Identity` with encryption |
| Containers and resources | Sensitivity labels on Teams, groups, and SharePoint sites; cloud resource tags and labels | Purview, Azure Policy, AWS SCPs and tag policies, GCP IAM conditions and org policy, OCI IAM policy, Terraform | An S3 bucket tagged `data-classification=restricted` |
| Columns and tables | Policy tags, object tags, LF-tags, Unity Catalog tags, SQL sensitivity classifications | Warehouse query engines, masking policies, access control | A BigQuery column with a `Restricted` policy tag |
| Objects and files in storage | S3 object tags, Azure blob index tags, file system properties | Lifecycle rules, IAM conditions, scanners | An S3 object tagged `data-classification=restricted` |

All four layers use the same vocabulary: the four tiers, the nine labels, and the tag schema.

## The tag schema

The schema works unchanged across AWS tags, Azure tags, Google Cloud labels, and OCI tags. All keys and values are lowercase and use only hyphens and underscores, because Google Cloud labels require lowercase keys and values with a limited character set.

| Key | Allowed values | Purpose |
|---|---|---|
| `data-classification` | `public`, `internal`, `confidential`, `restricted` | Tier; drives the protection profile |
| `protection-profile` | `pp1`, `pp2`, `pp3` | Explicit profile; must be at least the profile implied by the tier |
| `data-domain` | `guest`, `payment`, `loyalty`, `employee`, `finance`, `operations`, `property-iot`, `security` | Selects the domain key and owner group |
| `regulatory-scope` | `none`, `pci`, `gdpr`, `ccpa`, `pipl`, `lgpd`, or combinations joined by `_`, e.g. `pci_gdpr` | Selects regime-specific controls and evidence |
| `data-residency` | `us`, `eu`, `uk`, `cn`, `apac`, `latam`, `mea`, `global` | Selects in-region keys and allowed regions |
| `data-owner` | Team slug, e.g. `guest-platform` | Routes findings and approvals |
| `retention-class` | `r90d`, `r1y`, `r3y`, `r7y`, `r10y`, `legal-hold` | Drives lifecycle and deletion |

Mapping between the tag value and the label:

| `data-classification` | Labels in that tier |
|---|---|
| `public` | `Public` |
| `internal` | `Internal` |
| `confidential` | `Confidential\Guest-PII`, `Confidential\Employee`, `Confidential\Business` |
| `restricted` | `Restricted\PCI`, `Restricted\Guest-Identity`, `Restricted\Special-Category`, `Restricted\Secrets` |

The sublabel is not carried in the cloud tag, because backslashes are not permitted in GCP label values and the combination of `data-classification`, `data-domain`, and `regulatory-scope` carries the same information for resource-level decisions. Column-level and document-level metadata carry the full label.

## Microsoft Purview sensitivity labels

Sensitivity labels are the carrier for documents, email, containers, and, through the Purview Data Map, schematized data assets.

### What a label can do

| Capability | Applies to | Used for |
|---|---|---|
| Content marking (header, footer, watermark) | Files, email | Visual cue for C2 and C3 |
| Encryption with usage rights | Files, email | Persistent protection for C3 documents that travels with the file |
| Double Key Encryption (DKE) | Files, email | `Restricted\Secrets` content where Microsoft must not be able to decrypt |
| Container settings (privacy, external sharing, guest access, unmanaged device access) | Teams, Microsoft 365 groups, SharePoint sites | Sites for events and group sales that hold guest lists |
| Auto-labeling in Office apps (client-side) | Files, email being edited | Recommend or apply a label when sensitive information types are detected |
| Service-side auto-labeling | SharePoint, OneDrive, Exchange | Label files at rest and email in transit without user action |
| Labeling of schematized data assets | Purview Data Map assets (databases, storage) | Consistent labels shown in the catalog for structured data |

### Creating the taxonomy with PowerShell

Labels are created in the Purview portal or with Security and Compliance PowerShell. The example creates the `Restricted` parent and the `Restricted\Guest-Identity` sublabel with encryption.

```powershell
Connect-IPPSSession -UserPrincipalName admin@example.com

# Parent label
New-Label -Name "Restricted" -DisplayName "Restricted" `
  -Tooltip "Severe harm if disclosed. C3." -ContentType "File, Email"

$parent = Get-Label -Identity "Restricted"

# Sublabel with encryption: members of the identity data group get co-author rights
New-Label -Name "Restricted-Guest-Identity" -DisplayName "Guest-Identity" `
  -ParentId $parent.ImmutableId `
  -Tooltip "Passport, national ID, biometrics. C3." `
  -ContentType "File, Email" `
  -EncryptionEnabled $true `
  -EncryptionProtectionType Template `
  -EncryptionRightsDefinitions "guest-identity-readers@example.com:VIEW,VIEWRIGHTSDATA,DOCEDIT,EDIT,PRINT,EXTRACT,OBJMODEL" `
  -EncryptionContentExpiredOnDateInDaysOrNever Never `
  -EncryptionOfflineAccessDays 7 `
  -ApplyContentMarkingFooterEnabled $true `
  -ApplyContentMarkingFooterText "Restricted - Guest Identity"

# Publish the labels to users with a label policy
New-LabelPolicy -Name "Global labels" `
  -Labels "Public","Internal","Confidential","Restricted","Restricted-Guest-Identity" `
  -ExchangeLocation All
```

{: .verify }
Label cmdlet parameter names and the available encryption rights are documented in the Security and Compliance PowerShell reference. Confirm parameter names against the current module version before scripting production changes.

### Auto-labeling

Service-side auto-labeling runs in simulation first so that matches can be reviewed. The example applies `Restricted\PCI` to email and files containing credit card numbers.

```powershell
New-AutoSensitivityLabelPolicy -Name "Auto-label PCI" `
  -ApplySensitivityLabel "Restricted-PCI" `
  -ExchangeLocation All -SharePointLocation All -OneDriveLocation All `
  -Mode TestWithoutNotifications

New-AutoSensitivityLabelRule -Policy "Auto-label PCI" -Name "Card numbers" `
  -Workload Exchange `
  -ContentContainsSensitiveInformation @{Name="Credit Card Number"; minCount="1"; minConfidence="85"}
```

Rules are created per workload (Exchange, SharePoint, OneDriveForBusiness). After the simulation results are reviewed, the policy mode is changed to `Enable`.

Client-side auto-labeling is configured on the label itself in the portal, with a condition (sensitive information types or trainable classifiers) and a choice to recommend or apply automatically. The organization recommends for C2 and applies automatically for C3 information types with high-confidence matches.

### Labeling files outside Microsoft 365

For on-prem file shares, the Purview information protection scanner can apply labels in bulk. For individual files and scripted workflows, the Purview Information Protection client PowerShell module provides file-level cmdlets:

```powershell
# Inspect the current label and protection status
Get-FileStatus -Path "\\prop-fs01\frontdesk\scans\registration-2026-09.pdf"

# Apply a label by its ID
Set-FileLabel -Path "\\prop-fs01\frontdesk\scans\" -LabelId "<label-guid>" `
  -JustificationMessage "Bulk labeling of front desk scans"
```

### MIP SDK

The Microsoft Information Protection (MIP) SDK lets other applications read and apply labels and protection. Its main components are:

| SDK component | What it does | Organization use |
|---|---|---|
| File SDK | Read and write labels and protection on supported file types | The events platform labels exported rooming lists before they are emailed |
| Policy SDK | Evaluate label policy and compute actions without handling files | A custom upload service computes the required label for a document type |
| Protection SDK | Encrypt and decrypt content using the protection service | Line-of-business applications that store protected content |

Third-party DLP, CASB, and archiving products integrate through the SDK to honor Purview labels, which is how a single label taxonomy is enforced by several vendors.

### Labeling schematized data assets

Purview can extend sensitivity labels to assets in the Data Map, so that a database or storage account shows a label derived from the classifications found in it. This keeps the catalog view consistent with document labels. It is a catalog label, not an enforcement mechanism in the database; enforcement in the database comes from the column-level mechanisms later on this page.

{: .verify }
Extending sensitivity labels to Data Map assets has changed names and licensing across Purview releases. Confirm current availability and prerequisites.

## Cloud resource tags

### AWS: tags, tag policies, and SCPs

AWS tags are key-value pairs on resources. Two organization-level mechanisms govern them:

- **Tag policies** standardize tag keys, capitalization, and allowed values, report non-compliance, and can prevent non-compliant values on specified resource types.
- **Service control policies (SCPs)** can deny resource creation when a required tag is missing from the request, for services that support tag-on-create condition keys.

A tag policy for `data-classification`:

```json
{
  "tags": {
    "data-classification": {
      "tag_key": { "@@assign": "data-classification" },
      "tag_value": {
        "@@assign": ["public", "internal", "confidential", "restricted"]
      },
      "enforced_for": { "@@assign": ["s3:bucket"] }
    },
    "protection-profile": {
      "tag_key": { "@@assign": "protection-profile" },
      "tag_value": { "@@assign": ["pp1", "pp2", "pp3"] }
    }
  }
}
```

{: .note }
Tag policy enforcement (`enforced_for`) prevents non-compliant values from being set, but does not by itself require a tag to exist. Requiring the tag at creation is done with SCPs or with provisioning guardrails.

An SCP that denies creation of KMS keys, RDS instances, and EBS volumes without a valid classification tag:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "RequireClassificationTagOnCreate",
      "Effect": "Deny",
      "Action": [
        "kms:CreateKey",
        "rds:CreateDBInstance",
        "rds:CreateDBCluster",
        "ec2:CreateVolume",
        "dynamodb:CreateTable"
      ],
      "Resource": "*",
      "Condition": {
        "Null": { "aws:RequestTag/data-classification": "true" }
      }
    },
    {
      "Sid": "RequireValidClassificationValue",
      "Effect": "Deny",
      "Action": [
        "kms:CreateKey",
        "rds:CreateDBInstance",
        "rds:CreateDBCluster",
        "ec2:CreateVolume",
        "dynamodb:CreateTable"
      ],
      "Resource": "*",
      "Condition": {
        "StringNotEquals": {
          "aws:RequestTag/data-classification": ["public", "internal", "confidential", "restricted"]
        }
      }
    },
    {
      "Sid": "ProtectClassificationTagFromChange",
      "Effect": "Deny",
      "Action": ["tag:TagResources", "tag:UntagResources"],
      "Resource": "*",
      "Condition": {
        "ForAnyValue:StringEquals": { "aws:TagKeys": ["data-classification"] },
        "StringNotLike": { "aws:PrincipalArn": "arn:aws:iam::*:role/data-governance-tagger" }
      }
    }
  ]
}
```

{: .warning }
Not every AWS service supports `aws:RequestTag` on its create action, and some create tags in a separate API call after creation. Test each action in a sandbox organizational unit before attaching a deny SCP, or legitimate provisioning will fail. For S3 buckets, enforce tags through the provisioning pipeline and AWS Config rules if tag-on-create conditions are not supported for the action in use. The third statement is illustrative; per-service tagging actions (for example `s3:PutBucketTagging`) also need to be covered for complete protection.

Tagging a resource:

```bash
aws s3api put-bucket-tagging --bucket dl-raw-guest-eu-west-1 --tagging '{
  "TagSet": [
    {"Key": "data-classification", "Value": "restricted"},
    {"Key": "protection-profile",  "Value": "pp3"},
    {"Key": "data-domain",         "Value": "guest"},
    {"Key": "regulatory-scope",    "Value": "gdpr"},
    {"Key": "data-residency",      "Value": "eu"},
    {"Key": "data-owner",          "Value": "guest-platform"},
    {"Key": "retention-class",     "Value": "r3y"}
  ]
}'
```

Tags also drive access control through attribute-based access control (ABAC). A KMS key policy statement can allow a role to use only keys whose `data-domain` tag matches the role's principal tag:

```json
{
  "Sid": "AllowUseOfKeysInOwnDomain",
  "Effect": "Allow",
  "Principal": { "AWS": "arn:aws:iam::111122223333:root" },
  "Action": ["kms:Decrypt", "kms:GenerateDataKey"],
  "Resource": "*",
  "Condition": {
    "StringEquals": {
      "aws:ResourceTag/data-domain": "${aws:PrincipalTag/data-domain}"
    }
  }
}
```

### Azure: tags and Azure Policy

Azure tags are name-value pairs on subscriptions, resource groups, and resources. Tag names are case-insensitive and values are case-sensitive, so the lowercase convention avoids ambiguity. Azure Policy enforces them.

A custom policy that denies storage accounts, SQL databases, and Key Vaults without a valid `data-classification` value:

```json
{
  "mode": "Indexed",
  "policyRule": {
    "if": {
      "allOf": [
        {
          "field": "type",
          "in": [
            "Microsoft.Storage/storageAccounts",
            "Microsoft.Sql/servers/databases",
            "Microsoft.KeyVault/vaults",
            "Microsoft.DocumentDB/databaseAccounts"
          ]
        },
        {
          "not": {
            "field": "tags['data-classification']",
            "in": ["public", "internal", "confidential", "restricted"]
          }
        }
      ]
    },
    "then": { "effect": "deny" }
  }
}
```

Deploy and assign it at a management group:

```bash
az policy definition create \
  --name require-data-classification \
  --display-name "Require valid data-classification tag on data resources" \
  --mode Indexed \
  --rules policy-rule.json \
  --management-group corp-root

az policy assignment create \
  --name require-data-classification \
  --policy "/providers/Microsoft.Management/managementGroups/corp-root/providers/Microsoft.Authorization/policyDefinitions/require-data-classification" \
  --scope "/providers/Microsoft.Management/managementGroups/corp-root"
```

Built-in policies complement the custom rule: "Require a tag on resources", "Inherit a tag from the resource group if missing" (modify effect, useful for `data-owner` and `data-residency`), and "Add a tag to resources". Tagging with the CLI:

```bash
az tag update --resource-id "/subscriptions/<sub>/resourceGroups/rg-guest-eu/providers/Microsoft.Storage/storageAccounts/stguesteu01" \
  --operation Merge \
  --tags data-classification=restricted protection-profile=pp3 data-domain=guest \
         regulatory-scope=gdpr data-residency=eu data-owner=guest-platform retention-class=r3y
```

### Google Cloud: labels and tags are different

Google Cloud has two metadata mechanisms that are easy to confuse.

| Aspect | Labels | Tags (Resource Manager tags) |
|---|---|---|
| Structure | Key-value pairs set directly on a resource | Key and value are resources in their own right, defined at organization or project level, then bound to resources |
| Permissions to change | Anyone who can update the resource | Separate IAM permissions on the tag value (`roles/resourcemanager.tagUser`) |
| Inheritance | None | Inherited down the resource hierarchy (organization, folder, project, resource) |
| Usable in IAM conditions | No | Yes |
| Usable in organization policy conditions | No | Yes |
| Billing export and filtering | Yes | Yes (tags are also in billing export) |
| Character rules | Lowercase letters, digits, hyphens, underscores; limits on length | Short names are more permissive |

The organization uses both: **labels** for the full seven-key schema (filtering, billing, inventory), and **tags** for `data-classification` and `data-residency`, because those two drive IAM and organization policy decisions and must not be changeable by resource editors.

Labels:

```bash
gcloud storage buckets update gs://dl-raw-guest-eu \
  --update-labels=data-classification=restricted,protection-profile=pp3,data-domain=guest,regulatory-scope=gdpr,data-residency=eu,data-owner=guest-platform,retention-class=r3y

bq update --set_label data-classification:confidential \
  --set_label data-domain:guest guest-analytics-prod:guest_curated
```

Tags:

```bash
# Define the tag key and values at the organization
gcloud resource-manager tags keys create data-classification \
  --parent=organizations/123456789012 \
  --description="Data classification tier"

for v in public internal confidential restricted; do
  gcloud resource-manager tags values create "$v" \
    --parent=123456789012/data-classification
done

# Bind a tag value to a bucket
gcloud resource-manager tags bindings create \
  --tag-value=123456789012/data-classification/restricted \
  --parent=//storage.googleapis.com/projects/_/buckets/dl-raw-guest-eu \
  --location=europe-west1
```

An IAM condition can then restrict a role to resources carrying a tag value, for example granting analysts read access only where the tag is not `restricted`, using `resource.matchTag('123456789012/data-classification', 'confidential')` in the condition expression.

### OCI: defined tags, namespaces, and tag defaults

OCI supports freeform tags (unmanaged key-value pairs) and defined tags, which live in a tag namespace, have controlled keys, and can restrict values to a list. The organization uses defined tags in a namespace named `data-governance`.

```bash
# Create the namespace in the root compartment (tenancy)
oci iam tag-namespace create \
  --compartment-id ocid1.tenancy.oc1..aaaa... \
  --name data-governance \
  --description "Data classification and protection metadata"

# Create a tag key restricted to the allowed values
oci iam tag create \
  --tag-namespace-id ocid1.tagnamespace.oc1..aaaa... \
  --name data-classification \
  --description "Data classification tier" \
  --validator '{"validatorType":"ENUM","values":["public","internal","confidential","restricted"]}'

# Apply defined tags when creating a bucket
oci os bucket create \
  --compartment-id ocid1.compartment.oc1..aaaa... \
  --name fin-owner-statements \
  --defined-tags '{"data-governance":{"data-classification":"confidential","data-domain":"finance","data-residency":"us","protection-profile":"pp2"}}'
```

**Tag defaults** apply a defined tag value automatically to every resource created in a compartment, and can be marked as required so that the creator must supply a value. The organization sets `data-classification` as a required tag default in compartments that hold data stores, with `confidential` as the default value where the compartment's purpose is known.

OCI IAM policies can reference tags on the target resource in conditions, which allows domain-scoped key access similar to the AWS ABAC example.

{: .verify }
OCI tag key naming rules, the exact syntax for referencing defined tags with hyphens in IAM policy conditions, and the CLI flag for tag value validators should be confirmed against current OCI documentation. If hyphens cause issues in policy expressions, use a namespace and key naming variant without hyphens for OCI only and map it in the inventory.

### Cross-cloud tag enforcement summary

| Control | AWS | Azure | Google Cloud | OCI |
|---|---|---|---|---|
| Standardize keys and values | Tag policies | Azure Policy (audit or deny on value) | Tag keys and values as resources; label conventions checked by policy tooling | Defined tags with value validators |
| Require at creation | SCP with `aws:RequestTag` conditions; provisioning pipeline | Azure Policy deny | Organization policy custom constraints or provisioning pipeline; tags required through IaC | Required tag defaults |
| Inherit from parent | Not native (use IaC defaults) | Policy modify effect: inherit from resource group or subscription | Tags inherit through the hierarchy | Tag defaults per compartment |
| Protect from change | SCP on tagging actions | Azure RBAC and policy | Tag IAM permissions | IAM policy on tag namespace use |
| Use in access decisions | ABAC with `aws:ResourceTag` and `aws:PrincipalTag` | Azure ABAC conditions on storage; RBAC scopes | IAM conditions with `resource.matchTag` | IAM policy conditions on tags |
| Report compliance | Tag policy compliance reports, AWS Config | Azure Policy compliance | Cloud Asset Inventory queries | OCI Search queries |

## Column-level metadata

Column-level metadata is what makes masking and fine-grained access work in structured data. Each platform has its own mechanism; the organization maps all of them to the label taxonomy.

### BigQuery policy tags

Policy tags are defined in taxonomies and attached to columns in the table schema. With fine-grained access control activated on the taxonomy, a user needs the Fine-Grained Reader role on a policy tag to read the column in clear. Data policies attached to policy tags provide dynamic masking for users without that role.

```bash
# Create a taxonomy with fine-grained access control enabled
gcloud data-catalog taxonomies create \
  --location=eu \
  --display-name="data-classification" \
  --description="Organization label taxonomy" \
  --activated-policy-types=FINE_GRAINED_ACCESS_CONTROL
```

Attach a policy tag in the schema file and apply it:

```json
[
  {"name": "guest_id", "type": "STRING"},
  {"name": "email", "type": "STRING",
   "policyTags": {"names": ["projects/guest-analytics-prod/locations/eu/taxonomies/1111/policyTags/2222"]}},
  {"name": "passport_number", "type": "STRING",
   "policyTags": {"names": ["projects/guest-analytics-prod/locations/eu/taxonomies/1111/policyTags/3333"]}}
]
```

```bash
bq update guest-analytics-prod:guest_curated.profiles schema.json
```

Policy tag `2222` represents `Confidential\Guest-PII` and has a data policy that masks email with a hash for analysts. Policy tag `3333` represents `Restricted\Guest-Identity` and has no masked reader rule beyond nullification, so only named identity verification roles see values.

{: .verify }
Policy tag taxonomy management has been moving from Data Catalog to Dataplex. Confirm whether new taxonomies should be created through the Dataplex interfaces as of mid-2026.

### Snowflake object tags and tag-based masking

Snowflake tags are schema-level objects assigned to tables and columns. A masking policy assigned to a tag applies automatically to every column that carries the tag, which is the most direct label-to-control mechanism in any warehouse.

```sql
CREATE TAG governance.tags.data_classification
  ALLOWED_VALUES 'public', 'internal', 'confidential', 'restricted'
  COMMENT = 'Organization classification tier';

ALTER TABLE guest.core.profiles MODIFY COLUMN email
  SET TAG governance.tags.data_classification = 'confidential';

ALTER TABLE guest.core.profiles MODIFY COLUMN passport_number
  SET TAG governance.tags.data_classification = 'restricted';

CREATE MASKING POLICY governance.policies.mask_by_classification
  AS (val STRING) RETURNS STRING ->
  CASE
    WHEN SYSTEM$GET_TAG_ON_CURRENT_COLUMN('governance.tags.data_classification') = 'restricted'
         AND IS_ROLE_IN_SESSION('GUEST_IDENTITY_VERIFIER') THEN val
    WHEN SYSTEM$GET_TAG_ON_CURRENT_COLUMN('governance.tags.data_classification') = 'confidential'
         AND IS_ROLE_IN_SESSION('GUEST_PII_READER') THEN val
    WHEN SYSTEM$GET_TAG_ON_CURRENT_COLUMN('governance.tags.data_classification') IN ('public', 'internal') THEN val
    ELSE '***MASKED***'
  END;

ALTER TAG governance.tags.data_classification
  SET MASKING POLICY governance.policies.mask_by_classification;
```

Tag names in Snowflake use underscores because hyphens are not valid in unquoted identifiers. The inventory maps `data_classification` to `data-classification`.

### Databricks Unity Catalog tags

Unity Catalog supports tags on catalogs, schemas, tables, and columns. Column masks and row filters are SQL functions attached to columns and tables.

```sql
ALTER TABLE main.guest.profiles
  SET TAGS ('data-classification' = 'confidential', 'data-domain' = 'guest');

ALTER TABLE main.guest.profiles
  ALTER COLUMN passport_number SET TAGS ('data-classification' = 'restricted');

CREATE OR REPLACE FUNCTION main.governance.mask_restricted(val STRING)
  RETURN CASE WHEN is_account_group_member('guest-identity-verifiers') THEN val
              ELSE '***MASKED***' END;

ALTER TABLE main.guest.profiles
  ALTER COLUMN passport_number SET MASK main.governance.mask_restricted;
```

{: .verify }
Databricks has introduced attribute-based access control policies that apply masks based on tags (governed tags) rather than per column. Confirm availability and status before designing tag-driven masking in Unity Catalog; the per-column mask above works independently of that feature.

### AWS Lake Formation LF-tags

LF-tags are key-value tags managed by Lake Formation and attached to databases, tables, and columns in the Glue Data Catalog. Permissions are granted on LF-tag expressions, so new tables inherit access rules through their tags.

```bash
aws lakeformation create-lf-tag \
  --tag-key data-classification \
  --tag-values public internal confidential restricted

aws lakeformation add-lf-tags-to-resource \
  --resource '{"TableWithColumns": {"DatabaseName": "guest_curated", "Name": "profiles", "ColumnNames": ["passport_number"]}}' \
  --lf-tags '[{"TagKey": "data-classification", "TagValues": ["restricted"]}]'

# Analysts may select only columns tagged internal or confidential
aws lakeformation grant-permissions \
  --principal DataLakePrincipalIdentifier=arn:aws:iam::111122223333:role/analyst \
  --permissions SELECT \
  --resource '{"LFTagPolicy": {"ResourceType": "TABLE", "Expression": [{"TagKey": "data-classification", "TagValues": ["internal", "confidential"]}]}}'
```

### SQL Server and Azure SQL sensitivity classification

SQL Server 2019 and later, Azure SQL Database, and Azure SQL Managed Instance store classifications in the database. They appear in audit logs (the `data_sensitivity_information` field), so access to classified columns can be monitored.

```sql
ADD SENSITIVITY CLASSIFICATION TO
    dbo.GuestProfile.Email,
    dbo.GuestProfile.Phone
WITH (LABEL = 'Confidential\Guest-PII', INFORMATION_TYPE = 'Contact Info', RANK = MEDIUM);

ADD SENSITIVITY CLASSIFICATION TO
    dbo.GuestIdentity.PassportNumber
WITH (LABEL = 'Restricted\Guest-Identity', INFORMATION_TYPE = 'National ID', RANK = CRITICAL);

-- Remove a classification
DROP SENSITIVITY CLASSIFICATION FROM dbo.GuestProfile.Phone;
```

### Oracle Database

Oracle Data Safe sensitive data models record sensitive columns and types for Oracle databases, and feed Data Safe masking. For in-database enforcement, Oracle Data Redaction and Virtual Private Database policies are attached to the columns identified by the model. Oracle does not have a native column tag equivalent to Snowflake tags; the sensitive data model acts as the metadata store.

### Column-level mechanism comparison

| Platform | Metadata mechanism | Enforcement tied to metadata | Masking | Notes |
|---|---|---|---|---|
| BigQuery | Policy tags in taxonomies | Fine-grained reader role per policy tag | Data policies on policy tags | One policy tag per column |
| Snowflake | Object tags with allowed values | Tag-based masking policies | Masking policy functions | Most direct tag-to-control link |
| Databricks Unity Catalog | Tags on objects and columns | Column masks and row filters; tag-driven policies (verify) | SQL mask functions | |
| AWS Lake Formation | LF-tags | LF-tag based access control grants | Column exclusion; cell-level filters | Masking of values requires other tooling |
| SQL Server and Azure SQL | Sensitivity classifications | Auditing; enforcement by separate RLS, DDM, Always Encrypted | Dynamic data masking | Classification visible in audit logs |
| Oracle | Data Safe sensitive data models | Data Redaction, VPD | Data Redaction; Data Safe static masking | |
| Redshift | Tags on resources; dynamic data masking policies attached to columns | DDM policies attached to roles | Dynamic data masking | Resource tags are not column-level |

## Unstructured object and file metadata

### S3 object tags

S3 object tags (up to 10 per object) can drive IAM conditions, lifecycle rules, and replication. They are useful for mixed-content buckets, although the recommended pattern is one classification per bucket.

```bash
aws s3api put-object-tagging \
  --bucket dl-raw-guest-eu-west-1 \
  --key extracts/pms/2026-09-20/registration-cards.parquet \
  --tagging 'TagSet=[{Key=data-classification,Value=restricted},{Key=retention-class,Value=r90d}]'
```

A bucket policy statement can deny reads of `restricted` objects to principals without the right principal tag, using `s3:ExistingObjectTag/data-classification` in the condition.

### Azure blob index tags

Blob index tags are key-value attributes that are indexed and queryable across a storage account, and usable in lifecycle management filters and in Azure ABAC conditions.

```bash
az storage blob tag set \
  --account-name stguesteu01 \
  --container-name scans \
  --name 2026/09/registration-0001.pdf \
  --tags data-classification=restricted retention-class=r90d \
  --auth-mode login
```

### Google Cloud Storage and OCI Object Storage

Cloud Storage supports custom object metadata (key-value pairs) but not tags at the object level usable in IAM conditions; the organization therefore separates classifications by bucket and applies tags at the bucket level. OCI Object Storage supports user-defined object metadata (`opc-meta-*` headers) and tags at the bucket level; the same bucket-per-classification rule applies.

### File system metadata

On Windows file servers, the Purview label is stored inside Office and PDF files and survives copying. File Classification Infrastructure properties are stored in alternate data streams or file properties and do not reliably survive copying to other systems, so they are used for on-server management only.

## Keeping metadata correct over time

| Risk | Control |
|---|---|
| Tag removed or changed by a resource editor | Deny tag changes except by the governance role (SCP, GCP tag IAM, OCI namespace policy, Azure RBAC) |
| Tag says `internal` but discovery finds C3 data | Drift detection: discovery results compared with tags daily; mismatch raises a finding and, for C3, automatically raises the tag |
| New column added with sensitive content | Continuous column-level discovery; schema change hooks in CI for data pipelines |
| Label downgraded by a user | Purview requires justification for downgrades; activity explorer reports them |
| Copies lose metadata | Prefer carriers that travel (Purview labels in files); for exports, the pipeline sets tags on the target |

The repository's policy resolver treats a missing or invalid tag as `confidential` (the default-to-Confidential rule) and emits a finding. See [code/classification on GitHub](https://github.com/steven-smith-itnet/data-protection-pqc-security-architecture/tree/main/code/classification).

## Key takeaways for engineering teams

- Apply the seven-key tag schema exactly, in lowercase, on every data resource and every key; automation depends on exact values.
- In Google Cloud, use tags (not only labels) for `data-classification` and `data-residency`, because only tags can be used in IAM and organization policy conditions and protected from resource editors.
- Column-level metadata is what makes masking automatic; tag columns at creation in the pipeline, not after the fact.
- Test deny policies in a sandbox; not every cloud create action supports tag conditions.
- Purview labels are the only carrier that reliably travels with a file; use them for C2 and C3 documents.

## Related pages

- [Data classification scheme]({% link docs/01-prerequisites/classification.md %})
- [Label-to-control mapping]({% link docs/01-prerequisites/label-to-control.md %})
- [Guardrails and policy as code]({% link docs/08-engineering/policy-as-code.md %})
- [Microsoft 365 and collaboration]({% link docs/04-unstructured/m365-collaboration.md %})
- [Data lakes and analytics platforms]({% link docs/03-structured/analytics-platforms.md %})

## Sources

- AWS Organizations tag policies: <https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_tag-policies.html>
- Azure Policy tag definitions: <https://learn.microsoft.com/azure/governance/policy/tutorials/govern-tags>
- Google Cloud tags overview: <https://cloud.google.com/resource-manager/docs/tags/tags-overview>
- OCI tagging overview: <https://docs.oracle.com/iaas/Content/Tagging/Concepts/taggingoverview.htm>
- Microsoft Purview sensitivity labels: <https://learn.microsoft.com/purview/sensitivity-labels>
- BigQuery column-level access control: <https://cloud.google.com/bigquery/docs/column-level-security-intro>
- Snowflake tag-based masking policies: <https://docs.snowflake.com/en/user-guide/tag-based-masking-policies>
- AWS Lake Formation LF-tags: <https://docs.aws.amazon.com/lake-formation/latest/dg/tag-based-access-control.html>
- SQL Server ADD SENSITIVITY CLASSIFICATION: <https://learn.microsoft.com/sql/t-sql/statements/add-sensitivity-classification-transact-sql>
