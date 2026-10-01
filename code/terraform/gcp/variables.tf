variable "name_prefix" {
  description = "Prefix for bucket and key ring names (bucket names are global)."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{2,20}$", var.name_prefix))
    error_message = "name_prefix must be 3 to 21 lowercase letters, digits, or hyphens."
  }
}

variable "project_id" {
  description = "Project that holds the key ring and buckets."
  type        = string
}

variable "location" {
  description = "Location for the key ring and buckets. CMEK keys must be in the same location as the bucket (for example europe-west1, or the multi-region eu)."
  type        = string
}

variable "key_admins" {
  description = "Members granted roles/cloudkms.admin on the key ring (manage, no encrypt or decrypt), e.g. group:kms-admins@example.com."
  type        = list(string)

  validation {
    condition     = length(var.key_admins) > 0
    error_message = "At least one key administrator is required."
  }
}

variable "rotation_period" {
  description = "Automatic rotation period in seconds with an s suffix. Default 365 days."
  type        = string
  default     = "31536000s"
}

variable "destroy_scheduled_duration" {
  description = "Time a key version stays in DESTROY_SCHEDULED before destruction. Default 30 days."
  type        = string
  default     = "2592000s"
}
