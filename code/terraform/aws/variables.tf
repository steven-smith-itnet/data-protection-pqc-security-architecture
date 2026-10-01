variable "name_prefix" {
  description = "Prefix for bucket names and key aliases (S3 bucket names are global)."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{2,20}$", var.name_prefix))
    error_message = "name_prefix must be 3 to 21 lowercase letters, digits, or hyphens."
  }
}

variable "account_id" {
  description = "AWS account ID that owns the keys. Passed in rather than looked up so the module plans offline."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "account_id must be 12 digits."
  }
}

variable "region" {
  description = "Region of the buckets; used for the kms:ViaService condition."
  type        = string
}

variable "key_admin_arns" {
  description = "IAM principals that administer keys (no encrypt or decrypt). Must include the principal running Terraform, or the key policy lockout check fails."
  type        = list(string)

  validation {
    condition     = length(var.key_admin_arns) > 0
    error_message = "At least one key administrator is required."
  }
}

variable "key_user_arns" {
  description = "Map of data domain to IAM principals allowed to use that domain's key through S3 (encrypt, decrypt, generate data key)."
  type        = map(list(string))
  default     = {}
}

variable "deletion_window_in_days" {
  description = "Waiting period before a scheduled key deletion completes (7 to 30)."
  type        = number
  default     = 30

  validation {
    condition     = var.deletion_window_in_days >= 7 && var.deletion_window_in_days <= 30
    error_message = "deletion_window_in_days must be between 7 and 30."
  }
}

variable "rotation_period_in_days" {
  description = "Automatic rotation period for customer managed keys (90 to 2560)."
  type        = number
  default     = 365

  validation {
    condition     = var.rotation_period_in_days >= 90 && var.rotation_period_in_days <= 2560
    error_message = "rotation_period_in_days must be between 90 and 2560."
  }
}

variable "custom_key_store_id" {
  description = "Optional CloudHSM or external (XKS) custom key store ID. When set, keys for domains that hold pp3 data are created in it."
  type        = string
  default     = null
}

variable "break_glass_role_arn" {
  description = "The only principal allowed to schedule key deletion (matches the SCP exception in code/policy/aws-scp/)."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:iam::[0-9]{12}:role/.+$", var.break_glass_role_arn))
    error_message = "break_glass_role_arn must be an IAM role ARN."
  }
}
