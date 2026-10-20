mock_provider "azurerm" {
  mock_resource "azurerm_data_factory" {
    defaults = {
      id       = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.DataFactory/factories/adf-tp-test"
      identity = { principal_id = "22222222-2222-2222-2222-222222222222" }
    }
  }
}

variables {
  name                       = "adf-tp-test"
  resource_group_name        = "rg-test"
  location                   = "westeurope"
  log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.OperationalInsights/workspaces/log-test"
  linked_storage_accounts = {
    raw     = "https://sttestraw.dfs.core.windows.net"
    curated = "https://sttestcur.dfs.core.windows.net"
  }
}

run "factory_uses_managed_identity" {
  command = plan

  assert {
    condition     = azurerm_data_factory.this.identity[0].type == "SystemAssigned"
    error_message = "The factory must use a system-assigned managed identity."
  }

  assert {
    condition     = alltrue([for ls in azurerm_data_factory_linked_service_data_lake_storage_gen2.this : ls.use_managed_identity == true])
    error_message = "Linked services must authenticate with the managed identity, not keys."
  }
}

run "factory_public_access_follows_input" {
  command = plan

  variables {
    public_network_enabled = false
  }

  assert {
    condition     = azurerm_data_factory.this.public_network_enabled == false
    error_message = "Public network access must be off when the input disables it."
  }
}

run "creates_one_linked_service_per_account" {
  command = plan

  assert {
    condition     = length(azurerm_data_factory_linked_service_data_lake_storage_gen2.this) == 2
    error_message = "Expected one linked service for each entry in linked_storage_accounts."
  }

  assert {
    condition     = azurerm_data_factory_linked_service_data_lake_storage_gen2.this["raw"].name == "ls-raw"
    error_message = "Linked services must be named ls-<key>."
  }
}

run "outputs_expose_factory_id_and_identity" {
  command = apply

  assert {
    condition     = output.id == azurerm_data_factory.this.id
    error_message = "Output id must be the factory's ID."
  }

  assert {
    condition     = output.principal_id == "22222222-2222-2222-2222-222222222222"
    error_message = "Output principal_id must be the factory's managed identity principal."
  }
}

run "diagnostics_send_pipeline_and_activity_logs" {
  command = plan

  assert {
    condition     = toset([for l in azurerm_monitor_diagnostic_setting.this.enabled_log : l.category]) == toset(["PipelineRuns", "ActivityRuns"])
    error_message = "Diagnostics must enable PipelineRuns and ActivityRuns logs."
  }
}
