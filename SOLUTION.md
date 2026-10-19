# Terraform test agent: solution notes

A custom agent with five reusable skills, run by a GitHub Actions workflow on
every pull request that changes Terraform code. It decides per module or
stack whether tests should be added or updated, writes them, runs them in a
sandbox, and reports results and review findings in the pull request. The
workflow then re-runs everything itself before it commits a single line.

```text
pull_request ──► context ──► checks ──► agent ──► verify ──► publish
                 (who/what)  (no LLM)   (LLM)     (no LLM)   (writes)
```

## Where things are

| Path | What it is |
|---|---|
| `.claude/agents/terraform-test-engineer.md` | The custom agent: role, working order, hard rules, output contract. |
| `.claude/skills/tf-change-analysis/` | Turns a diff into one decision per unit. `scripts/changed_scope.py` maps changed files to units. |
| `.claude/skills/tf-test-authoring/` | How tests are written here. `reference.md` holds patterns that were run and verified. |
| `.claude/skills/tf-test-runner/` | `run_tests.py` (lint, fmt, validate, test → JSON, in a sandbox), `prepare.py` (init), `lint_tests.py` (test policy). |
| `.claude/skills/tf-coverage/` | `coverage.py`: which resources, validations and outputs tests reference. |
| `.claude/skills/tf-risk-review/` | Checklist and evidence rules for findings. |
| `.github/workflows/terraform-test-agent.yml` | The workflow. |
| `.github/test-agent/` | Trusted workflow scripts: run the agent, sanitise the workspace, validate its output against the schema, guard the patch, render the comment. |

The skills are ordinary Claude Code skills. The same files serve a developer
running Claude Code locally (`/tf-test-authoring`, or asking for the
`terraform-test-engineer` agent) and the CI run, so local and CI behaviour
cannot drift apart.

## How a run works

1. **context** reads the pull request and decides whether the agent runs.
   It is skipped for drafts, forks, the `test-agent:skip` label and commits
   made by the agent itself.
2. **checks** (no LLM, no secrets) works out the scope with
   `changed_scope.py`, initialises the units, and runs the existing tests,
   lint, `fmt` and `validate`. It also measures coverage. This is the gate
   that does not depend on a model, and it fails the check when the pull
   request as pushed is broken.
3. **agent** replaces the pull request's `.claude/`, `CLAUDE.md` and
   `.mcp.json` with the base branch's copy, then runs Claude Code headless as
   `terraform-test-engineer`. The agent:
   - plans per unit (`tf-change-analysis`),
   - measures coverage (`tf-coverage`),
   - reviews the code (`tf-risk-review`),
   - writes tests (`tf-test-authoring`),
   - runs them, at most three fix rounds per file (`tf-test-runner`),
   - returns JSON that `--json-schema` validates.

   Only test files are collected from its workspace, as a patch.
4. **verify** (no LLM, no secrets) runs `guard_changes.py` on the patch,
   applies it to a clean checkout and re-runs every test in scope. The
   agent's own claim that "tests pass" is never used.
5. **publish** (the only job that can write) commits the verified test files
   to the pull request branch, marks the new commit with a
   `tf-test-agent/verify` status, and creates or updates one comment:
   decisions, test changes, the independent test run, coverage before and
   after, findings, and limitations.

## Main decisions and what they cost

