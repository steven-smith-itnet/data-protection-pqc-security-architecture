output "vault_type" {
  description = "DEFAULT or VIRTUAL_PRIVATE, chosen from the highest protection profile present."
  value       = length(oci_kms_vault.data) > 0 ? oci_kms_vault.data[0].vault_type : null
}

output "key_ids" {
  description = "Master encryption key OCID per data domain."
  value       = { for dom, k in oci_kms_key.domain : dom => k.id }
}

output "buckets" {
  description = "Per dataset: bucket name, protection profile, and key (null means Oracle-managed keys)."
  value = {
    for name, d in local.datasets : name => {
      bucket             = oci_objectstorage_bucket.dataset[name].name
      protection_profile = d.protection_profile
      kms_key_id         = d.protection_profile == "pp1" ? null : oci_kms_key.domain[d.data_domain].id
    }
  }
}
