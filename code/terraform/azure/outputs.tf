output "key_vault_id" {
  description = "Key Vault holding the domain keys (null when no dataset needs a CMK)."
  value       = length(azurerm_key_vault.data) > 0 ? azurerm_key_vault.data[0].id : null
}

output "key_ids" {
  description = "Versionless key ID per data domain."
  value       = { for dom, k in azurerm_key_vault_key.domain : dom => k.versionless_id }
}

output "storage_accounts" {
  description = "Per dataset: storage account name, protection profile, and CMK (null means Microsoft-managed keys)."
  value = {
    for name, d in local.datasets : name => {
      name               = azurerm_storage_account.dataset[name].name
      protection_profile = d.protection_profile
      key_id             = d.protection_profile == "pp1" ? null : azurerm_key_vault_key.domain[d.data_domain].versionless_id
      infrastructure_enc = contains(local.pp3_datasets, name)
    }
  }
}
