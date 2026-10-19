mock_provider "azurerm" {}
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

run "rejects_unknown_environment" {
  command = plan

  variables {
    environment = "staging"
  }

  expect_failures = [var.environment]
}
