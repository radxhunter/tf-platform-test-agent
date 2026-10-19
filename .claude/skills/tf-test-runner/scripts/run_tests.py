#!/usr/bin/env python3
"""Run the policy lint, fmt check, validate and terraform test for units.

Usage: run_tests.py <unit-dir> [<unit-dir> ...] [--out FILE]

A unit is `modules/<name>` or `stacks/<name>`, relative to the repository
root (the current directory). Stacks are tested once per `envs/*.tfvars`
file, so assertions in stack tests must hold for every environment.

Terraform runs in a sandbox chosen by TF_TEST_SANDBOX:
  docker (default)  a throwaway container with no network, a read-only root
                    and repository, no capabilities and no environment
                    variables from the host. Terraform code under test (and
                    any provider binary) cannot reach a secret or the network.
  none              terraform on the host. Only for a developer's machine.

Units must be initialised first (prepare.py). The result is printed as JSON
and, with --out, also written to FILE. Exit code 0 only when every step of
every unit passed.
"""
import glob
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
UNIT_RE = re.compile(r"^(modules|stacks)/[a-z0-9][a-z0-9-]*$")
# Pinned by digest so a re-tagged image cannot change what runs.
DEFAULT_IMAGE = (
    "hashicorp/terraform:1.16.6"
    "@sha256:bfffc1ded5fbf0a17beaaf22eb4793980abdb19d0761ff6a3a0efb2ab4d9b316"
)
TIMEOUT_SECONDS = int(os.environ.get("TF_TEST_TIMEOUT", "600"))
MAX_TEXT = 4000


def check_unit(unit):
    unit = unit.replace("\\", "/").rstrip("/")
    if not UNIT_RE.match(unit) or not os.path.isdir(unit):
        raise SystemExit(f"not a unit directory: {unit!r} (expected modules/<name> or stacks/<name>)")
    return unit


def plugin_cache():
    return os.path.abspath(os.environ.get("TF_PLUGIN_CACHE_DIR", os.path.join(".", ".tf-plugin-cache")))


def terraform_cmd(unit, args, network=False):
    sandbox = os.environ.get("TF_TEST_SANDBOX", "docker")
    if sandbox == "none":
        return [os.environ.get("TF_BIN", "terraform"), f"-chdir={unit}", *args], None
    if sandbox != "docker":
        raise SystemExit(f"unknown TF_TEST_SANDBOX={sandbox!r}")
    image = os.environ.get("TF_IMAGE", DEFAULT_IMAGE)
    repo = os.path.abspath(".")
    cache = plugin_cache()
    os.makedirs(cache, exist_ok=True)
    cmd = [
        "docker", "run", "--rm", "--init",
        "--network", "bridge" if network else "none",
        "--read-only", "--tmpfs", "/tmp:rw,size=256m",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--pids-limit", "512", "--memory", "3g", "--cpus", "2",
        "--user", f"{os.getuid()}:{os.getgid()}",
        "--env", "HOME=/tmp", "--env", "TF_IN_AUTOMATION=1",
        "--env", "CHECKPOINT_DISABLE=1",
        # prepare.py needs to write .terraform/ and the cache; tests do not.
        "--volume", f"{repo}:/ws:{'rw' if network else 'ro'}",
        "--volume", f"{cache}:/tf-cache:{'rw' if network else 'ro'}",
        "--workdir", "/ws",
    ]
    if network:
        cmd += ["--env", "TF_PLUGIN_CACHE_DIR=/tf-cache"]
    cmd += [image, f"-chdir={unit}", *args]
    return cmd, None


def run(cmd, timeout=TIMEOUT_SECONDS):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout}s"


def clip(text):
    text = text.strip()
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "\n...[truncated]"


def parse_test_json(stdout):
    runs, diagnostics, summary = [], [], None
    for line in stdout.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        kind = ev.get("type")
        if kind == "test_run" and ev["test_run"].get("progress") == "complete":
            tr = ev["test_run"]
            runs.append({"file": tr["path"].replace("\\", "/"), "run": tr["run"], "status": tr.get("status")})
        elif kind == "diagnostic":
            d = ev["diagnostic"]
            rng = d.get("range") or {}
            diagnostics.append({
                "severity": d.get("severity"),
                "summary": d.get("summary"),
                "detail": clip(d.get("detail") or ""),
                "file": (rng.get("filename") or "").replace("\\", "/"),
                "line": (rng.get("start") or {}).get("line"),
                "run": ev.get("@testrun"),
            })
        elif kind == "test_summary":
            summary = ev["test_summary"]
    return runs, diagnostics, summary


def test_unit(unit):
    result = {"unit": unit, "ok": True}

    code, out, err = run([sys.executable, os.path.join(HERE, "lint_tests.py"), unit])
    result["lint"] = {"ok": code == 0, "errors": [l for l in out.splitlines() if l.strip()]}

    test_files = glob.glob(os.path.join(unit, "tests", "*.tftest.hcl"))
    if test_files:
        cmd, _ = terraform_cmd(unit, ["fmt", "-check", "-diff", "-no-color", "tests"])
        code, out, err = run(cmd)
        result["fmt"] = {"ok": code == 0, "output": clip(out + err)}
    else:
        result["fmt"] = {"ok": True, "output": "no test files"}

    cmd, _ = terraform_cmd(unit, ["validate", "-no-color"])
    code, out, err = run(cmd)
    result["validate"] = {"ok": code == 0, "output": clip(out + err)}

    result["tests"] = []
    if not test_files:
        result["tests"].append({"var_file": None, "status": "no_tests", "runs": [], "diagnostics": []})
    elif result["lint"]["ok"]:
        # Never execute tests that break the policy: a test without a mock
        # would configure a real provider or run the module's own scripts.
        var_files = sorted(glob.glob(os.path.join(unit, "envs", "*.tfvars"))) if unit.startswith("stacks/") else []
        for var_file in var_files or [None]:
            args = ["test", "-json", "-no-color"]
            if var_file:
                args.append("-var-file=" + os.path.relpath(var_file, unit).replace("\\", "/"))
            cmd, _ = terraform_cmd(unit, args)
            code, out, err = run(cmd)
            runs, diags, summary = parse_test_json(out)
            status = (summary or {}).get("status") or ("pass" if code == 0 else "error")
            entry = {
                "var_file": var_file.replace("\\", "/") if var_file else None,
                "status": status,
                "summary": summary,
                "runs": runs,
                "diagnostics": diags,
            }
            if code != 0 and not diags:
                entry["stderr"] = clip(err or out)
            result["tests"].append(entry)
    else:
        result["tests"].append({"var_file": None, "status": "skipped_policy", "runs": [], "diagnostics": []})

    result["ok"] = (
        result["lint"]["ok"]
        and result["fmt"]["ok"]
        and result["validate"]["ok"]
        and all(t["status"] in ("pass", "no_tests") for t in result["tests"])
    )
    return result


def main(argv):
    out_file = None
    if "--out" in argv:
        i = argv.index("--out")
        out_file = argv[i + 1]
        argv = argv[:i] + argv[i + 2 :]
    units = [check_unit(u) for u in argv[1:]]
    if not units:
        print(__doc__, file=sys.stderr)
        return 2
    results = [test_unit(u) for u in units]
    report = {"ok": all(r["ok"] for r in results), "units": results}
    text = json.dumps(report, indent=2)
    print(text)
    if out_file:
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
