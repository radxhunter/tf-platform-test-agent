---
name: tf-test-runner
description: Run the policy lint, terraform fmt check, validate and terraform test for one or more Terraform units in an isolated sandbox, and read the structured result. Use after every change to a test file, and to get a baseline before changing anything.
---

# Running Terraform tests

```sh
python3 .claude/skills/tf-test-runner/scripts/run_tests.py modules/key-vault [stacks/data-platform ...]
```

The command prints one JSON document:

```json
{
  "ok": false,
  "units": [{
    "unit": "modules/key-vault",
    "ok": false,
    "lint":     {"ok": true,  "errors": []},
    "fmt":      {"ok": false, "output": "<diff of what fmt would change>"},
    "validate": {"ok": true,  "output": "Success! ..."},
    "tests": [{
      "var_file": null,
      "status": "fail",
      "summary": {"passed": 2, "failed": 1, "errored": 0, "skipped": 0},
      "runs": [{"file": "tests/main.tftest.hcl", "run": "x", "status": "fail"}],
      "diagnostics": [{"summary": "Test assertion failed", "detail": "...", "file": "tests/main.tftest.hcl", "line": 21, "run": "x"}]
    }]
  }]
}
```

Stacks have one `tests` entry per `envs/*.tfvars` file.

## How to use the result

- `lint.ok == false`: the file breaks the repository's test policy and was
  **not executed**. Fix the listed rule (P1-P6) first.
- `fmt.ok == false`: apply the shown diff by hand. Alignment of `=` in a block
  is the usual cause.
- `validate.ok == false`: the unit itself does not validate. That is not
  yours to fix: report it as a finding and stop working on that unit.
- A failing run: read `diagnostics`. `cannot parse Azure ID` means a fake ID
  is malformed (see `tf-test-authoring/reference.md`); "unknown condition
  value" means you asserted a computed value in a `plan` run.

## Limits

- At most **three** fix-and-rerun rounds per test file. If it still fails,
  remove the failing run, keep the passing ones and explain why in the
  output. Do not keep guessing.
- The sandbox has no network. Units must be initialised beforehand (in CI the
  workflow does it; locally run `prepare.py` once). If a run reports missing
  providers, say so; do not try to initialise anything yourself.
- Locally, outside CI, `TF_TEST_SANDBOX=none` runs the host's `terraform`
  instead of Docker.
