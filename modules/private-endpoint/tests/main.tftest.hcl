mock_provider "azurerm" {}

variables {
  name                = "tp-test-blob"
  resource_group_name = "rg-test"
  location            = "westeurope"
  subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Network/virtualNetworks/vnet-test/subnets/snet-test"
  target_resource_id  = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Storage/storageAccounts/sttest001"
  subresource_name    = "blob"
}

run "endpoint_is_automatic_and_named_by_convention" {
  command = plan

  assert {
    condition     = azurerm_private_endpoint.this.name == "pe-tp-test-blob"
    error_message = "The endpoint must be named pe-<name>."
  }

  assert {
    condition     = azurerm_private_endpoint.this.private_service_connection[0].is_manual_connection == false
    error_message = "The connection must not require manual approval."
  }

  assert {
    condition     = azurerm_private_endpoint.this.private_service_connection[0].subresource_names == tolist(["blob"])
    error_message = "The subresource name must reach the service connection."
  }
}

run "no_dns_zone_group_without_zone_id" {
  command = plan

  assert {
    condition     = length(azurerm_private_endpoint.this.private_dns_zone_group) == 0
    error_message = "No DNS zone group should be created without a zone ID."
  }
}

run "dns_zone_group_created_with_zone_id" {
  command = plan

  variables {
    private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net"
  }

  assert {
    condition     = length(azurerm_private_endpoint.this.private_dns_zone_group) == 1
    error_message = "A DNS zone group must be created when a zone ID is given."
  }
}
