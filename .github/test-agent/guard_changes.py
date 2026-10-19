#!/usr/bin/env python3
"""Check the agent's patch before anything is tested, committed or reported.

Usage: guard_changes.py <repo> <patch> <scope.json> --out guard.json

Runs `git apply --check` first, then inspects the patch itself:

  G1  every touched path is <unit>/tests/<name>.tftest.hcl,
  G2  that unit is in scope for this run,
  G3  files are only added or modified: no deletes, renames, mode changes,
      symlinks or binary content,
  G4  the patch is under MAX_BYTES and touches at most MAX_FILES files,

and, for files that already existed, records every run block or assert the
patch removes (W1). Removals are allowed, since a behaviour change can make
an assertion obsolete, but they are always shown to the reviewer.

Violations (G*) reject the whole patch. Exit code 1 when rejected.
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".claude", "skills", "tf-coverage", "scripts"))
from hcl_lite import blocks, strip_comments  # noqa: E402

TEST_PATH = re.compile(r"^((?:modules|stacks)/[a-z0-9][a-z0-9-]*)/tests/[a-z0-9_-]+\.tftest\.hcl$")
MAX_BYTES = 200_000
MAX_FILES = 30


def git(repo, *args, check=True, input_text=None):
    return subprocess.run(["git", "-C", repo, *args], check=check, capture_output=True, text=True, input=input_text)


def runs_and_asserts(text):
    found = {}
    for labels, body in blocks(strip_comments(text), "run"):
        name = labels[0] if labels else "?"
        found[name] = sum(1 for _ in blocks(body, "assert"))
    return found


def main(argv):
    repo, patch_path, scope_path = argv[1], argv[2], argv[3]
    out_path = argv[argv.index("--out") + 1]
    scope_units = {u["path"] for u in json.load(open(scope_path))["units"]}
    patch = open(patch_path, encoding="utf-8", errors="replace").read()

    violations, warnings, files = [], [], []
    if not patch.strip():
        result = {"ok": True, "empty": True, "files": [], "violations": [], "warnings": []}
        json.dump(result, open(out_path, "w"), indent=2)
        print("empty patch")
        return 0

    if len(patch.encode()) > MAX_BYTES:
        violations.append(f"G4 patch is {len(patch.encode())} bytes, limit {MAX_BYTES}")

    check = git(repo, "apply", "--check", "--numstat", "--summary", os.path.abspath(patch_path), check=False)
    if check.returncode != 0:
        violations.append("patch does not apply cleanly: " + check.stderr.strip()[:500])

    # Headers of each file section in a git diff.
    for header in re.findall(r"(?m)^diff --git a/(\S+) b/(\S+)$", patch):
        a, b = header
        if a != b:
            violations.append(f"G3 rename {a} -> {b}")
        files.append(b)
    for kind in ("deleted file mode", "rename from", "copy from", "old mode", "new mode 120000", "GIT binary patch", "Binary files"):
        if kind in patch:
            violations.append(f"G3 patch contains '{kind}'")
    if len(files) > MAX_FILES:
        violations.append(f"G4 patch touches {len(files)} files, limit {MAX_FILES}")

    for path in files:
        m = TEST_PATH.match(path)
        if not m:
            violations.append(f"G1 {path} is not a test file under <unit>/tests/")
            continue
        if m.group(1) not in scope_units:
            violations.append(f"G2 {path} belongs to {m.group(1)}, which is not in scope")

    if not violations:
        for path in files:
            before = git(repo, "show", f"HEAD:{path}", check=False)
            if before.returncode != 0:
                continue
            old = runs_and_asserts(before.stdout)
            # Reconstruct the new file by applying the patch to a temporary index.
            env_index = os.path.join(repo, ".git", "guard-index")
            subprocess.run(["git", "-C", repo, "read-tree", "HEAD"], env={**os.environ, "GIT_INDEX_FILE": env_index}, check=True)
            subprocess.run(
                ["git", "-C", repo, "apply", "--cached", "--include", path, os.path.abspath(patch_path)],
                env={**os.environ, "GIT_INDEX_FILE": env_index}, check=True, capture_output=True,
            )
            after = subprocess.run(
                ["git", "-C", repo, "show", f":{path}"],
                env={**os.environ, "GIT_INDEX_FILE": env_index}, check=True, capture_output=True, text=True,
            ).stdout
            os.remove(env_index)
            new = runs_and_asserts(after)
            for run, count in old.items():
                if run not in new:
                    warnings.append(f"W1 {path}: run '{run}' was removed ({count} asserts)")
                elif new[run] < count:
                    warnings.append(f"W1 {path}: run '{run}' went from {count} to {new[run]} asserts")

    result = {"ok": not violations, "empty": False, "files": files, "violations": violations, "warnings": warnings}
    json.dump(result, open(out_path, "w"), indent=2)
    for line in violations + warnings:
        print(line)
    return 0 if not violations else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
