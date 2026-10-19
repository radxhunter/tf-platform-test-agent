#!/usr/bin/env python3
"""Initialise units so run_tests.py can test them without network access.

Usage: prepare.py <unit-dir> [<unit-dir> ...]

Runs `terraform init -backend=false -lockfile=readonly` in the same sandbox
as run_tests.py, but with network access, so providers can be downloaded.
The lock file must already exist and is never changed: a provider whose
checksum does not match the committed lock file fails here.

This is the only step that needs the network. Run it before any secret is
present in the job, and never let the agent call it.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_tests import check_unit, clip, run, terraform_cmd  # noqa: E402


def main(argv):
    units = [check_unit(u) for u in argv[1:]]
    if not units:
        print(__doc__, file=sys.stderr)
        return 2
    failed = False
    for unit in units:
        if not os.path.isfile(os.path.join(unit, ".terraform.lock.hcl")):
            print(f"{unit}: missing .terraform.lock.hcl; commit one (terraform providers lock)")
            failed = True
            continue
        cmd, _ = terraform_cmd(
            unit, ["init", "-backend=false", "-input=false", "-lockfile=readonly", "-no-color"], network=True
        )
        code, out, err = run(cmd)
        print(f"{unit}: init {'ok' if code == 0 else 'FAILED'}")
        if code != 0:
            print(clip(out + err))
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
