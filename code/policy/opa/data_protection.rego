# Data protection guardrails evaluated against Terraform plan JSON
# (`terraform show -json tfplan`). Phase 7: policy as code.
#
# Rules (each produces a message in `deny`):
#   1. data-classification must be present and valid on buckets, storage
#      accounts, and customer-managed keys.
#   2. data-classification=restricted requires protection-profile=pp3.
#   3. confidential and restricted storage must use a customer-managed key
#      (AWS SSE-KMS or DSSE-KMS with a key ID; Azure customer_managed_key;
#      GCP encryption.default_kms_key_name).
#   4. No public buckets: AWS public access block fully on and no public ACL;
#      GCP public access prevention enforced; Azure nested public access off.
#   5. AWS KMS keys have automatic rotation on.
#
# AWS companion resources (encryption configuration, public access block) are
# linked to their bucket by module address, resource name, and index, which is
# the convention used in code/terraform/aws. A confidential or restricted
# bucket with no linked encryption resource is denied (fail closed).
package terraform.data_protection

import rego.v1

allowed_classifications := {"public", "internal", "confidential", "restricted"}

cmk_required := {"confidential", "restricted"}

public_acls := {"public-read", "public-read-write", "authenticated-read"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

resources contains rc if {
	some rc in input.resource_changes
	rc.mode == "managed"
	not is_delete(rc)
}

is_delete(rc) if rc.change.actions == ["delete"]

after(rc) := object.get(rc.change, "after", {})

after_unknown(rc) := object.get(rc.change, "after_unknown", {})

# Tags (AWS, Azure), labels (GCP), or freeform tags (OCI); null becomes {}.
tags(rc) := t if {
	t := after(rc).tags
	is_object(t)
} else := t if {
	t := after(rc).tags_all
	is_object(t)
} else := t if {
	t := after(rc).labels
	is_object(t)
} else := t if {
	t := after(rc).freeform_tags
	is_object(t)
} else := {}

classification(rc) := object.get(tags(rc), "data-classification", "")

link_key(rc) := [object.get(rc, "module_address", ""), rc.name, object.get(rc, "index", null)]

by_type(t) := {link_key(rc): rc | some rc in resources; rc.type == t}

tagged_types := {
	"aws_s3_bucket",
	"aws_kms_key",
	"azurerm_storage_account",
	"azurerm_key_vault_key",
	"google_storage_bucket",
	"google_kms_crypto_key",
	"oci_objectstorage_bucket",
	"oci_kms_key",
}

# ---------------------------------------------------------------------------
# Rule 1: classification tag present and valid
# ---------------------------------------------------------------------------

deny contains msg if {
	some rc in resources
	rc.type in tagged_types
	not classification(rc) in allowed_classifications
	msg := sprintf("%s: missing or invalid data-classification tag (found %q)", [rc.address, classification(rc)])
}

# ---------------------------------------------------------------------------
# Rule 2: restricted requires pp3
# ---------------------------------------------------------------------------

deny contains msg if {
	some rc in resources
	rc.type in tagged_types
	classification(rc) == "restricted"
	pp := object.get(tags(rc), "protection-profile", "")
	pp != "pp3"
	msg := sprintf("%s: data-classification=restricted requires protection-profile=pp3 (found %q)", [rc.address, pp])
}

# ---------------------------------------------------------------------------
# Rule 3: customer-managed keys for confidential and restricted data
# ---------------------------------------------------------------------------

# AWS: the linked encryption configuration must use aws:kms or aws:kms:dsse
# with a key ID that is either set or computed at apply time.
aws_sse_ok(sse) if {
	some i
	rule := after(sse).rule[i]
	default_enc := rule.apply_server_side_encryption_by_default[0]
	default_enc.sse_algorithm in {"aws:kms", "aws:kms:dsse"}
	aws_kms_key_set(sse, i, default_enc)
}

aws_kms_key_set(_, _, default_enc) if {
	is_string(default_enc.kms_master_key_id)
	default_enc.kms_master_key_id != ""
}

aws_kms_key_set(sse, i, _) if {
	after_unknown(sse).rule[i].apply_server_side_encryption_by_default[0].kms_master_key_id == true
}

deny contains msg if {
	some key, bucket in by_type("aws_s3_bucket")
	classification(bucket) in cmk_required
	not by_type("aws_s3_bucket_server_side_encryption_configuration")[key]
	msg := sprintf("%s: %s data needs an encryption configuration with a customer managed KMS key; none found", [bucket.address, classification(bucket)])
}

deny contains msg if {
	some key, bucket in by_type("aws_s3_bucket")
	classification(bucket) in cmk_required
	sse := by_type("aws_s3_bucket_server_side_encryption_configuration")[key]
	not aws_sse_ok(sse)
	msg := sprintf("%s: %s data must use SSE-KMS or DSSE-KMS with a customer managed KMS key", [bucket.address, classification(bucket)])
}

# Azure: customer_managed_key block present (known or computed).
deny contains msg if {
	some rc in resources
	rc.type == "azurerm_storage_account"
	classification(rc) in cmk_required
	count(object.get(after(rc), "customer_managed_key", [])) == 0
	msg := sprintf("%s: %s data must use a customer-managed key", [rc.address, classification(rc)])
}

# GCP: encryption.default_kms_key_name set or computed.
gcp_cmek(rc) if {
	name := after(rc).encryption[0].default_kms_key_name
	is_string(name)
	name != ""
}

gcp_cmek(rc) if after_unknown(rc).encryption[0].default_kms_key_name == true

deny contains msg if {
	some rc in resources
	rc.type == "google_storage_bucket"
	classification(rc) in cmk_required
	not gcp_cmek(rc)
	msg := sprintf("%s: %s data must use CMEK (encryption.default_kms_key_name)", [rc.address, classification(rc)])
}

# ---------------------------------------------------------------------------
# Rule 4: no public buckets
# ---------------------------------------------------------------------------

pab_fields := ["block_public_acls", "block_public_policy", "ignore_public_acls", "restrict_public_buckets"]

deny contains msg if {
	some key, bucket in by_type("aws_s3_bucket")
	not by_type("aws_s3_bucket_public_access_block")[key]
	msg := sprintf("%s: no S3 public access block", [bucket.address])
}

deny contains msg if {
	some key, bucket in by_type("aws_s3_bucket")
	pab := by_type("aws_s3_bucket_public_access_block")[key]
	some field in pab_fields
	object.get(after(pab), field, false) != true
	msg := sprintf("%s: public access block setting %s is not true", [bucket.address, field])
}

deny contains msg if {
	some rc in resources
	rc.type == "aws_s3_bucket_acl"
	after(rc).acl in public_acls
	msg := sprintf("%s: public ACL %q is not allowed", [rc.address, after(rc).acl])
}

deny contains msg if {
	some rc in resources
	rc.type == "google_storage_bucket"
	object.get(after(rc), "public_access_prevention", "") != "enforced"
	msg := sprintf("%s: public_access_prevention must be enforced", [rc.address])
}

deny contains msg if {
	some rc in resources
	rc.type == "azurerm_storage_account"
	object.get(after(rc), "allow_nested_items_to_be_public", true) != false
	msg := sprintf("%s: allow_nested_items_to_be_public must be false", [rc.address])
}

# ---------------------------------------------------------------------------
# Rule 5: KMS key rotation
# ---------------------------------------------------------------------------

deny contains msg if {
	some rc in resources
	rc.type == "aws_kms_key"
	object.get(after(rc), "key_usage", "ENCRYPT_DECRYPT") == "ENCRYPT_DECRYPT"
	object.get(after(rc), "customer_master_key_spec", "SYMMETRIC_DEFAULT") == "SYMMETRIC_DEFAULT"
	object.get(after(rc), "enable_key_rotation", false) != true
	msg := sprintf("%s: automatic key rotation must be enabled", [rc.address])
}
