mock_provider "azurerm" {}

variables {
  name                = "log-tp-test"
  resource_group_name = "rg-test"
  location            = "westeurope"
}

run "workspace_uses_per_gb_sku_and_default_retention" {
  command = plan

  assert {
    condition     = azurerm_log_analytics_workspace.this.sku == "PerGB2018"
    error_message = "The workspace must use the PerGB2018 sku."
  }

  assert {
    condition     = azurerm_log_analytics_workspace.this.retention_in_days == 30
    error_message = "Default retention must be 30 days."
  }
}

run "retention_follows_input" {
  command = plan

  variables {
    retention_in_days = 90
  }

  assert {
    condition     = azurerm_log_analytics_workspace.this.retention_in_days == 90
    error_message = "Retention must follow retention_in_days."
  }
}
