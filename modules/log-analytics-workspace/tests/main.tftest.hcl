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

run "accepts_minimum_retention" {
  command = plan

  variables {
    retention_in_days = 30
  }

  assert {
    condition     = azurerm_log_analytics_workspace.this.retention_in_days == 30
    error_message = "30 days is the lowest valid retention."
  }
}

run "accepts_maximum_retention" {
  command = plan

  variables {
    retention_in_days = 730
  }

  assert {
    condition     = azurerm_log_analytics_workspace.this.retention_in_days == 730
    error_message = "730 days is the highest valid retention."
  }
}

run "rejects_retention_below_minimum" {
  command = plan

  variables {
    retention_in_days = 29
  }

  expect_failures = [var.retention_in_days]
}

run "rejects_retention_above_maximum" {
  command = plan

  variables {
    retention_in_days = 731
  }

  expect_failures = [var.retention_in_days]
}

run "output_exposes_workspace_id" {
  command = apply

  assert {
    condition     = output.id == azurerm_log_analytics_workspace.this.id
    error_message = "Output id must be the workspace's ID."
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
