import json
import os
import tempfile
import unittest

import helpers as h


class ChangedScope(unittest.TestCase):
    def test_maps_changed_files_to_units(self):
        with h.temp_repo() as (tmp, repo):
            h.make_unit(repo, unit="modules/other", test_text=None)
            h.git(repo, "add", "-A")
            h.git(repo, "commit", "-q", "-m", "other")
            base = h.git(repo, "rev-parse", "HEAD").strip()
            with open(os.path.join(repo, "modules/demo/main.tf"), "a", newline="\n") as f:
                f.write("# change\n")
            with open(os.path.join(repo, "README.md"), "w") as f:
                f.write("x\n")
            h.write(os.path.join(repo, ".claude/skills/x/SKILL.md"), "x\n")
            h.git(repo, "add", "-A")
            h.git(repo, "commit", "-q", "-m", "change")
            proc = h.run(h.SCOPE, base, "HEAD", "--repo", repo)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            data = json.loads(proc.stdout)
            self.assertEqual([u["path"] for u in data["units"]], ["modules/demo"])
            self.assertTrue(data["units"][0]["has_tests"])
            self.assertIn("README.md", data["other_files"])
            self.assertTrue(data["agent_config_changed"])

    def test_include_adds_unchanged_units_and_marks_them(self):
        with h.temp_repo() as (tmp, repo):
            h.make_unit(repo, unit="modules/other", test_text=None)
            h.git(repo, "add", "-A")
            h.git(repo, "commit", "-q", "-m", "other")
            proc = h.run(h.SCOPE, "HEAD", "HEAD", "--repo", repo, "--include", "all")
            data = json.loads(proc.stdout)
            self.assertEqual(sorted(u["path"] for u in data["units"]), ["modules/demo", "modules/other"])
            other = [u for u in data["units"] if u["path"] == "modules/other"][0]
            self.assertTrue(other["requested"])
            self.assertFalse(other["has_tests"])

    def test_refuses_refs_that_look_like_options_and_units_outside_scope(self):
        with h.temp_repo() as (tmp, repo):
            self.assertEqual(h.run(h.SCOPE, "--output=/tmp/x", "HEAD", "--repo", repo).returncode, 2)
            proc = h.run(h.SCOPE, "HEAD", "HEAD", "--repo", repo, "--include", ".github")
            self.assertEqual(proc.returncode, 2)

    def test_deleted_unit_is_reported_not_tested(self):
        with h.temp_repo() as (tmp, repo):
            base = h.git(repo, "rev-parse", "HEAD").strip()
            h.git(repo, "rm", "-rq", "modules/demo")
            h.git(repo, "commit", "-q", "-m", "delete")
            data = json.loads(h.run(h.SCOPE, base, "HEAD", "--repo", repo).stdout)
            self.assertEqual(data["units"], [])
            self.assertEqual(data["deleted_units"], ["modules/demo"])


class Coverage(unittest.TestCase):
    def test_reports_covered_and_uncovered_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            unit = h.make_unit(tmp)
            data = json.loads(h.run(h.COVERAGE, unit).stdout)[0]
            by = {i["address"]: i["covered"] for i in data["items"]}
            self.assertTrue(by["azurerm_storage_account.this"])
            self.assertTrue(by["var.name"])  # validation covered by expect_failures
            self.assertFalse(by["output.id"])
            self.assertEqual((data["covered"], data["total"]), (2, 3))

    def test_unit_without_tests_is_zero_percent(self):
        with tempfile.TemporaryDirectory() as tmp:
            unit = h.make_unit(tmp, test_text=None)
            data = json.loads(h.run(h.COVERAGE, unit).stdout)[0]
            self.assertEqual(data["percent"], 0)

    def test_assert_inside_a_comment_does_not_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = h.GOOD_TEST.replace(
                "azurerm_storage_account.this.min_tls_version", "var.name"
            ).replace("azurerm_storage_account.this.account_replication_type", "var.name")
            text += "# condition = azurerm_storage_account.this.id != null\n"
            unit = h.make_unit(tmp, test_text=text)
            data = json.loads(h.run(h.COVERAGE, unit).stdout)[0]
            by = {i["address"]: i["covered"] for i in data["items"]}
            self.assertFalse(by["azurerm_storage_account.this"])


