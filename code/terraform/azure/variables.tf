variable "name_prefix" {
  description = "Short prefix for resource names. Storage account names are 3 to 24 lowercase letters and digits, so keep this short."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9]{2,7}$", var.name_prefix))
    error_message = "name_prefix must be 3 to 8 lowercase letters or digits."
  }
}

variable "resource_group_name" {
  description = "Existing resource group for the vault, identities, and storage accounts."
  type        = string
}

variable "location" {
  description = "Azure region, for example westeurope."
  type        = string
}

variable "tenant_id" {
  description = "Entra ID tenant ID for the Key Vault."
  type        = string
}

variable "key_admin_principal_ids" {
  description = "Object IDs granted Key Vault Crypto Officer (manage keys, no data-plane use by the storage identity path)."
  type        = list(string)

  validation {
    condition     = length(var.key_admin_principal_ids) > 0
    error_message = "At least one key administrator is required."
  }
}

variable "soft_delete_retention_days" {
  description = "Key Vault soft-delete retention (7 to 90). Purge protection is always on."
  type        = number
  default     = 90

  validation {
    condition     = var.soft_delete_retention_days >= 7 && var.soft_delete_retention_days <= 90
    error_message = "soft_delete_retention_days must be between 7 and 90."
  }
}

variable "key_expire_after" {
  description = "ISO 8601 duration after which a key version expires; rotation happens 30 days before."
  type        = string
  default     = "P365D"
}