| Decision | Why | What it costs |
|---|---|---|
| **Claude Code CLI headless** with a custom agent and skills, not a hand-written agent loop. | Skills, tool permissions, structured output and budget limits already exist and are tested. The same config works locally. | Ties the agent to one vendor's runtime. The model is swappable (`vars.TEST_AGENT_MODEL`), the runtime is not. |
| **The LLM never holds a write token.** It produces a patch; deterministic jobs check, test and commit it. | A prompt-injected or confused agent can at worst produce a patch that the guard rejects. | Four jobs and artifacts instead of one step. Each run takes a few minutes longer. |
| **Re-run everything after the agent.** | Agents report success they did not achieve. The comment's pass/fail facts come from `verify.json`, never from the agent. | Tests run twice. |
| **Terraform runs in a container with `--network none`, a read-only root and a read-only repo, no capabilities and no environment.** Only `init` gets network, and only before any secret is in the job. | `terraform plan` runs code: `modules/function-app` runs a shell script through `data "external"`, and providers are binaries. A test file or a PR could turn that into secret theft. | Needs Docker on the runner. Locally, `TF_TEST_SANDBOX=none` runs on the host. |
| **A test policy enforced by code** (`lint_tests.py`): every provider mocked, no `provider` blocks, no foreign modules, explicit `command`. Files that break it are not executed. | This makes "tests never touch the cloud and never run the module's scripts" a property of the pipeline, not a promise in a prompt. | Rules out tests against a real provider. That is the point here, but it is a limit (see below). |
| **Agent config always from the base branch.** | A pull request could otherwise widen the agent's tools or rewrite its instructions while it holds the key. | A change to the agent only takes effect after it is merged, so it cannot be tried out on its own pull request. |
| **Tool allowlist on the command line** (`dontAsk` mode). The agent gets Read, Glob, Grep, Skill, Edit/Write on `*/tests/*.tftest.hcl`, and Bash for exactly two scripts. | A settings file that fails validation is silently ignored in print mode. Flags fail closed. | Long command line in `run_agent.sh`. |
| **Committed tests must pass.** Suspicious code becomes a finding, never a red test. | People decide about infrastructure. A failing test for a design question would block merges the team may want. | A real bug is reported, not enforced. |
| **Commit to the PR branch with `GITHUB_TOKEN`.** | Simple, and it cannot trigger itself in a loop: pushes made with `GITHUB_TOKEN` start no workflow. | The new commit gets no new workflow run. The status set by `publish` covers it. A GitHub App token would give a full re-run (see production). |
| **Plan-first tests with mocks.** `apply` with mocks only for outputs. | Fast (seconds per module), no credentials, deterministic. | Cannot prove Azure accepts the configuration. |

## How the LLM is controlled, and what that caught

| Control | Enforced by |
|---|---|
| What the agent may touch | `--tools`, `--allowedTools` and `dontAsk` in `run_agent.sh`, then `guard_changes.py` on the patch |
| What a test may do | `lint_tests.py` (policy P1-P6), and the sandbox in `run_tests.py` |
| Whether tests pass | `verify` re-runs them; the agent's claim is not used |
| The shape of the result | `validate_output.py` against `output.schema.json` |
| Whether a secret leaked | Exact-value and pattern search on everything the agent produced |
| Spend and time | `--max-budget-usd`, job `timeout-minutes`, three fix rounds per file |

Building it surfaced four problems. Each was caught by running something,
not by reading the model's output, and none of them let unverified work
into a pull request:

1. **Mock patterns that looked right but failed.** Before writing
   `reference.md` I ran every pattern. Two were wrong: a nested `identity`
   block in `mock_resource` is an object, not a list, and a stack test cannot
   address resources inside a module. A third problem only showed under
   `apply`: mocked IDs are random strings that dependent resources reject. The
   skill now teaches the fixes, not the guesses.
