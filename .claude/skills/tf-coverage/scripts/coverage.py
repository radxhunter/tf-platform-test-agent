#!/usr/bin/env python3
"""Report which parts of a Terraform unit its tests touch.

Usage: coverage.py <unit-dir> [<unit-dir> ...] [--format json|markdown]

For each unit (a module or stack directory) it lists:
  - resources, data sources and module calls, and whether any `assert`
    condition references them,
  - variables with `validation` blocks, and whether a run lists them in
    `expect_failures` (the only way to show a validation rejects bad input),
  - outputs, and whether any assert references them.

This is reference coverage, not behavioural coverage: a resource counts as
covered when an assertion mentions it, however weak that assertion is. Use it
to find gaps, not to prove that the tests are good.
"""
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hcl_lite import blocks, bracket_list, strip_comments  # noqa: E402


def read_all(paths):
    return "\n".join(strip_comments(open(p, encoding="utf-8").read()) for p in sorted(paths))


def analyse(unit):
    src = read_all(glob.glob(os.path.join(unit, "*.tf")))
    test_files = sorted(glob.glob(os.path.join(unit, "tests", "*.tftest.hcl")))
    tests = read_all(test_files)

    asserts, expected_failures, runs = [], [], 0
    for _, run_body in blocks(tests, "run"):
        runs += 1
        expected_failures.append(bracket_list(run_body, "expect_failures"))
        for _, assert_body in blocks(run_body, "assert"):
            asserts.append(assert_body)
    assert_text = "\n".join(asserts)
    failure_text = "\n".join(expected_failures)

    def referenced(address, text):
        return re.search(r"(?<![\w.])" + re.escape(address) + r"(?![\w-])", text) is not None

    items = []
    for labels, _ in blocks(src, "resource"):
        addr = ".".join(labels)
        items.append({"kind": "resource", "address": addr, "covered": referenced(addr, assert_text)})
    for labels, _ in blocks(src, "data"):
        addr = "data." + ".".join(labels)
        items.append({"kind": "data", "address": addr, "covered": referenced(addr, assert_text)})
    for labels, _ in blocks(src, "module"):
        addr = "module." + labels[0]
        items.append({"kind": "module", "address": addr, "covered": referenced(addr, assert_text)})
    for labels, body in blocks(src, "variable"):
        if any(True for _ in blocks(body, "validation")):
            addr = "var." + labels[0]
            items.append({"kind": "validation", "address": addr, "covered": referenced(addr, failure_text)})
    for labels, _ in blocks(src, "output"):
        addr = "output." + labels[0]
        items.append({"kind": "output", "address": addr, "covered": referenced(addr, assert_text)})

    # Data sources are usually mocked or overridden, so they are reported but
    # not counted towards the percentage.
    counted = [i for i in items if i["kind"] != "data"]
    covered = sum(1 for i in counted if i["covered"])
    return {
        "unit": unit.replace("\\", "/").rstrip("/"),
        "test_files": len(test_files),
        "runs": runs,
        "asserts": len(asserts),
        "covered": covered,
        "total": len(counted),
        "percent": round(100 * covered / len(counted)) if counted else 100,
        "items": items,
    }


def markdown(reports):
    lines = [
        "| Unit | Test files | Runs | Asserts | Covered | Gaps |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for r in reports:
        gaps = [i["address"] for i in r["items"] if not i["covered"] and i["kind"] != "data"]
        gap_text = ", ".join(f"`{g}`" for g in gaps) if gaps else "none"
        lines.append(
            f"| `{r['unit']}` | {r['test_files']} | {r['runs']} | {r['asserts']} "
            f"| {r['covered']}/{r['total']} ({r['percent']}%) | {gap_text} |"
        )
    return "\n".join(lines)


def main(argv):
    fmt = "json"
    if "--format" in argv:
        i = argv.index("--format")
        fmt = argv[i + 1]
        argv = argv[:i] + argv[i + 2 :]
    units = argv[1:]
    if not units:
        print(__doc__, file=sys.stderr)
        return 2
    reports = [analyse(u) for u in units]
    if fmt == "markdown":
        print(markdown(reports))
    else:
        json.dump(reports, sys.stdout, indent=2)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
