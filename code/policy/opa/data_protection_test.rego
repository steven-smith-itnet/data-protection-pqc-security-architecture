package terraform.data_protection_test

import rego.v1

import data.terraform.data_protection

# Fixtures are real `terraform show -json` plans produced offline from
# code/terraform/aws/examples/offline-plan (compliant) and
# code/terraform/aws/examples/noncompliant-plan (deliberately non-compliant).
compliant := data.fixtures.aws_compliant

noncompliant := data.fixtures.aws_noncompliant

denials(plan) := msgs if {
	msgs := data_protection.deny with input as plan
}

has(msgs, fragment) if {
	some m in msgs
	contains(m, fragment)
}

# ---- real plan fixtures ----------------------------------------------------

test_compliant_module_plan_has_no_denials if {
	count(denials(compliant)) == 0
}

test_restricted_requires_pp3 if {
	has(denials(noncompliant), "aws_s3_bucket.cards: data-classification=restricted requires protection-profile=pp3")
}

test_restricted_requires_cmk if {
	has(denials(noncompliant), "aws_s3_bucket.cards: restricted data must use SSE-KMS or DSSE-KMS")
}

test_public_access_block_off_denied if {
	has(denials(noncompliant), "aws_s3_bucket.cards: public access block setting block_public_policy is not true")
}

test_missing_public_access_block_denied if {
	has(denials(noncompliant), "aws_s3_bucket.untagged: no S3 public access block")
}

test_public_acl_denied if {
	has(denials(noncompliant), "public ACL \"public-read\" is not allowed")
}

test_missing_classification_denied if {
	has(denials(noncompliant), "aws_s3_bucket.untagged: missing or invalid data-classification tag")
}

test_kms_rotation_required if {
	has(denials(noncompliant), "aws_kms_key.unrotated: automatic key rotation must be enabled")
}

test_noncompliant_total if {
	count(denials(noncompliant)) == 11
}

# ---- small inline cases ----------------------------------------------------

bucket(tags) := {
	"address": "aws_s3_bucket.b",
	"mode": "managed",
	"type": "aws_s3_bucket",
	"name": "b",
	"change": {"actions": ["create"], "after": {"tags": tags}, "after_unknown": {}},
}

pab := {
	"address": "aws_s3_bucket_public_access_block.b",
	"mode": "managed",
	"type": "aws_s3_bucket_public_access_block",
	"name": "b",
	"change": {"actions": ["create"], "after": {
		"block_public_acls": true, "block_public_policy": true,
		"ignore_public_acls": true, "restrict_public_buckets": true,
	}},
}

sse(alg, key) := {
	"address": "aws_s3_bucket_server_side_encryption_configuration.b",
	"mode": "managed",
	"type": "aws_s3_bucket_server_side_encryption_configuration",
	"name": "b",
	"change": {"actions": ["create"], "after": {"rule": [{"apply_server_side_encryption_by_default": [{"sse_algorithm": alg, "kms_master_key_id": key}]}]}, "after_unknown": {}},
}

test_dsse_kms_with_key_allowed if {
	plan := {"resource_changes": [
		bucket({"data-classification": "restricted", "protection-profile": "pp3"}),
		pab,
		sse("aws:kms:dsse", "arn:aws:kms:eu-west-1:111122223333:key/example"),
	]}
	count(denials(plan)) == 0
}

test_kms_without_key_id_denied if {
	plan := {"resource_changes": [
		bucket({"data-classification": "confidential", "protection-profile": "pp2"}),
		pab,
		sse("aws:kms", null),
	]}
	has(denials(plan), "confidential data must use SSE-KMS or DSSE-KMS")
}

test_confidential_without_encryption_resource_denied if {
	plan := {"resource_changes": [bucket({"data-classification": "confidential", "protection-profile": "pp2"}), pab]}
	has(denials(plan), "none found")
}

test_internal_bucket_needs_no_cmk if {
	plan := {"resource_changes": [bucket({"data-classification": "internal", "protection-profile": "pp1"}), pab]}
	count(denials(plan)) == 0
}

test_delete_actions_ignored if {
	b := bucket({})
	deleted := object.union(b, {"change": {"actions": ["delete"], "after": null}})
	count(denials({"resource_changes": [deleted]})) == 0
}

test_gcp_restricted_bucket_without_cmek_denied if {
	plan := {"resource_changes": [{
		"address": "google_storage_bucket.g",
		"mode": "managed",
		"type": "google_storage_bucket",
		"name": "g",
		"change": {
			"actions": ["create"], "after": {
				"labels": {"data-classification": "restricted", "protection-profile": "pp3"},
				"encryption": [],
				"public_access_prevention": "inherited",
			},
			"after_unknown": {},
		},
	}]}
	msgs := denials(plan)
	has(msgs, "must use CMEK")
	has(msgs, "public_access_prevention must be enforced")
}

test_azure_confidential_with_cmk_allowed if {
	plan := {"resource_changes": [{
		"address": "azurerm_storage_account.a",
		"mode": "managed",
		"type": "azurerm_storage_account",
		"name": "a",
		"change": {
			"actions": ["create"], "after": {
				"tags": {"data-classification": "confidential", "protection-profile": "pp2"},
				"customer_managed_key": [{"key_vault_key_id": "https://kv.example/keys/guest"}],
				"allow_nested_items_to_be_public": false,
			},
			"after_unknown": {},
		},
	}]}
	count(denials(plan)) == 0
}