2. **`--json-schema` was silently ignored together with `--agent`.** The
   first CI run wrote good tests, but returned JSON in its own shape. The
   workflow refused to publish it ([run](https://github.com/radxhunter/tf-platform-test-agent/actions/runs/39249355973)).
   Fix: the schema is in the prompt, and the result is validated by our own
   code ([#3](https://github.com/radxhunter/tf-platform-test-agent/pull/3)).
3. **The trusted side was stale.** A pull request's `base.sha` is not
   refreshed when `main` moves, so the second run used the agent configuration
   from before the fix. The workflow now takes the current tip of the base
   branch ([#4](https://github.com/radxhunter/tf-platform-test-agent/pull/4)).
4. **A bug in my own guard.** The first run on the example pull request was
   the first to *modify* an existing test file, and the guard crashed while
   comparing its assertions (a relative `GIT_INDEX_FILE`). The pipeline failed
   safe: nothing was committed and the check went red. The comment did not
   say why, which was fixed along with the bug
   ([#6](https://github.com/radxhunter/tf-platform-test-agent/pull/6)).

The agent also tried, unprompted, to read several files with
`cd modules && for ... cat ...` in Bash. `dontAsk` denied it, the denial is
in the transcript, and the agent switched to the Read tool.

## Prerequisites and how to run it

- A GitHub repository with Actions enabled. The workflow file is on the
  default branch, and so are `.claude/` and `.github/test-agent/`.
- A repository secret: `ANTHROPIC_API_KEY`, or `CLAUDE_CODE_OAUTH_TOKEN`
  from `claude setup-token`. Without either, the agent step reports that and
  the deterministic checks still run.
- Optional repository variables: `TEST_AGENT_MODEL` (default
  `claude-sonnet-5-5`) and `TEST_AGENT_MAX_USD` (default `5`, a hard spend
  cap per run).
- Settings → Actions → General → *Workflow permissions*: the default
  read-only is fine. Each job asks for what it needs.

Runs happen on their own for pull requests that touch `modules/` or
`stacks/`. To run it by hand, for example to backfill tests for the whole
repository on a pull request:

```sh
gh workflow run terraform-test-agent.yml -f pr=<number> -f include=all
```

Locally, with Terraform 1.9 or newer on the host instead of Docker:

```sh
export TF_TEST_SANDBOX=none
python3 .claude/skills/tf-test-runner/scripts/prepare.py modules/key-vault
python3 .claude/skills/tf-test-runner/scripts/run_tests.py modules/key-vault
python3 .claude/skills/tf-coverage/scripts/coverage.py modules/* --format markdown
```

## Example run

Pull request [#5](https://github.com/radxhunter/tf-platform-test-agent/pull/5)
sends Key Vault audit logs to Log Analytics, validates log retention
(30-730 days) and makes retention configurable per environment (prod 90). It
breaks the existing key-vault tests on purpose, with a new required input.
The [run](https://github.com/radxhunter/tf-platform-test-agent/actions/runs/39251842145)
went like this:

1. **checks** failed, correctly. With the pull request as pushed, key-vault
   tests error with "No value for required variable". That result goes to the
   agent as `baseline.json`.
2. **agent** (24 turns, $0.12, no tool denied) loaded `tf-change-analysis`
   and read the scope, diff and baseline. It then loaded `tf-test-authoring`,
   `tf-coverage` and `tf-risk-review`, read `reference.md`, the changed code
   and the existing tests, made three edits, and ran `tf-test-runner` once on
   all three units. Its decisions:

   | Unit | Decision | Reason given |
   |---|---|---|
   | `modules/key-vault` | updated tests | The new required input broke the baseline. Added it to the file-level variables, changed no assertion, and added a run for the new diagnostic setting (workspace wiring, `audit` group, `AllMetrics`). |
   | `modules/log-analytics-workspace` | added tests | The new validation had no test. Added accepted boundaries 30 and 730, and rejected values 29 and 731 with `expect_failures`. |
   | `stacks/data-platform` | no change | The new wiring is a module *input*, which a stack test cannot see. Existing tests still pass in dev and prod. |

3. **verify**: the guard found three test files in scope, no removed
   assertions. The re-run passed: key-vault 3/3, log-analytics 6/6, stack 5/5
   in dev and 5/5 in prod.
4. **publish** committed the tests as `04a8487`, set `tf-test-agent/verify`
   to success on it, and posted the
   [comment](https://github.com/radxhunter/tf-platform-test-agent/pull/5#issuecomment-6267096267).
   It has two low/info findings on the change itself. One: the stack's
   `log_retention_days` has no validation of its own, so a bad value fails
   with an error naming the module's variable. The other: dev keeps the
   30-day default while audit logs now flow to the workspace.

The run is red overall because `checks` is red. That is intended: the
commit as pushed was broken, and the agent's follow-up commit carries its own
green status.

The backfill run on [#2](https://github.com/radxhunter/tf-platform-test-agent/pull/2)
added 24 test runs to the six units that had none, and found every planted
risk without being told to look for them:

- FTP allowed on the function app,
- *Storage Blob Data Owner* where a narrower role fits,
- a shell script run during plan,
- private endpoints without DNS zones,
- public access on by default in three modules,
- unvalidated retention.

It left those values unasserted on purpose and reported them, so the tests
do not endorse them.

Two runs of the same change are not identical. The first, failed attempt on
#5 also added a stack test that checked the retention range; the second
judged that the wiring is not observable from the stack and added none. Both
are defensible, and both passed the same guard and re-run. That variance is
why those controls exist.

## What the generated tests can and cannot show

They can show that:

- the configuration is valid and every input combination tested plans,
- security-relevant settings have the values the code intends (TLS, public
  access, RBAC, deny-by-default rules) for the inputs tested,
- validations reject bad input and accept boundary values,
- `for_each`, `dynamic` blocks and outputs have the right shape and wiring,
- environment rules hold for each `envs/*.tfvars` file of a stack.

They cannot show that:

- Azure accepts the configuration (naming rules, quotas, SKU and region
  availability, API constraints the provider only learns at apply time),
- anything about values that only exist after a real apply (IDs, IPs, URLs).
  Mocks generate them,
- the infrastructure behaves correctly at runtime (network paths, DNS
  resolution through private endpoints, RBAC propagation),
- the provider behaves as documented. A mocked provider skips its logic.

Coverage is *reference* coverage: an item counts as covered when an assert
mentions it. It finds gaps. It does not measure test quality.

## Assumptions

- Contributors with write access are trusted roughly as much as GitHub
  already trusts them: they can edit workflows anyway. The untrusted inputs
  are the *content* the agent reads (code, comments, diffs) and fork pull
  requests.
- `terraform test` with mocked providers is the agreed test level. No
  Terratest, no real deployments.
- One repository, one stack, units under `modules/` and `stacks/`.
- The team reviews the agent's commits like any other commit before merge.

## Limitations

- Fork pull requests get the deterministic checks only, with results in the
  job summary. A read-only token cannot comment on them.
- The guard reports removed assertions but cannot judge whether a modified
  assertion is weaker. A reviewer must read changed assertions; the comment
  lists them with their old value.
- `lint_tests.py` and `coverage.py` use a small HCL reader, not a full
  parser. Unusual formatting could hide an item from coverage. The lint errs
  towards refusing.
- Model output varies between runs. The guard, policy and re-run bound the
  damage, not the quality. A weak but passing test can still be committed;
  that is why commits are reviewed.
- After the agent pushes, the pull request has the agent's commit plus a
  status, but no full re-run of the workflow.

## With many more modules, teams or repositories

- **Repositories**: move the workflow into a reusable workflow
  (`workflow_call`) and the agent and skills into a Claude Code plugin in a
  central repository, pinned by version. Each repository keeps only a thin
  caller and its own `reference.md` additions.
- **Modules**: run units in parallel (a matrix over `scope.json`), one agent
  per unit with a per-unit budget, and cache provider downloads. The scope
  logic already limits work to what changed.
- **Teams**: CODEOWNERS per module routes findings to the right people.
  Severity thresholds and rules move into a config file per team. The
  findings feed a dashboard so recurring ones become module fixes, not
  repeated comments.
- **Cost and noise**: track cost, turns, accepted versus reverted agent
  commits and findings marked as useful. These numbers decide the model and
  whether a rule stays.

## For a production version I would

- push with a **GitHub App** token, so the agent's commit triggers a normal
  re-run (the loop guard for that is already in `context`), and keep the key
  in an **environment** with protection rules,
- run the agent on **self-hosted ephemeral runners** with an egress
  allowlist (Anthropic API, Terraform registry only), as a second layer
  under the container sandbox,
- add a **mutation check**: break the code under test on purpose (flip a
  `true`, drop a block) and require a generated test to fail. That measures
  whether tests check anything,
- support **maintainer-triggered runs for forks** (`/test-agent` comment by
  someone with write access, running the base branch's workflow on a pinned
  head SHA),
- add **plan-level policy** next to tests (Checkov, tfsec or OPA) so known
  rules are not left to the model's memory,
- keep **evaluation pull requests**: a fixed set of changes with known right
  answers, re-run when the agent, skills or model change.
