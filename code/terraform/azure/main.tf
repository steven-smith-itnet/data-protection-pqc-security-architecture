# Label-driven encryption for Azure Storage.
#
#   pp1  Microsoft-managed keys, TLS 1.2 minimum, no public blob access.
#   pp2  Customer-managed key (RSA-HSM, Key Vault Premium) for the data domain,
#        used through a user-assigned identity per storage account.
#   pp3  pp2 plus infrastructure encryption (a second encryption layer).
#        For stronger isolation, point a pp3 domain at Managed HSM instead.
#
# Separation of duties: admins get Key Vault Crypto Officer on the vault; the
# storage identities get Key Vault Crypto Service Encryption User on their own
# domain's key only.

locals {
  pp3_datasets = toset([for name, d in local.datasets : name if d.protection_profile == "pp3"])
  # Storage account names: prefix + env + dataset, letters and digits only, max 24.
  account_names = {
    for name, _ in local.datasets : name => substr(replace("${var.name_prefix}${var.environment}${name}", "-", ""), 0, 24)
  }
}

resource "azurerm_key_vault" "data" {
  count = length(local.cmk_domains) > 0 ? 1 : 0

  name                       = "${var.name_prefix}-${var.environment}-dp-kv"
  location                   = var.location
  resource_group_name        = var.resource_group_name
  tenant_id                  = var.tenant_id
  sku_name                   = "premium" # HSM-backed keys (RSA-HSM)
  rbac_authorization_enabled = true
  purge_protection_enabled   = true
  soft_delete_retention_days = var.soft_delete_retention_days
  tags = {
    "protection-profile" = "pp2"
    "environment"        = var.environment
  }
}

resource "azurerm_role_assignment" "key_admin" {
  for_each = length(local.cmk_domains) > 0 ? toset(var.key_admin_principal_ids) : toset([])

  scope                = azurerm_key_vault.data[0].id
  role_definition_name = "Key Vault Crypto Officer"
  principal_id         = each.value
}

resource "azurerm_key_vault_key" "domain" {
  for_each = local.cmk_domains

  name         = "${each.key}-${var.environment}-kek"
  key_vault_id = azurerm_key_vault.data[0].id
  key_type     = "RSA-HSM"
  key_size     = 3072
  key_opts     = ["wrapKey", "unwrapKey"]

  rotation_policy {
    automatic {
      time_before_expiry = "P30D"
    }
    expire_after         = var.key_expire_after
    notify_before_expiry = "P29D"
  }

  tags = {
    "data-classification" = local.domain_classification[each.key]
    "data-domain"         = each.key
    "environment"         = var.environment
  }

  depends_on = [azurerm_role_assignment.key_admin]
}

resource "azurerm_user_assigned_identity" "storage" {
  for_each = { for name, d in local.datasets : name => d if d.protection_profile != "pp1" }

  name                = "${var.name_prefix}-${var.environment}-${each.key}-id"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = local.dataset_tags[each.key]
}

resource "azurerm_role_assignment" "storage_key_user" {
  for_each = azurerm_user_assigned_identity.storage

  # Scope is the single domain key, not the vault.
  scope                = azurerm_key_vault_key.domain[local.datasets[each.key].data_domain].resource_versionless_id
  role_definition_name = "Key Vault Crypto Service Encryption User"
  principal_id         = each.value.principal_id
}

resource "azurerm_storage_account" "dataset" {
  for_each = local.datasets

  name                              = local.account_names[each.key]
  resource_group_name               = var.resource_group_name
  location                          = var.location
  account_tier                      = "Standard"
  account_replication_type          = "ZRS"
  account_kind                      = "StorageV2"
  min_tls_version                   = "TLS1_2"
  https_traffic_only_enabled        = true
  allow_nested_items_to_be_public   = false
  shared_access_key_enabled         = each.value.protection_profile == "pp1"
  infrastructure_encryption_enabled = contains(local.pp3_datasets, each.key)
  tags                              = local.dataset_tags[each.key]

  dynamic "identity" {
    for_each = each.value.protection_profile == "pp1" ? [] : [1]
    content {
      type         = "UserAssigned"
      identity_ids = [azurerm_user_assigned_identity.storage[each.key].id]
    }
  }

  dynamic "customer_managed_key" {
    for_each = each.value.protection_profile == "pp1" ? [] : [1]
    content {
      key_vault_key_id          = azurerm_key_vault_key.domain[each.value.data_domain].versionless_id
      user_assigned_identity_id = azurerm_user_assigned_identity.storage[each.key].id
    }
  }

  depends_on = [azurerm_role_assignment.storage_key_user]
}
