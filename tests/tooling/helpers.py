"""Shared helpers for the tooling tests: run scripts as the workflow does."""
import contextlib
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

LINT = os.path.join(ROOT, ".claude", "skills", "tf-test-runner", "scripts", "lint_tests.py")
COVERAGE = os.path.join(ROOT, ".claude", "skills", "tf-coverage", "scripts", "coverage.py")
SCOPE = os.path.join(ROOT, ".claude", "skills", "tf-change-analysis", "scripts", "changed_scope.py")
GUARD = os.path.join(ROOT, ".github", "test-agent", "guard_changes.py")
VALIDATE = os.path.join(ROOT, ".github", "test-agent", "validate_output.py")
RENDER = os.path.join(ROOT, ".github", "test-agent", "render_comment.py")
SCHEMA = os.path.join(ROOT, ".github", "test-agent", "output.schema.json")

VERSIONS = """terraform {
  required_version = ">= 1.9.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}
"""

MAIN = """resource "azurerm_storage_account" "this" {
  name                     = var.name
  min_tls_version          = "TLS1_2"
  account_replication_type = "LRS"
}
"""

VARIABLES = """variable "name" {
  type = string

  validation {
    condition     = length(var.name) > 2
    error_message = "Too short."
  }
}
"""

OUTPUTS = """output "id" {
  value = azurerm_storage_account.this.id
}
"""

GOOD_TEST = """mock_provider "azurerm" {}

variables {
  name = "demo"
}

run "tls_is_enforced" {
  command = plan

  assert {
    condition     = azurerm_storage_account.this.min_tls_version == "TLS1_2"
    error_message = "TLS 1.2 is required."
  }

  assert {
    condition     = azurerm_storage_account.this.account_replication_type == "LRS"
    error_message = "LRS expected."
  }
}

run "rejects_short_name" {
  command = plan

  variables {
    name = "ab"
  }

  expect_failures = [var.name]
}
"""


def run(script, *args, cwd=None):
    return subprocess.run([sys.executable, script, *args], cwd=cwd, capture_output=True, text=True)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.autocrlf=false", *args],
        check=True, capture_output=True, text=True,
    ).stdout


def make_unit(root, unit="modules/demo", test_text=GOOD_TEST):
    base = os.path.join(root, unit)
    write(os.path.join(base, "versions.tf"), VERSIONS)
    write(os.path.join(base, "main.tf"), MAIN)
    write(os.path.join(base, "variables.tf"), VARIABLES)
    write(os.path.join(base, "outputs.tf"), OUTPUTS)
    if test_text is not None:
        write(os.path.join(base, "tests", "main.tftest.hcl"), test_text)
    return base


@contextlib.contextmanager
def temp_repo(**unit_kwargs):
    """A git repository with one committed unit, as the CI checkout would be."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = os.path.join(tmp, "repo")
        os.makedirs(repo)
        git(repo, "init", "-q", "-b", "main")
        make_unit(repo, **unit_kwargs)
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "base")
        yield tmp, repo
