output "crypto_key_ids" {
  description = "Cloud KMS key ID per data domain."
  value       = { for dom, k in google_kms_crypto_key.domain : dom => k.id }
}

output "buckets" {
  description = "Per dataset: bucket name, protection profile, and CMEK key (null means Google default encryption)."
  value = {
    for name, d in local.datasets : name => {
      bucket             = google_storage_bucket.dataset[name].name
      protection_profile = d.protection_profile
      kms_key            = d.protection_profile == "pp1" ? null : google_kms_crypto_key.domain[d.data_domain].id
    }
  }
}
