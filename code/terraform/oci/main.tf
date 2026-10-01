# Label-driven encryption for OCI Object Storage.
#
#   pp1  Oracle-managed keys, no public access.
#   pp2  Customer-managed AES-256 master encryption key in OCI Vault,
#        HSM protection mode, one key per data domain.
#   pp3  pp2 plus the key in a virtual private vault (isolated HSM partition)
#        and object versioning. For customer-held keys, OCI External KMS is
#        the option to evaluate (verify regional availability).
#
# Separation of duties: the admin group manages vaults and keys; the user
# group can only associate keys (key-delegate); the Object Storage service
# can use only the listed keys.

data "oci_objectstorage_namespace" "ns" {
  compartment_id = var.compartment_id
}

locals {
  pp3_present = anytrue([for d in local.datasets : d.protection_profile == "pp3"])
  vault_type  = local.pp3_present && var.use_private_vault_for_pp3 ? "VIRTUAL_PRIVATE" : "DEFAULT"
}

resource "oci_kms_vault" "data" {
  count = length(local.cmk_domains) > 0 ? 1 : 0

  compartment_id = var.compartment_id
  display_name   = "${var.name_prefix}-${var.environment}-data-vault"
  vault_type     = local.vault_type
  freeform_tags = {
    "environment" = var.environment
  }
}

resource "oci_kms_key" "domain" {
  for_each = local.cmk_domains

  compartment_id      = var.compartment_id
  display_name        = "${var.name_prefix}-${var.environment}-${each.key}-mek"
  management_endpoint = oci_kms_vault.data[0].management_endpoint
  protection_mode     = "HSM"

  key_shape {
    algorithm = "AES"
    length    = 32
  }

  is_auto_rotation_enabled = true
  auto_key_rotation_details {
    rotation_interval_in_days = var.rotation_interval_in_days
  }

  freeform_tags = {
    "data-classification" = local.domain_classification[each.key]
    "data-domain"         = each.key
    "environment"         = var.environment
  }
}

resource "oci_identity_policy" "keys" {
  count = length(local.cmk_domains) > 0 ? 1 : 0

  compartment_id = var.compartment_id
  name           = "${var.name_prefix}-${var.environment}-data-keys"
  description    = "Separate key administration from key use for label-driven encryption."
  statements = concat(
    [
      "Allow group ${var.key_admin_group} to manage vaults in compartment ${var.compartment_name}",
      "Allow group ${var.key_admin_group} to manage keys in compartment ${var.compartment_name}",
      "Allow group ${var.key_user_group} to use key-delegate in compartment ${var.compartment_name}",
    ],
    [
      for dom, k in oci_kms_key.domain :
      "Allow service objectstorage-${var.region} to use keys in compartment ${var.compartment_name} where target.key.id = '${k.id}'"
    ]
  )
}

resource "oci_objectstorage_bucket" "dataset" {
  for_each = local.datasets

  compartment_id = var.compartment_id
  namespace      = data.oci_objectstorage_namespace.ns.namespace
  name           = "${var.name_prefix}-${var.environment}-${each.key}"
  access_type    = "NoPublicAccess"
  kms_key_id     = each.value.protection_profile == "pp1" ? null : oci_kms_key.domain[each.value.data_domain].id
  versioning     = each.value.protection_profile == "pp3" ? "Enabled" : "Disabled"
  freeform_tags  = local.dataset_tags[each.key]

  depends_on = [oci_identity_policy.keys]
}
