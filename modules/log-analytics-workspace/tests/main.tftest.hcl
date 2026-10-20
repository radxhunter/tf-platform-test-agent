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

run "output_exposes_workspace_id" {
  command = apply

  assert {
    condition     = output.id == azurerm_log_analytics_workspace.this.id
    error_message = "Output id must be the workspace's ID."
  }
}

run "daily_quota_defaults_to_no_cap" {
  command = plan

  assert {
    condition     = azurerm_log_analytics_workspace.this.daily_quota_gb == -1
    error_message = "The daily ingestion quota must default to -1 (no cap)."
  }
}

run "daily_quota_follows_input" {
  command = plan

  variables {
    daily_quota_gb = 5
  }

  assert {
    condition     = azurerm_log_analytics_workspace.this.daily_quota_gb == 5
    error_message = "The daily quota must follow daily_quota_gb."
  }
}

run "daily_quota_accepts_minimum_boundary" {
  command = plan

  variables {
    daily_quota_gb = 0.023
  }

  assert {
    condition     = azurerm_log_analytics_workspace.this.daily_quota_gb == 0.023
    error_message = "The minimum quota of 0.023 GB must be accepted."
  }
}

run "daily_quota_rejects_value_below_minimum" {
  command = plan

  variables {
    daily_quota_gb = 0.01
  }

  expect_failures = [var.daily_quota_gb]
}

run "daily_quota_rejects_negative_value_other_than_minus_one" {
  command = plan

  variables {
    daily_quota_gb = -2
  }

  expect_failures = [var.daily_quota_gb]
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
