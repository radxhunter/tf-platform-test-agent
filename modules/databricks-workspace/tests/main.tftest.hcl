mock_provider "azurerm" {
  mock_resource "azurerm_databricks_workspace" {
    defaults = {
      id            = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Databricks/workspaces/dbw-tp-test"
      workspace_url = "adb-1234567890123456.7.azuredatabricks.net"
    }
  }
}

variables {
  name                = "dbw-tp-test"
  resource_group_name = "rg-test"
  location            = "westeurope"
}

run "workspace_has_no_public_ip_for_clusters" {
  command = plan

  assert {
    condition     = azurerm_databricks_workspace.this.custom_parameters[0].no_public_ip == true
    error_message = "Cluster nodes must not get public IPs."
  }
}

run "workspace_public_access_follows_input" {
  command = plan

  variables {
    public_network_access_enabled = false
  }

  assert {
    condition     = azurerm_databricks_workspace.this.public_network_access_enabled == false
    error_message = "Public network access must be off when the input disables it."
  }
}

run "managed_resource_group_name_is_derived" {
  command = plan

  assert {
    condition     = azurerm_databricks_workspace.this.managed_resource_group_name == "rg-test-dbw-tp-test-managed"
    error_message = "The managed resource group must be <resource group>-<name>-managed."
  }
}

run "outputs_expose_workspace_id_and_url" {
  command = apply

  assert {
    condition     = output.id == azurerm_databricks_workspace.this.id
    error_message = "Output id must be the workspace's ID."
  }

  assert {
    condition     = output.workspace_url == "adb-1234567890123456.7.azuredatabricks.net"
    error_message = "Output workspace_url must be the workspace's URL."
  }
}

run "accepts_standard_sku" {
  command = plan

  variables {
    sku = "standard"
  }

  assert {
    condition     = azurerm_databricks_workspace.this.sku == "standard"
    error_message = "The standard sku must be accepted."
  }
}

run "rejects_unknown_sku" {
  command = plan

  variables {
    sku = "trial"
  }

  expect_failures = [var.sku]
}
