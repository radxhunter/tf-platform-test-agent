#!/usr/bin/env python3
"""Map a git diff to the Terraform units (modules and stacks) it touches.

Usage: changed_scope.py <base-sha> <head-sha> [--repo DIR] [--include UNITS]

--include adds units to the scope even when the diff does not touch them,
for example "all" or "modules/key-vault modules/network" for a backfill run.
They are marked "requested": true.

Prints JSON to stdout:
{
  "base": "...", "head": "...",
  "units": [
    {"path": "modules/key-vault", "kind": "module",
     "source_changed": ["main.tf"], "tests_changed": [], "has_tests": true}
  ],
  "deleted_units": ["modules/old"],
  "agent_config_changed": false,
  "other_files": ["README.md"]
}

A "unit" is a directory under modules/ or stacks/ that holds .tf files.
Only the diff is used; nothing in the changed files is executed.
"""
import json
import os
import re
import subprocess
import sys

UNIT_RE = re.compile(r"^(modules|stacks)/([a-z0-9][a-z0-9-]*)/(.+)$")
AGENT_CONFIG_PREFIXES = (".claude/", ".github/", "CLAUDE.md", ".mcp.json")


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", repo, *args], check=True, capture_output=True, text=True
    ).stdout


def main(argv):
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    base, head = argv[1], argv[2]
    repo = argv[argv.index("--repo") + 1] if "--repo" in argv else "."
    for sha in (base, head):
        # A ref starting with "-" would be read by git as an option.
        if not re.fullmatch(r"[A-Za-z0-9_][\w./~^-]*", sha):
            print(f"refusing suspicious ref: {sha!r}", file=sys.stderr)
            return 2

    merge_base = git(repo, "merge-base", base, head).strip()
    raw = git(repo, "diff", "--name-status", "--no-renames", "-z", merge_base, head)
    parts = [p for p in raw.split("\0") if p]
    changes = list(zip(parts[0::2], parts[1::2]))

    units = {}
    other, agent_config_changed = [], False
    for status, path in changes:
        if path.startswith(AGENT_CONFIG_PREFIXES):
            agent_config_changed = True
        m = UNIT_RE.match(path)
        if not m:
            other.append(path)
            continue
        unit = f"{m.group(1)}/{m.group(2)}"
        rel = m.group(3)
        u = units.setdefault(
            unit,
            {
                "path": unit,
                "kind": "module" if m.group(1) == "modules" else "stack",
                "source_changed": [],
                "tests_changed": [],
            },
        )
        bucket = "tests_changed" if rel.startswith("tests/") else "source_changed"
        u[bucket].append(f"{status} {rel}")

    include = argv[argv.index("--include") + 1].split() if "--include" in argv else []
    if include == ["all"]:
        include = sorted(
            f"{top}/{name}"
            for top in ("modules", "stacks")
            if os.path.isdir(os.path.join(repo, top))
            for name in os.listdir(os.path.join(repo, top))
        )
    for unit in include:
        if not re.fullmatch(r"(modules|stacks)/[a-z0-9][a-z0-9-]*", unit):
            print(f"refusing unit outside modules/ or stacks/: {unit!r}", file=sys.stderr)
            return 2
        u = units.setdefault(
            unit,
            {
                "path": unit,
                "kind": "module" if unit.startswith("modules/") else "stack",
                "source_changed": [],
                "tests_changed": [],
            },
        )
        u["requested"] = True

    present, deleted = [], []
    for unit in sorted(units):
        unit_dir = os.path.join(repo, unit)
        has_tf = os.path.isdir(unit_dir) and any(
            f.endswith(".tf") for f in os.listdir(unit_dir)
        )
        if not has_tf:
            deleted.append(unit)
            continue
        tests_dir = os.path.join(unit_dir, "tests")
        units[unit]["has_tests"] = os.path.isdir(tests_dir) and any(
            f.endswith(".tftest.hcl") for f in os.listdir(tests_dir)
        )
        present.append(units[unit])

    json.dump(
        {
            "base": merge_base,
            "head": git(repo, "rev-parse", head).strip(),
            "units": present,
            "deleted_units": deleted,
            "agent_config_changed": agent_config_changed,
            "other_files": other,
        },
        sys.stdout,
        indent=2,
    )
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
