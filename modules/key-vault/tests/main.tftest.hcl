mock_provider "azurerm" {
  mock_resource "azurerm_key_vault" {
    defaults = {
      id        = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.KeyVault/vaults/kv-tp-test"
      vault_uri = "https://kv-tp-test.vault.azure.net/"
    }
  }

  mock_data "azurerm_role_definition" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/providers/Microsoft.Authorization/roleDefinitions/4633458b-17de-408a-b874-0445c86b69e6"
    }
  }
}

variables {
  name                = "kv-tp-test"
  resource_group_name = "rg-test"
  location            = "westeurope"
  tenant_id           = "00000000-0000-0000-0000-000000000000"

  log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.OperationalInsights/workspaces/log-test"

  secret_readers = {
    adf = "11111111-1111-1111-1111-111111111111"
  }
}

run "vault_uses_rbac_and_purge_protection" {
  command = plan

  assert {
    condition     = azurerm_key_vault.this.rbac_authorization_enabled == true
    error_message = "The vault must use role-based access, not access policies."
  }

  assert {
    condition     = azurerm_key_vault.this.purge_protection_enabled == true
    error_message = "Purge protection must be on."
  }
}

run "diagnostics_send_audit_logs_and_metrics_to_workspace" {
  command = plan

  assert {
    condition     = azurerm_monitor_diagnostic_setting.this.log_analytics_workspace_id == var.log_analytics_workspace_id
    error_message = "Diagnostics must go to the workspace given in log_analytics_workspace_id."
  }

  assert {
    condition     = one(azurerm_monitor_diagnostic_setting.this.enabled_log).category_group == "audit"
    error_message = "The audit log category group must be enabled."
  }

  assert {
    condition     = one(azurerm_monitor_diagnostic_setting.this.enabled_metric).category == "AllMetrics"
    error_message = "AllMetrics must be enabled."
  }
}

run "outputs_expose_vault_id_and_uri" {
  command = apply

  assert {
    condition     = output.id == azurerm_key_vault.this.id
    error_message = "Output id must be the vault's ID."
  }

  assert {
    condition     = output.vault_uri == "https://kv-tp-test.vault.azure.net/"
    error_message = "Output vault_uri must be the vault's URI."
  }
}

run "creates_one_role_assignment_per_reader" {
  command = plan

  assert {
    condition     = length(azurerm_role_assignment.secret_reader) == 1
    error_message = "Expected one role assignment for each secret reader."
  }
}
