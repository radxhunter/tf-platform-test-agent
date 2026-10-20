---
name: tf-coverage
description: Measure which resources, module calls, validations and outputs of a Terraform unit are referenced by its tests, to find gaps worth testing. Use before writing tests (to choose what to test) and after (to report the change).
---

# Terraform test coverage

```sh
python3 .claude/skills/tf-coverage/scripts/coverage.py modules/data-factory [more units] [--format markdown]
```

For each unit you get every resource, data source, module call, validated
variable and output, and whether the tests reference it:

- a resource, module call or output is covered when an `assert` condition
  mentions its address,
- a validation is covered when a run lists the variable in
  `expect_failures`,
- data sources are listed, but not counted, since tests mock or override
  them.

## Reading it honestly

This is *reference* coverage. 100% means every item is mentioned in some
assert, not that the important properties are checked. Use the gap list to
choose work, in this order:

1. uncovered validations (cheap, and they guard input contracts),
2. resources with security-relevant settings and no assert on them,
3. `for_each` resources and `dynamic` blocks (shape),
4. outputs (an `apply` run with mocks).

Outputs are not low value: they are what callers depend on. Cover each one
with a real equality assert in an `apply` run. Leave an item uncovered only
when any assert you could write would be meaningless (an echo of the code, or
a value only Azure knows), and then say so in `limitations`. Never add an
assert just to reach 100%.
Report coverage before and after in the run output.