class ValidateOutput(unittest.TestCase):
    VALID = {
        "summary": "ok",
        "units": [{"path": "modules/demo", "decision": "no_change", "reason": "r", "skills_used": ["tf-coverage"]}],
        "test_changes": [],
        "findings": [],
        "limitations": [],
    }

    def check(self, doc):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "o.json")
            h.write(path, json.dumps(doc))
            proc = h.run(h.VALIDATE, h.SCHEMA, path)
            return proc.returncode, proc.stdout

    def test_valid_document_passes(self):
        self.assertEqual(self.check(self.VALID)[0], 0)

    def test_the_shape_the_model_invented_on_the_first_run_fails(self):
        bad = dict(self.VALID)
        bad["units"] = [{"path": "modules/demo", "decision": "no_change", "reason": "r"}]
        bad["skills_used"] = ["tf-coverage"]
        code, out = self.check(bad)
        self.assertEqual(code, 1)
        self.assertIn("skills_used", out)

    def test_path_outside_modules_and_stacks_fails(self):
        bad = json.loads(json.dumps(self.VALID))
        bad["units"][0]["path"] = ".github/workflows"
        self.assertEqual(self.check(bad)[0], 1)

    def test_test_change_outside_tests_directory_fails(self):
        bad = json.loads(json.dumps(self.VALID))
        bad["test_changes"] = [{"file": "modules/demo/main.tf", "change": "modified", "runs": [], "rationale": "x"}]
        self.assertEqual(self.check(bad)[0], 1)

    def test_too_long_text_and_unknown_severity_fail(self):
        bad = json.loads(json.dumps(self.VALID))
        bad["summary"] = "x" * 801
        self.assertEqual(self.check(bad)[0], 1)
        bad = json.loads(json.dumps(self.VALID))
        bad["findings"] = [{"severity": "critical", "category": "security", "file": "f", "line": 1, "title": "t",
                            "detail": "d", "evidence": "e", "in_diff": True}]
        self.assertEqual(self.check(bad)[0], 1)


class RenderComment(unittest.TestCase):
    def render(self, files, **meta):
        with tempfile.TemporaryDirectory() as tmp:
            for name, doc in files.items():
                h.write(os.path.join(tmp, name), json.dumps(doc))
            args = [h.RENDER, "--dir", tmp]
            for k, v in meta.items():
                args += ["--meta", f"{k}={v}"]
            proc = h.run(*args)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            return proc.stdout

    def hostile_output(self):
        doc = json.loads(json.dumps(ValidateOutput.VALID))
        doc["summary"] = "Hi @everyone <script>alert(1)</script> [click](http://evil.example)"
        doc["units"][0]["reason"] = "pipe | breaks | tables\nnewline"
        doc["findings"] = [{
            "severity": "high", "category": "security", "file": "a.tf", "line": 1,
            "title": "@maintainer look", "detail": "<img src=x onerror=1>",
            "evidence": "x\n~~~\n# injected heading", "in_diff": True,
        }]
        return {"output": doc, "meta": {"num_turns": 1}}

    def test_agent_text_is_neutralised(self):
        body = self.render({"agent-result.json": self.hostile_output()}, agent_status="success")
        self.assertNotIn("<script>", body)
        self.assertNotIn("<img", body)
        self.assertNotIn("@everyone", body)
        self.assertNotIn("@maintainer", body)
        self.assertNotIn("](http://evil", body)
        # the evidence cannot close its own fence and start a heading
        self.assertNotIn("~~~\n# injected heading", body)

    def test_pass_fail_facts_come_from_verify_not_from_the_agent(self):
        verify = {"ok": False, "units": [{
            "unit": "modules/demo", "ok": False,
            "lint": {"ok": True, "errors": []}, "fmt": {"ok": True, "output": ""},
            "validate": {"ok": True, "output": ""},
            "tests": [{"var_file": None, "status": "fail", "summary": {"passed": 0, "failed": 1, "errored": 0}, "runs": [], "diagnostics": []}],
        }]}
        body = self.render(
            {"agent-result.json": {"output": ValidateOutput.VALID, "meta": {}},
             "guard.json": {"ok": True, "empty": False, "files": [], "violations": [], "warnings": []},
             "verify.json": verify},
            agent_status="success", push="pushed:abc1234",
        )
        self.assertIn("did not pass the independent re-run", body)
        self.assertNotIn("committed as abc1234", body)

    def test_missing_verification_is_said_plainly(self):
        body = self.render({"agent-result.json": {"output": ValidateOutput.VALID, "meta": {}}}, agent_status="success")
        self.assertIn("verification step produced no results", body)

    def test_agent_failure_is_reported_first(self):
        body = self.render({}, agent_status="no API key is configured")
        self.assertIn("Agent did not run to completion", body)

    def test_comment_has_the_marker_used_to_update_it(self):
        self.assertTrue(self.render({}, agent_status="x").startswith("<!-- tf-test-agent -->"))


if __name__ == "__main__":
    unittest.main()
