# ---------------------------------------------------------------------------
# Tag schema (identical in the aws, azure, gcp, and oci modules).
# Values mirror code/classification/label_policy.yaml; change them together.
# ---------------------------------------------------------------------------

variable "environment" {
  description = "Environment name, used in resource names and the environment tag."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,15}$", var.environment))
    error_message = "environment must be 2 to 16 lowercase letters, digits, or hyphens."
  }
}

variable "datasets" {
  description = <<-EOT
    Map of dataset name to its data tags. Each dataset gets one storage
    container encrypted according to its protection profile:
      pp1 (public, internal)  provider-managed encryption
      pp2 (confidential)      customer-managed key for the data domain
      pp3 (restricted)        customer-managed key for the data domain plus the
                              module's additional pp3 controls
    protection_profile may be set higher than the classification requires,
    never lower.
  EOT
  type = map(object({
    data_domain         = string
    data_classification = string
    regulatory_scope    = string
    data_owner          = string
    data_residency      = string
    retention_class     = string
    protection_profile  = optional(string)
  }))

  validation {
    condition     = alltrue([for k, _ in var.datasets : can(regex("^[a-z0-9][a-z0-9-]{1,30}$", k))])
    error_message = "dataset names must be 2 to 31 lowercase letters, digits, or hyphens."
  }
  validation {
    condition = alltrue([for d in var.datasets : contains(
      ["guest", "payment", "loyalty", "employee", "finance", "operations", "property-iot", "security"],
    d.data_domain)])
    error_message = "data_domain must be one of: guest, payment, loyalty, employee, finance, operations, property-iot, security."
  }
  validation {
    condition     = alltrue([for d in var.datasets : contains(["public", "internal", "confidential", "restricted"], d.data_classification)])
    error_message = "data_classification must be one of: public, internal, confidential, restricted."
  }
  validation {
    condition     = alltrue([for d in var.datasets : can(regex("^(none|(pci|gdpr|ccpa|pipl|lgpd)(_(pci|gdpr|ccpa|pipl|lgpd))*)$", d.regulatory_scope))])
    error_message = "regulatory_scope must be none, or one or more of pci, gdpr, ccpa, pipl, lgpd joined by '_' (for example pci_gdpr)."
  }
  validation {
    condition     = alltrue([for d in var.datasets : !strcontains(d.regulatory_scope, "pci") || d.data_classification == "restricted"])
    error_message = "regulatory_scope containing pci requires data_classification = restricted."
  }
  validation {
    condition     = alltrue([for d in var.datasets : can(regex("^[a-z0-9][a-z0-9_-]{1,62}$", d.data_owner))])
    error_message = "data_owner must be a lowercase team slug, for example guest-platform."
  }
  validation {
    condition     = alltrue([for d in var.datasets : contains(["us", "eu", "uk", "cn", "apac", "latam", "mea", "global"], d.data_residency)])
    error_message = "data_residency must be one of: us, eu, uk, cn, apac, latam, mea, global."
  }
  validation {
    condition     = alltrue([for d in var.datasets : contains(["r90d", "r1y", "r3y", "r7y", "r10y", "legal-hold"], d.retention_class)])
    error_message = "retention_class must be one of: r90d, r1y, r3y, r7y, r10y, legal-hold."
  }
  validation {
    condition = alltrue([for d in var.datasets :
      d.protection_profile == null ? true : (
        contains(["pp1", "pp2", "pp3"], coalesce(d.protection_profile, "pp1")) &&
        tonumber(substr(coalesce(d.protection_profile, "pp1"), 2, 1)) >= lookup({ public = 1, internal = 1, confidential = 2, restricted = 3 }, d.data_classification, 3)
      )
    ])
    error_message = "protection_profile must be pp1, pp2, or pp3 and not weaker than the classification requires (confidential = pp2, restricted = pp3)."
  }
}

locals {
  required_profile = { public = "pp1", internal = "pp1", confidential = "pp2", restricted = "pp3" }

  datasets = {
    for name, d in var.datasets : name => merge(d, {
      protection_profile = coalesce(d.protection_profile, local.required_profile[d.data_classification])
    })
  }

  # Data domains that need a customer-managed key (any pp2 or pp3 dataset).
  cmk_domains = toset([for d in local.datasets : d.data_domain if d.protection_profile != "pp1"])

  # Highest classification stored under each CMK domain; tags the key itself.
  domain_classification = {
    for dom in local.cmk_domains : dom => (
      anytrue([for d in local.datasets : d.data_domain == dom && d.protection_profile == "pp3"]) ? "restricted" : "confidential"
    )
  }

  dataset_tags = {
    for name, d in local.datasets : name => {
      "data-classification" = d.data_classification
      "protection-profile"  = d.protection_profile
      "data-domain"         = d.data_domain
      "regulatory-scope"    = d.regulatory_scope
      "data-owner"          = d.data_owner
      "data-residency"      = d.data_residency
      "retention-class"     = d.retention_class
      "environment"         = var.environment
    }
  }
}
