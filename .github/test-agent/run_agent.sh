#!/usr/bin/env bash
# Run the terraform-test-engineer agent headless, with a fixed tool allowlist.
#
# Usage: run_agent.sh <out-dir>
# Run from the pull request checkout, after sanitize_workspace.sh has replaced
# its agent configuration with the trusted copy from the base branch.
#
# Permissions are passed as flags, not through a settings file, because a
# settings file that fails validation is silently ignored in print mode.
# dontAsk mode denies every tool use that is not explicitly allowed here.
set -euo pipefail

out_dir="$1"
mkdir -p "$out_dir"
here="$(cd "$(dirname "$0")" && pwd)"
schema="$(cat "$here/output.schema.json")"
scope_units="$(python3 -c 'import json; print(" ".join(u["path"] for u in json.load(open(".test-agent/context/scope.json"))["units"]))')"

# --json-schema is not used: together with --agent it did not produce
# structured output (see SOLUTION.md). The schema is part of the prompt and
# the result is validated against it below.
prompt="Pull request #${PR_NUMBER}. Units in scope: ${scope_units:-none}.
The context files are in .test-agent/context/ (scope.json, diff.patch, baseline.json).
Follow your instructions: plan per unit, review, write or update tests, run them.
Your final message must be a single JSON object, with no text or code fence
around it, that is valid against this JSON Schema (every required field,
including units[].skills_used):
${schema}"

runner='python3 .claude/skills/tf-test-runner/scripts/run_tests.py'
coverage='python3 .claude/skills/tf-coverage/scripts/coverage.py'

allowed=(
  "Read(./**)" "Glob" "Grep" "Skill"
  "Edit(./modules/*/tests/*.tftest.hcl)" "Write(./modules/*/tests/*.tftest.hcl)"
  "Edit(./stacks/*/tests/*.tftest.hcl)" "Write(./stacks/*/tests/*.tftest.hcl)"
  "Bash(${runner} *)" "Bash(${coverage} *)"
)
denied=(
  "WebFetch" "WebSearch"
  "Read(//proc/**)" "Read(//etc/**)" "Read(//root/**)" "Read(//home/runner/.*/**)"
  "Read(./.git/**)" "Edit(./.claude/**)" "Edit(./.github/**)"
)

set +e
claude -p "$prompt" \
  --agent terraform-test-engineer \
  --model "${TEST_AGENT_MODEL:-claude-sonnet-5-5}" \
  --tools "Read,Glob,Grep,Edit,Write,Bash,Skill" \
  --permission-mode dontAsk \
  --allowedTools "${allowed[@]}" \
  --disallowedTools "${denied[@]}" \
  --setting-sources project \
  --max-budget-usd "${TEST_AGENT_MAX_USD:-5}" \
  --no-session-persistence \
  --output-format stream-json --verbose \
  > "$out_dir/transcript.jsonl" 2> "$out_dir/stderr.log"
status=$?
set -e

# The last event of the stream is the result; keep only the structured part.
python3 - "$out_dir" "$here" <<'EOF'
import json, subprocess, sys
out, here = sys.argv[1], sys.argv[2]
result = None
for line in open(f"{out}/transcript.jsonl", encoding="utf-8"):
    try:
        event = json.loads(line)
    except ValueError:
        continue
    if event.get("type") == "result":
        result = event
meta = {
    "subtype": (result or {}).get("subtype", "missing"),
    "num_turns": (result or {}).get("num_turns"),
    "total_cost_usd": (result or {}).get("total_cost_usd"),
    "duration_ms": (result or {}).get("duration_ms"),
}
structured = (result or {}).get("structured_output")
if structured is None and result and isinstance(result.get("result"), str):
    # Accept the object from the final message text, with or without a
    # code fence around it. Anything else in the text is ignored.
    text = result["result"]
    start, end = text.find("{"), text.rfind("}")
    try:
        structured = json.loads(text[start : end + 1]) if start != -1 else None
    except ValueError:
        structured = None
if structured is None:
    json.dump({"meta": meta, "output": None}, open(f"{out}/agent-result.json", "w"), indent=2)
    print(json.dumps(meta))
    sys.exit("agent returned no JSON result")

json.dump(structured, open(f"{out}/raw-output.json", "w"), indent=2)
check = subprocess.run(
    [sys.executable, f"{here}/validate_output.py", f"{here}/output.schema.json", f"{out}/raw-output.json"],
    capture_output=True, text=True,
)
meta["schema_errors"] = check.stdout.splitlines()
valid = check.returncode == 0
json.dump({"meta": meta, "output": structured if valid else None}, open(f"{out}/agent-result.json", "w"), indent=2)
print(json.dumps(meta))
if not valid:
    sys.exit("agent result does not match the output schema:\n" + check.stdout)
EOF

exit $status
