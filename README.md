# Terraform Platform Base

A small Terraform repository for a data platform on Azure: networking, storage, secrets, monitoring, data integration, analytics and a function app.

## Layout

```text
modules/            Reusable modules. Each has main.tf, variables.tf, outputs.tf and versions.tf.
  <module>/tests/   Tests for a module, where they exist. Run them from the module folder.
stacks/
  data-platform/    The stack that uses the modules. One set of variables per environment in envs/.
```

## Requirements

- Terraform 1.9 or newer
- Internet access to download providers
- No Azure subscription or credentials

## Run the tests of a module

The tests use a mocked `azurerm` provider, so they need no credentials.

```sh
cd modules/storage-account
terraform init -backend=false
terraform test
```

## Check the stack

```sh
cd stacks/data-platform
terraform init -backend=false
terraform fmt -check -recursive ../..
terraform validate
```

The stack has no backend configured. A real deployment would need one, and credentials for it.

## Test agent

Pull requests that change `modules/` or `stacks/` are picked up by the
Terraform test agent (`.github/workflows/terraform-test-agent.yml`). It adds
or updates tests for the changed units, re-runs them in a sandbox, commits
the ones that pass to the pull request, and leaves one comment with results
and findings. See [SOLUTION.md](SOLUTION.md) for how it works and why.

Add the `test-agent:skip` label to a pull request to skip the agent.

The scripts and workflows that police the agent have their own tests
(`tests/tooling`, run by the `CI` workflow). Run them with:

```sh
cd tests/tooling && python3 -m unittest discover -s . -p 'test_*.py'
```

## Conventions

- Resource files in a stack and modules use `main.tf`, `variables.tf`, `outputs.tf` and `versions.tf`.
- Use `for_each` rather than `count` for repeated resources.
- Environments are `dev`, `uat` and `prod`.
- Format code with `terraform fmt -recursive` before committing.
