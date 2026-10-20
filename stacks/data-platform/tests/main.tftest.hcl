mock_provider "azurerm" {
  mock_resource "azurerm_virtual_network" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Network/virtualNetworks/vnet-test"
    }
  }

  mock_resource "azurerm_subnet" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Network/virtualNetworks/vnet-test/subnets/snet-test"
    }
  }

  mock_resource "azurerm_network_security_group" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Network/networkSecurityGroups/nsg-test"
    }
  }

  mock_resource "azurerm_log_analytics_workspace" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.OperationalInsights/workspaces/log-test"
    }
  }

  mock_resource "azurerm_storage_account" {
    defaults = {
      id                   = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Storage/storageAccounts/sttest001"
      primary_dfs_endpoint = "https://sttest001.dfs.core.windows.net/"
    }
  }

  mock_resource "azurerm_key_vault" {
    defaults = {
      id        = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.KeyVault/vaults/kv-test"
      vault_uri = "https://kv-test.vault.azure.net/"
    }
  }

  mock_data "azurerm_role_definition" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/providers/Microsoft.Authorization/roleDefinitions/4633458b-17de-408a-b874-0445c86b69e6"
    }
  }

  mock_resource "azurerm_data_factory" {
    defaults = {
      id       = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.DataFactory/factories/adf-test"
      identity = { principal_id = "22222222-2222-2222-2222-222222222222" }
    }
  }

  mock_resource "azurerm_databricks_workspace" {
    defaults = {
      id            = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Databricks/workspaces/dbw-test"
      workspace_url = "adb-1234567890123456.7.azuredatabricks.net"
    }
  }

  mock_resource "azurerm_service_plan" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Web/serverFarms/asp-test"
    }
  }

  mock_resource "azurerm_linux_function_app" {
    defaults = {
      id       = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Web/sites/func-test"
      identity = { principal_id = "33333333-3333-3333-3333-333333333333" }
    }
  }

  mock_resource "azurerm_private_endpoint" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Network/privateEndpoints/pe-test"
    }
  }
}

mock_provider "external" {}

override_data {
  target = module.function_app.data.external.build_info
  values = {
    result = { revision = "abc1234" }
  }
}

run "stack_names_and_tags_follow_environment" {
  command = plan

  assert {
    condition     = azurerm_resource_group.this.name == "rg-tp-${var.environment}"
    error_message = "The resource group must be named rg-tp-<environment>."
  }

  assert {
    condition     = local.tags["environment"] == var.environment && local.tags["managed_by"] == "terraform"
    error_message = "Tags must carry the environment and managed_by=terraform."
  }
}

run "production_denies_public_access" {
  command = plan

  assert {
    condition     = var.environment != "prod" || var.public_access_enabled == false
    error_message = "Production must not enable public network access."
  }
}

run "one_lake_and_two_endpoints_per_data_lake" {
  command = plan

  assert {
    condition     = length(module.data_lake) == length(var.data_lakes)
    error_message = "Expected one storage module instance for each data lake."
  }

  assert {
    condition     = length(module.lake_endpoint) == 2 * length(var.data_lakes)
    error_message = "Expected a blob and a dfs private endpoint for each data lake."
  }
}

run "subnets_are_carved_from_the_address_space" {
  command = plan

  assert {
    condition     = keys(local.subnets) == ["apps", "endpoints"]
    error_message = "The stack must define the apps and endpoints subnets."
  }

  assert {
    condition     = local.subnets["apps"].address_prefixes[0] != local.subnets["endpoints"].address_prefixes[0]
    error_message = "Subnets must not overlap."
  }
}

run "outputs_expose_group_workspace_url_and_vault_uri" {
  command = apply

  assert {
    condition     = output.resource_group_name == "rg-tp-${var.environment}"
    error_message = "Output resource_group_name must be the platform resource group."
  }

  assert {
    condition     = output.databricks_workspace_url == "adb-1234567890123456.7.azuredatabricks.net"
    error_message = "Output databricks_workspace_url must come from the Databricks module."
  }

  assert {
    condition     = output.key_vault_uri == "https://kv-test.vault.azure.net/"
    error_message = "Output key_vault_uri must come from the key vault module."
  }
}

run "rejects_unknown_environment" {
  command = plan

  variables {
    environment = "staging"
  }

  expect_failures = [var.environment]
}
