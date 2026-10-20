import json
import os
import unittest

import helpers as h

SCOPE = {"units": [{"path": "modules/demo"}]}


def guard(tmp, repo, patch_text):
    """Run the guard the way the workflow does: relative repo path, absolute patch."""
    patch = os.path.join(tmp, "agent.patch")
    scope = os.path.join(tmp, "scope.json")
    out = os.path.join(tmp, "guard.json")
    h.write(patch, patch_text)
    h.write(scope, json.dumps(SCOPE))
    proc = h.run(h.GUARD, os.path.basename(repo), patch, scope, "--out", out, cwd=os.path.dirname(repo))
    result = None
    if os.path.exists(out):
        with open(out, encoding="utf-8") as f:
            result = json.load(f)
    return proc, result


class GuardPatch(unittest.TestCase):
    def patch_of(self, repo):
        """The patch of the working tree changes, then a clean checkout again.

        In CI the guard sees the pull request checkout *without* the agent's
        changes, and the patch comes from the agent's workspace.
        """
        h.git(repo, "add", "-N", ".")
        patch = h.git(repo, "diff", "--no-color")
        h.git(repo, "reset", "-q", "--hard")
        h.git(repo, "clean", "-fdq")
        return patch

    def test_empty_patch_is_ok(self):
        with h.temp_repo() as (tmp, repo):
            proc, result = guard(tmp, repo, "")
            self.assertEqual(proc.returncode, 0)
            self.assertTrue(result["empty"])

    def test_new_test_file_in_scope_is_accepted(self):
        with h.temp_repo() as (tmp, repo):
            h.write(os.path.join(repo, "modules/demo/tests/extra.tftest.hcl"), h.GOOD_TEST)
            h.git(repo, "add", "-N", "modules/demo/tests/extra.tftest.hcl")
            proc, result = guard(tmp, repo, self.patch_of(repo))
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(result["files"], ["modules/demo/tests/extra.tftest.hcl"])

    def test_modified_existing_test_is_accepted(self):
        # Regression for the crash seen on the first example pull request.
        with h.temp_repo() as (tmp, repo):
            path = os.path.join(repo, "modules/demo/tests/main.tftest.hcl")
            h.write(path, h.GOOD_TEST.replace('name = "demo"', 'name = "demo-two"'))
            proc, result = guard(tmp, repo, self.patch_of(repo))
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(result["violations"], [])

    def test_removed_assertion_is_a_warning_not_a_violation(self):
        with h.temp_repo() as (tmp, repo):
            path = os.path.join(repo, "modules/demo/tests/main.tftest.hcl")
            weakened = h.GOOD_TEST.replace(
                '\n  assert {\n    condition     = azurerm_storage_account.this.account_replication_type == "LRS"\n    error_message = "LRS expected."\n  }\n',
                "",
            )
            self.assertNotEqual(weakened, h.GOOD_TEST)
            h.write(path, weakened)
            proc, result = guard(tmp, repo, self.patch_of(repo))
            self.assertEqual(proc.returncode, 0)
            self.assertTrue(any("W1" in w and "tls_is_enforced" in w for w in result["warnings"]), result)

    def test_removed_run_is_a_warning(self):
        with h.temp_repo() as (tmp, repo):
            path = os.path.join(repo, "modules/demo/tests/main.tftest.hcl")
            h.write(path, h.GOOD_TEST[: h.GOOD_TEST.index('run "rejects_short_name"')])
            proc, result = guard(tmp, repo, self.patch_of(repo))
            self.assertEqual(proc.returncode, 0)
            self.assertTrue(any("rejects_short_name" in w for w in result["warnings"]), result)

    def test_change_to_infrastructure_code_is_rejected(self):
        with h.temp_repo() as (tmp, repo):
            with open(os.path.join(repo, "modules/demo/main.tf"), "a", newline="\n") as f:
                f.write("# agent was here\n")
            proc, result = guard(tmp, repo, self.patch_of(repo))
            self.assertEqual(proc.returncode, 1)
            self.assertTrue(any(v.startswith("G1") for v in result["violations"]))

    def test_change_to_workflow_is_rejected(self):
        with h.temp_repo() as (tmp, repo):
            h.write(os.path.join(repo, ".github/workflows/x.yml"), "name: x\n")
            h.git(repo, "add", "-N", ".github/workflows/x.yml")
            proc, result = guard(tmp, repo, self.patch_of(repo))
            self.assertEqual(proc.returncode, 1)
            self.assertTrue(any("G1" in v for v in result["violations"]))

    def test_test_file_of_a_unit_out_of_scope_is_rejected(self):
        with h.temp_repo() as (tmp, repo):
            h.make_unit(repo, unit="modules/other")
            h.git(repo, "add", "-A")
            h.git(repo, "commit", "-q", "-m", "other")
            h.write(os.path.join(repo, "modules/other/tests/main.tftest.hcl"), h.GOOD_TEST + "\n")
            proc, result = guard(tmp, repo, self.patch_of(repo))
            self.assertEqual(proc.returncode, 1)
            self.assertTrue(any(v.startswith("G2") for v in result["violations"]))

    def test_deleting_a_test_file_is_rejected(self):
        with h.temp_repo() as (tmp, repo):
            h.git(repo, "rm", "-q", "modules/demo/tests/main.tftest.hcl")
            patch = h.git(repo, "diff", "--cached", "--no-color")
            h.git(repo, "reset", "-q", "--hard")
            proc, result = guard(tmp, repo, patch)
            self.assertEqual(proc.returncode, 1)
            self.assertTrue(any("G3" in v for v in result["violations"]))

    def test_path_tricks_are_rejected(self):
        with h.temp_repo() as (tmp, repo):
            h.write(os.path.join(repo, "modules/demo/tests/sub/deep.tftest.hcl"), h.GOOD_TEST)
            h.git(repo, "add", "-N", "modules/demo/tests/sub/deep.tftest.hcl")
            proc, result = guard(tmp, repo, self.patch_of(repo))
            self.assertEqual(proc.returncode, 1)

    def test_patch_that_does_not_apply_is_rejected(self):
        with h.temp_repo() as (tmp, repo):
            path = os.path.join(repo, "modules/demo/tests/main.tftest.hcl")
            h.write(path, h.GOOD_TEST.replace('name = "demo"', 'name = "x1"'))
            patch = self.patch_of(repo)
            h.git(repo, "checkout", "--", ".")
            h.write(path, h.GOOD_TEST.replace('name = "demo"', 'name = "changed-underneath"'))
            h.git(repo, "commit", "-aq", "-m", "moved")
            proc, result = guard(tmp, repo, patch)
            self.assertEqual(proc.returncode, 1)
            self.assertTrue(any("does not apply" in v for v in result["violations"]))

    def test_oversized_patch_is_rejected(self):
        with h.temp_repo() as (tmp, repo):
            big = h.GOOD_TEST + "# " + "x" * 250_000 + "\n"
            h.write(os.path.join(repo, "modules/demo/tests/big.tftest.hcl"), big)
            h.git(repo, "add", "-N", "modules/demo/tests/big.tftest.hcl")
            proc, result = guard(tmp, repo, self.patch_of(repo))
            self.assertEqual(proc.returncode, 1)
            self.assertTrue(any("G4" in v for v in result["violations"]))


if __name__ == "__main__":
    unittest.main()
