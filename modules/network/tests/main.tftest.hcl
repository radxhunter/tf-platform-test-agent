mock_provider "azurerm" {
  mock_resource "azurerm_virtual_network" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Network/virtualNetworks/vnet-tp-test"
    }
  }

  mock_resource "azurerm_subnet" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Network/virtualNetworks/vnet-tp-test/subnets/snet-test"
    }
  }

  mock_resource "azurerm_network_security_group" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Network/networkSecurityGroups/nsg-test"
    }
  }
}

variables {
  name                = "tp-test"
  resource_group_name = "rg-test"
  location            = "westeurope"
  address_space       = ["10.10.0.0/16"]
  subnets = {
    apps = {
      address_prefixes  = ["10.10.0.0/24"]
      service_endpoints = ["Microsoft.Storage"]
    }
    data = {
      address_prefixes = ["10.10.1.0/24"]
    }
  }
}

run "creates_one_subnet_and_nsg_per_key" {
  command = plan

  assert {
    condition     = length(azurerm_subnet.this) == 2
    error_message = "Expected one subnet for each key in var.subnets."
  }

  assert {
    condition     = length(azurerm_network_security_group.this) == 2
    error_message = "Expected one network security group for each subnet."
  }

  assert {
    condition     = length(azurerm_subnet_network_security_group_association.this) == 2
    error_message = "Every subnet must be associated with its network security group."
  }
}

run "names_follow_the_convention" {
  command = plan

  assert {
    condition     = azurerm_virtual_network.this.name == "vnet-tp-test"
    error_message = "The virtual network name must start with vnet-."
  }

  assert {
    condition     = azurerm_subnet.this["apps"].name == "snet-apps"
    error_message = "Subnet names must start with snet-."
  }
}

run "outputs_expose_vnet_and_subnet_ids" {
  command = apply

  assert {
    condition     = output.vnet_id == azurerm_virtual_network.this.id
    error_message = "Output vnet_id must be the virtual network's ID."
  }

  assert {
    condition     = toset(keys(output.subnet_ids)) == toset(["apps", "data"])
    error_message = "Output subnet_ids must have one entry for each subnet key."
  }

  assert {
    condition     = alltrue([for key, id in output.subnet_ids : id == azurerm_subnet.this[key].id])
    error_message = "Each subnet_ids entry must be the ID of the subnet with the same key."
  }
}

run "rejects_invalid_address_space" {
  command = plan

  variables {
    address_space = ["not-a-cidr"]
  }

  expect_failures = [var.address_space]
}
