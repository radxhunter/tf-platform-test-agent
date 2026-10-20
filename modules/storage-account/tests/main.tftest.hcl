mock_provider "azurerm" {
  mock_resource "azurerm_storage_account" {
    defaults = {
      id                   = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Storage/storageAccounts/sttptest001"
      primary_dfs_endpoint = "https://sttptest001.dfs.core.windows.net/"
    }
  }
}

variables {
  name                = "sttptest001"
  resource_group_name = "rg-test"
  location            = "westeurope"
  containers          = ["raw", "curated"]
}

run "account_is_locked_down_by_default" {
  command = plan

  assert {
    condition     = azurerm_storage_account.this.min_tls_version == "TLS1_2"
    error_message = "The account must require TLS 1.2."
  }

  assert {
    condition     = azurerm_storage_account.this.allow_nested_items_to_be_public == false
    error_message = "Public blob access must be off."
  }

  assert {
    condition     = azurerm_storage_account_network_rules.this.default_action == "Deny"
    error_message = "Network access must be denied by default."
  }
}

run "creates_one_container_per_name" {
  command = plan

  assert {
    condition     = length(azurerm_storage_container.this) == 2
    error_message = "Expected one container for each name."
  }
}

run "outputs_expose_account_id_name_and_dfs_endpoint" {
  command = apply

  assert {
    condition     = output.id == azurerm_storage_account.this.id
    error_message = "Output id must be the storage account's ID."
  }

  assert {
    condition     = output.name == azurerm_storage_account.this.name
    error_message = "Output name must be the storage account's name."
  }

  assert {
    condition     = output.primary_dfs_endpoint == "https://sttptest001.dfs.core.windows.net/"
    error_message = "Output primary_dfs_endpoint must be the account's DFS endpoint."
  }
}

run "rejects_invalid_name" {
  command = plan

  variables {
    name = "Invalid-Name"
  }

  expect_failures = [var.name]
}
