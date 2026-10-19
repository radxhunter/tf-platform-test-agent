# Test patterns that work in this repository

Every pattern below was run with Terraform 1.16 and `azurerm ~> 4.0` mocks.

## File skeleton

```hcl
mock_provider "azurerm" {}

variables {
  name                = "kv-tp-test"
  resource_group_name = "rg-test"
  location            = "westeurope"
}

run "vault_uses_rbac_and_purge_protection" {
  command = plan

  assert {
    condition     = azurerm_key_vault.this.rbac_authorization_enabled == true
    error_message = "The vault must use role-based access, not access policies."
  }
}
```

File-level `variables` hold a valid baseline. A `run` overrides only what it
needs in its own `variables` block.

## Azure resource IDs must look real

The azurerm provider validates ID arguments even when mocked. A placeholder
like `"x"` fails with `cannot parse Azure ID`. Use well-formed IDs:

```hcl
subnet_id          = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Network/virtualNetworks/vnet-test/subnets/snet-test"
storage_account_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Storage/storageAccounts/sttest001"
dns_zone_id        = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net"
workspace_id       = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.OperationalInsights/workspaces/log-test"
```

Object IDs and tenant IDs are GUIDs: `11111111-1111-1111-1111-111111111111`.

## The external provider: mock it and override the data source

`modules/function-app` reads `data.external.build_info`, which runs a shell
script. Mock the provider so the script never runs, then give the data source
the shape the module expects (a mocked map is empty, so `.result.revision`
would fail):

```hcl
mock_provider "azurerm" {}
mock_provider "external" {}

override_data {
  target = data.external.build_info
  values = {
    result = { revision = "abc1234" }
  }
}
```

From a stack, target the data source through the module path:
`target = module.function_app.data.external.build_info`.

## Plan versus apply with mocks

- `command = plan`: inputs and values known from configuration can be
  asserted. Computed attributes (`id`, `principal_id`, `workspace_url`) are
  unknown, and an assert on them fails with "unknown condition value".
- `command = apply` with mocked providers: no real resources, but computed
  attributes get generated values. Use it to check outputs and that
  references between resources are wired:

```hcl
run "outputs_expose_the_endpoint" {
  command = apply

  assert {
    condition     = output.id == azurerm_private_endpoint.this.id
    error_message = "Output id must be the endpoint's ID."
  }
}
```

In an `apply` run, mocked IDs are random strings such as `"tb9xgdi1"`. When
one resource passes another's `id` to an argument the provider validates
(`target_resource_id`, `scope`, `subnet_id`), apply fails with
`cannot parse Azure ID`. Give such resources a well-formed `id` in the mock.
The same block controls other computed values. A nested block such as
`identity` is written as a single object, not a list:

```hcl
mock_provider "azurerm" {
  mock_resource "azurerm_data_factory" {
    defaults = {
      id       = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.DataFactory/factories/adf-test"
      identity = { principal_id = "22222222-2222-2222-2222-222222222222" }
    }
  }
}
```

A `plan` run does not need any of this, so prefer `plan` and use `apply`
only for outputs and computed wiring.

## Validations: invalid and boundary values

```hcl
run "rejects_unknown_sku" {
  command = plan

  variables {
    sku = "basic"
  }

  expect_failures = [var.sku]
}
```

`expect_failures` only passes when the listed validation fails. Add a valid
boundary run next to it where the rule has a boundary (min, max, length).

## Repeated and optional blocks

```hcl
assert {
  condition     = length(azurerm_subnet.this) == 2
  error_message = "Expected one subnet for each key in var.subnets."
}

assert {
  condition     = length(azurerm_private_endpoint.this.private_dns_zone_group) == 0
  error_message = "No DNS zone group should be created without a zone ID."
}
```

Nested blocks are lists in conditions: `site_config[0].minimum_tls_version`.

## Stacks

`run_tests.py` runs stack tests once per `envs/*.tfvars` file, so stack
assertions must hold for every environment. Express environment rules as
implications:

```hcl
assert {
  condition     = var.environment != "prod" || var.public_access_enabled == false
  error_message = "Production must not enable public network access."
}
```

A stack test sees only what a module *outputs*: `module.network.subnet_ids`
works, `module.network.azurerm_subnet.this` fails with "Unsupported
attribute". Module outputs that come from computed attributes are unknown in
a `plan` run. Count module instances with `length(module.lake_endpoint)`,
and check the stack's own resources and locals directly.

To override a data source inside a called module, target it through the
module path: `target = module.function_app.data.external.build_info`.
