import os
import tempfile
import unittest

import helpers as h


def lint(test_text):
    with tempfile.TemporaryDirectory() as tmp:
        unit = h.make_unit(tmp, test_text=test_text)
        proc = h.run(h.LINT, unit)
        return proc.returncode, proc.stdout


class LintPolicy(unittest.TestCase):
    def test_good_file_passes(self):
        code, out = lint(h.GOOD_TEST)
        self.assertEqual(code, 0, out)

    def test_unmocked_provider_is_rejected(self):
        # Without the mock, the real provider would be configured (P1).
        code, out = lint(h.GOOD_TEST.replace('mock_provider "azurerm" {}\n', ""))
        self.assertEqual(code, 1)
        self.assertIn("P1", out)
        self.assertIn("azurerm", out)

    def test_real_provider_block_is_rejected(self):
        code, out = lint('provider "azurerm" {\n  features {}\n}\n' + h.GOOD_TEST)
        self.assertEqual(code, 1)
        self.assertIn("P2", out)

    def test_module_in_run_is_rejected(self):
        text = h.GOOD_TEST.replace(
            "command = plan\n\n  assert {\n    condition     = azurerm_storage_account.this.min_tls_version",
            'command = plan\n\n  module {\n    source = "../other"\n  }\n\n  assert {\n    condition     = azurerm_storage_account.this.min_tls_version',
            1,
        )
        code, out = lint(text)
        self.assertEqual(code, 1)
        self.assertIn("P3", out)

    def test_missing_command_is_rejected(self):
        code, out = lint(h.GOOD_TEST.replace("  command = plan\n\n  assert", "  assert", 1))
        self.assertEqual(code, 1)
        self.assertIn("P4", out)

    def test_bad_and_duplicate_run_names_are_rejected(self):
        code, out = lint(h.GOOD_TEST.replace("rejects_short_name", "tls_is_enforced"))
        self.assertIn("P5", out)
        code, out = lint(h.GOOD_TEST.replace("tls_is_enforced", "TLS-Is-Enforced"))
        self.assertIn("P5", out)

    def test_file_without_any_assert_is_rejected(self):
        code, out = lint('mock_provider "azurerm" {}\n\nrun "empty" {\n  command = plan\n}\n')
        self.assertEqual(code, 1)
        self.assertIn("P6", out)

    def test_comments_do_not_hide_violations(self):
        # A commented-out mock must not count as a mock.
        code, out = lint(h.GOOD_TEST.replace('mock_provider "azurerm" {}', '# mock_provider "azurerm" {}'))
        self.assertEqual(code, 1)
        self.assertIn("P1", out)

    def test_unit_without_required_providers_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            unit = h.make_unit(tmp)
            os.remove(os.path.join(unit, "versions.tf"))
            proc = h.run(h.LINT, unit)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("required_providers", proc.stdout)


if __name__ == "__main__":
    unittest.main()
