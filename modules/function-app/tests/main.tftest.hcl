mock_provider "azurerm" {}
mock_provider "external" {}

override_data {
  target = data.external.build_info
  values = {
    result = { revision = "abc1234" }
  }
}

variables {
  name                 = "func-tp-test"
  resource_group_name  = "rg-test"
  location             = "westeurope"
  storage_account_name = "sttest001"
  storage_account_id   = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Storage/storageAccounts/sttest001"
}

run "app_enforces_https_tls_and_managed_identity" {
  command = plan

  assert {
    condition     = azurerm_linux_function_app.this.https_only == true
    error_message = "The function app must accept HTTPS only."
  }

  assert {
    condition     = azurerm_linux_function_app.this.site_config[0].minimum_tls_version == "1.2"
    error_message = "Minimum TLS version must be 1.2."
  }

  assert {
    condition     = azurerm_linux_function_app.this.storage_uses_managed_identity == true
    error_message = "The runtime storage must be reached with the managed identity."
  }
}

run "public_access_follows_input" {
  command = plan

  variables {
    public_network_access_enabled = false
  }

  assert {
    condition     = azurerm_linux_function_app.this.public_network_access_enabled == false
    error_message = "Public network access must be off when the input disables it."
  }
}

run "app_settings_are_merged_with_build_revision" {
  command = plan

  variables {
    app_settings = { FOO = "bar" }
  }

  assert {
    condition     = azurerm_linux_function_app.this.app_settings["FOO"] == "bar" && azurerm_linux_function_app.this.app_settings["BUILD_REVISION"] == "abc1234"
    error_message = "Caller settings and BUILD_REVISION must both be present."
  }
}

run "runtime_storage_role_is_scoped_to_the_storage_account" {
  command = plan

  assert {
    condition     = azurerm_role_assignment.runtime_storage.scope == var.storage_account_id
    error_message = "The role assignment must be scoped to the runtime storage account only."
  }
}

run "service_plan_is_linux_premium" {
  command = plan

  assert {
    condition     = azurerm_service_plan.this.os_type == "Linux" && azurerm_service_plan.this.sku_name == "EP1"
    error_message = "The plan must be Linux on EP1."
  }
}
