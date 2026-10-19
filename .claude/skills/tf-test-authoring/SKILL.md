---
name: tf-test-authoring
description: Write or update `terraform test` files (.tftest.hcl) for modules and stacks in this repository, using mocked providers so no cloud credentials or resources are needed. Use whenever a test file is created or changed.
---

# Writing Terraform tests

Tests live in `<unit>/tests/*.tftest.hcl` and run with `terraform test` from
the unit directory. They must pass against the current code, run without
credentials and never touch a cloud API.

`reference.md` in this folder has worked patterns. Read it before writing the
first test of a run.

## Non-negotiable rules

These are also enforced by `lint_tests.py`; a file that breaks them is not run.

1. Add a `mock_provider "<name>" {}` for **every** provider in the unit's
   `required_providers` (for example `azurerm` and `external`). An unmocked
   `external` provider runs the module's shell script during plan.
2. No `provider` blocks, no `module { source = ... }` inside `run` blocks.
3. Every `run` says `command = plan` or `command = apply` explicitly.
4. Run names are `snake_case` and describe the property, for example
   `storage_denies_public_network_access`, not `test1`.
5. Edit only files under `<unit>/tests/`. Never change `.tf` files, variable
   files or lock files, even when a test would be easier to write.

## What a good test asserts

Each test protects a property a reviewer would care about if it broke:

1. **Security posture**: public access off, TLS minimums, RBAC instead of
   keys or access policies, deny-by-default network rules, least privilege.
2. **Input contracts**: every `validation` block gets a run with an invalid
   value and `expect_failures = [var.x]`, plus a valid boundary value where
   the rule has a boundary.
3. **Shape**: `for_each` and `count` produce one item per input key, and
   optional blocks (`dynamic`) appear only when their input is set.
4. **Wiring**: inputs reach the attribute they are meant for, and outputs
   expose the right attribute. With mocks, check outputs in an `apply` run,
   since computed values are unknown during plan.
5. **Conventions** from the README: naming prefixes, tags applied.

Avoid tests that only restate the code (`name == var.name` everywhere) or that
test the provider or Azure itself. One meaningful assert beats five echoes.

## Tests document the code as it is

A test must pass against the current code. When the code does something that
looks wrong (for example `ftps_state = "AllAllowed"`), **do not** write a
failing test and **do not** write a test that blesses it as correct. Leave it
untested, and report it as a finding (see `tf-risk-review`). People decide
whether infrastructure changes.

When the diff changes behaviour on purpose and an existing assert breaks,
update that assert, keep its intent, and record the old and new values in the
output. Never delete or loosen an assert about security posture to make a
test pass: report it as a finding instead.

## Before you finish a file

- Run it with `tf-test-runner` and read the result, not just the exit code.
- `terraform fmt` style: two-space indent, aligned `=`. The runner checks
  this; fix what it reports.
- Every `error_message` says what property broke, in one sentence.
