# Label-driven encryption for Cloud Storage.
#
#   pp1  Google default encryption, uniform bucket-level access, public access
#        prevention enforced.
#   pp2  CMEK with the data domain's Cloud KMS key, HSM protection level.
#   pp3  pp2 plus object versioning.
#        For customer-held keys, replace the key with a Cloud EKM key
#        (protection level EXTERNAL or EXTERNAL_VPC).
#
# Separation of duties: admins get roles/cloudkms.admin on the key ring; only
# the Cloud Storage service agent gets cryptoKeyEncrypterDecrypter, per key.

data "google_storage_project_service_account" "gcs" {
  project = var.project_id
}

resource "google_kms_key_ring" "data" {
  count = length(local.cmk_domains) > 0 ? 1 : 0

  name     = "${var.name_prefix}-${var.environment}-data"
  location = var.location
  project  = var.project_id
}

resource "google_kms_key_ring_iam_binding" "admins" {
  count = length(local.cmk_domains) > 0 ? 1 : 0

  key_ring_id = google_kms_key_ring.data[0].id
  role        = "roles/cloudkms.admin"
  members     = var.key_admins
}

resource "google_kms_crypto_key" "domain" {
  for_each = local.cmk_domains

  name                       = "${each.key}-kek"
  key_ring                   = google_kms_key_ring.data[0].id
  purpose                    = "ENCRYPT_DECRYPT"
  rotation_period            = var.rotation_period
  destroy_scheduled_duration = var.destroy_scheduled_duration

  version_template {
    algorithm        = "GOOGLE_SYMMETRIC_ENCRYPTION"
    protection_level = "HSM"
  }

  labels = {
    "data-classification" = local.domain_classification[each.key]
    "data-domain"         = each.key
    "environment"         = var.environment
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_kms_crypto_key_iam_member" "gcs_agent" {
  for_each = local.cmk_domains

  crypto_key_id = google_kms_crypto_key.domain[each.key].id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${data.google_storage_project_service_account.gcs.email_address}"
}

resource "google_storage_bucket" "dataset" {
  for_each = local.datasets

  name                        = "${var.name_prefix}-${var.environment}-${each.key}"
  project                     = var.project_id
  location                    = var.location
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  labels                      = local.dataset_tags[each.key]

  dynamic "encryption" {
    for_each = each.value.protection_profile == "pp1" ? [] : [1]
    content {
      default_kms_key_name = google_kms_crypto_key.domain[each.value.data_domain].id
    }
  }

  versioning {
    enabled = each.value.protection_profile == "pp3"
  }

  depends_on = [google_kms_crypto_key_iam_member.gcs_agent]
}
