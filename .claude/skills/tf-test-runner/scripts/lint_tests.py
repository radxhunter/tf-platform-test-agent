#!/usr/bin/env python3
"""Check that the test files of a Terraform unit follow the repository policy.

Usage: lint_tests.py <unit-dir> [<unit-dir> ...]

The policy makes sure a test can never reach a cloud API or run code from the
module under test, whoever wrote it (a person or the agent):

  P1  every provider in the unit's required_providers has a `mock_provider`
      in every test file, so no real provider is ever configured,
  P2  test files contain no `provider` blocks (real provider configuration),
  P3  run blocks do not load other modules (`module { source = ... }`),
  P4  every run block states `command = plan` or `command = apply`,
  P5  run names are snake_case and unique within a file,
  P6  every file has at least one run with at least one assert or
      expect_failures, so an empty test cannot pass silently.

Exit code 0 when all files pass, 1 with one line per violation otherwise.
"""
import glob
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tf-coverage", "scripts"))
from hcl_lite import attribute, blocks, bracket_list, strip_comments  # noqa: E402


def required_providers(unit):
    names = set()
    for path in glob.glob(os.path.join(unit, "*.tf")):
        text = strip_comments(open(path, encoding="utf-8").read())
        for _, tf_body in blocks(text, "terraform"):
            for _, rp_body in blocks(tf_body, "required_providers"):
                names.update(re.findall(r"(?m)^[ \t]*([a-zA-Z0-9_-]+)[ \t]*=[ \t]*\{", rp_body))
    return names


def lint_file(path, providers):
    errors = []
    text = strip_comments(open(path, encoding="utf-8").read())
    rel = path.replace("\\", "/")

    mocked = {labels[0] for labels, _ in blocks(text, "mock_provider") if labels}
    for name in sorted(providers - mocked):
        errors.append(f"{rel}: P1 provider '{name}' is not mocked; add mock_provider \"{name}\" {{}}")
    for labels, _ in blocks(text, "provider"):
        errors.append(f"{rel}: P2 real provider block '{labels[0] if labels else '?'}' is not allowed in tests")

    seen, useful_runs = set(), 0
    for labels, body in blocks(text, "run"):
        name = labels[0] if labels else "?"
        if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
            errors.append(f"{rel}: P5 run name '{name}' must be snake_case")
        if name in seen:
            errors.append(f"{rel}: P5 run name '{name}' is used twice")
        seen.add(name)
        if any(True for _ in blocks(body, "module")):
            errors.append(f"{rel}: P3 run '{name}' loads another module; test the unit itself")
        command = attribute(body, "command")
        if command not in ("plan", "apply"):
            errors.append(f"{rel}: P4 run '{name}' must set command = plan or command = apply")
        has_assert = any(True for _ in blocks(body, "assert"))
        if has_assert or bracket_list(body, "expect_failures").strip():
            useful_runs += 1
    if useful_runs == 0:
        errors.append(f"{rel}: P6 file has no run with an assert or expect_failures")
    return errors


def main(argv):
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    errors = []
    for unit in argv[1:]:
        providers = required_providers(unit)
        if not providers:
            errors.append(f"{unit}: cannot find required_providers; refusing to guess what to mock")
            continue
        for path in sorted(glob.glob(os.path.join(unit, "tests", "*.tftest.hcl"))):
            errors.extend(lint_file(path, providers))
    for e in errors:
        print(e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
