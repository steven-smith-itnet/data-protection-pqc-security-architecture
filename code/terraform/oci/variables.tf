variable "name_prefix" {
  description = "Prefix for vault, key, and bucket names."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{2,20}$", var.name_prefix))
    error_message = "name_prefix must be 3 to 21 lowercase letters, digits, or hyphens."
  }
}

variable "compartment_id" {
  description = "OCID of the compartment for the vault, keys, buckets, and policy."
  type        = string
}

variable "compartment_name" {
  description = "Compartment name as used in IAM policy statements."
  type        = string
}

variable "region" {
  description = "Region identifier, e.g. eu-frankfurt-1 (used in the Object Storage service principal name)."
  type        = string
}

variable "key_admin_group" {
  description = "IAM group that manages vaults and keys (no data access)."
  type        = string
}

variable "key_user_group" {
  description = "IAM group allowed to use keys through key delegation (associate keys with buckets)."
  type        = string
}

variable "rotation_interval_in_days" {
  description = "Automatic key rotation interval."
  type        = number
  default     = 365
}

variable "use_private_vault_for_pp3" {
  description = "Create a virtual private vault (dedicated HSM partition, higher cost) when any dataset is pp3."
  type        = bool
  default     = true
}
