#!/usr/bin/env python3
"""Render the pull request comment from the run's JSON files.

Usage: render_comment.py --dir <artifacts-dir> [--meta key=value ...]

Reads (each optional): agent-result.json, guard.json, verify.json,
baseline.json, coverage-before.json, coverage-after.json. Prints Markdown.

Everything the agent wrote is untrusted text. It is escaped so it cannot
mention people, inject HTML, break tables or close code blocks, and it is cut
to fixed lengths. Pass/fail facts come from verify.json, which the workflow
produced by re-running the tests itself, never from the agent's own claims.
"""
import json
import os
import sys

MARKER = "<!-- tf-test-agent -->"
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}
SEVERITY_ICON = {"high": "🔴", "medium": "🟠", "low": "🟡", "info": "🔵"}
DECISION_TEXT = {
    "added_tests": "tests added",
    "updated_tests": "tests updated",
    "no_change": "no test change",
    "skipped": "skipped",
}


def load(directory, name):
    path = os.path.join(directory, name)
    if not os.path.isfile(path):
        return None
    try:
        return json.load(open(path, encoding="utf-8"))
    except ValueError:
        return None


def text(value, limit=400):
    value = str(value or "")
    value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    value = value.replace("@", "@\u200b")  # no mentions
    value = value.replace("](", "]\u200b(")  # no links
    return value if len(value) <= limit else value[: limit - 1] + "…"


def cell(value, limit=300):
    return text(value, limit).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def code(value, limit=400):
    value = str(value or "")[:limit].replace("~~~", "~ ~ ~")
    return "~~~hcl\n" + value.replace("@", "@\u200b") + "\n~~~"


def unit_test_line(unit):
    parts = []
    for t in unit.get("tests", []):
        env = os.path.basename(t["var_file"]) if t.get("var_file") else ""
        s = t.get("summary") or {}
        label = f"{t['status']}"
        if s:
            label += f" ({s.get('passed', 0)} passed, {s.get('failed', 0)} failed, {s.get('errored', 0)} errored)"
        parts.append(f"{env}: {label}" if env else label)
    return "; ".join(parts) or "n/a"


def verification_table(report):
    rows = ["| Unit | Lint | fmt | validate | Tests |", "|---|:-:|:-:|:-:|---|"]
    for u in report.get("units", []):
        ok = lambda step: "✅" if u[step]["ok"] else "❌"  # noqa: E731
        rows.append(f"| `{u['unit']}` | {ok('lint')} | {ok('fmt')} | {ok('validate')} | {cell(unit_test_line(u))} |")
    return "\n".join(rows)


def failures(report):
    out = []
    for u in report.get("units", []):
        for e in u["lint"].get("errors", []):
            out.append(f"- `{u['unit']}` lint: {text(e, 300)}")
        for t in u.get("tests", []):
            for d in t.get("diagnostics", []):
                if d.get("severity") == "error":
                    where = f"{u['unit']}/{d.get('file')}:{d.get('line')}" if d.get("file") else u["unit"]
                    out.append(f"- `{text(where, 120)}` run `{text(d.get('run'), 80)}`: {text(d.get('summary'), 120)}: {text(d.get('detail'), 300)}")
    return out[:20]


def coverage_table(before, after):
    before = {r["unit"]: r for r in before or []}
    rows = ["| Unit | Before | After | Still uncovered |", "|---|---:|---:|---|"]
    for r in after or []:
        b = before.get(r["unit"])
        b_text = f"{b['covered']}/{b['total']} ({b['percent']}%)" if b else "n/a"
        gaps = [i["address"] for i in r["items"] if not i["covered"] and i["kind"] != "data"]
        gap_text = ", ".join(f"`{cell(g, 80)}`" for g in gaps[:8]) + (" …" if len(gaps) > 8 else "")
        rows.append(f"| `{r['unit']}` | {b_text} | {r['covered']}/{r['total']} ({r['percent']}%) | {gap_text or 'none'} |")
    return "\n".join(rows)


def main(argv):
    directory = argv[argv.index("--dir") + 1]
    meta = {}
    for i, arg in enumerate(argv):
        if arg == "--meta":
            key, _, value = argv[i + 1].partition("=")
            meta[key] = value

    agent = load(directory, "agent-result.json") or {}
    output = agent.get("output") or {}
    guard = load(directory, "guard.json")
    verify = load(directory, "verify.json")
    baseline = load(directory, "baseline.json")
    cov_before = load(directory, "coverage-before.json")
    cov_after = load(directory, "coverage-after.json")

    lines = [MARKER, "## 🧪 Terraform test agent", ""]

    # Headline: facts from the workflow, not from the agent.
    agent_status = meta.get("agent_status", "")
    push = meta.get("push", "")
    if agent_status and agent_status != "success":
        lines.append(f"**Agent did not run to completion:** {text(agent_status, 300)}")
    elif guard and not guard["ok"]:
        lines.append("❌ **The agent's changes were rejected by the guard and not applied.**")
    elif verify is not None and not verify.get("ok"):
        lines.append("❌ **The agent's tests did not pass the independent re-run, so nothing was committed.**")
    elif guard and guard.get("empty"):
        lines.append("✅ **No test changes were needed.** The existing tests were re-run below.")
    elif push.startswith("pushed:"):
        sha = push.split(":", 1)[1]
        lines.append(f"✅ **Tests added or updated, verified independently, and committed as {sha}.**")
    elif push:
        lines.append(f"⚠️ **Tests verified but not committed:** {text(push, 300)}")
    lines.append("")

    if output.get("summary"):
        lines += [text(output["summary"], 800), ""]

    units = output.get("units") or []
    if units:
        lines += ["### What the agent decided", "", "| Unit | Decision | Why | Skills used |", "|---|---|---|---|"]
        for u in units:
            skills = ", ".join(f"`{cell(s, 40)}`" for s in u.get("skills_used", []))
            lines.append(f"| `{cell(u['path'], 80)}` | {DECISION_TEXT.get(u['decision'], cell(u['decision']))} | {cell(u.get('reason'), 400)} | {skills} |")
        lines.append("")

    changes = output.get("test_changes") or []
    if changes:
        lines += ["### Test changes", ""]
        for c in changes:
            lines.append(f"**`{cell(c['file'], 120)}`** ({c['change']}): {text(c.get('rationale'), 500)}")
            for r in c.get("runs", []):
                prev = f" _(was: {text(r['previous'], 200)})_" if r.get("previous") else ""
                lines.append(f"- `{cell(r['name'], 80)}` ({r['change']}): {text(r.get('checks'), 250)}{prev}")
            lines.append("")

    if guard and guard.get("warnings"):
        lines += ["> [!WARNING]", "> Existing assertions were removed or reduced. Please check these on purpose:"]
        lines += [f"> - {text(w, 300)}" for w in guard["warnings"]]
        lines.append("")
    if guard and guard.get("violations"):
        lines += ["### Guard violations (patch rejected)", ""]
        lines += [f"- {text(v, 300)}" for v in guard["violations"]]
        lines.append("")

    if verify is not None:
        lines += ["### Independent test run", "",
                  "The workflow re-ran lint, `fmt`, `validate` and `terraform test` on the result in a sandbox without network or secrets.", "",
                  verification_table(verify), ""]
        fails = failures(verify)
        if fails:
            lines += ["<details><summary>Failures</summary>", ""] + fails + ["", "</details>", ""]
    elif baseline is not None:
        lines += ["### Test run (existing tests)", "", verification_table(baseline), ""]

    if cov_after:
        lines += ["### Coverage (resources, module calls, validations, outputs referenced by tests)", "",
                  coverage_table(cov_before, cov_after), ""]

    findings = sorted(output.get("findings") or [], key=lambda f: (SEVERITY_ORDER.get(f["severity"], 9), not f.get("in_diff")))
    if findings:
        lines += ["### Findings for reviewers", "",
                  "Things the agent noticed in the code. Nothing here was changed; whether to act is up to you.", ""]
        major = [f for f in findings if f["severity"] in ("high", "medium")]
        minor = [f for f in findings if f["severity"] not in ("high", "medium")]

        def render(f):
            where = f"{f['file']}:{f['line']}"
            scope = "in this PR" if f.get("in_diff") else "pre-existing"
            out = [f"#### {SEVERITY_ICON.get(f['severity'], '')} {text(f['title'], 120)}",
                   f"`{cell(where, 160)}` · {f['severity']} · {f['category']} · {scope}", "",
                   text(f.get("detail"), 800), "", code(f.get("evidence"))]
            if f.get("suggestion"):
                out += ["", f"_Suggestion:_ {text(f['suggestion'], 400)}"]
            return out + [""]

        for f in major:
            lines += render(f)
        if minor:
            lines += [f"<details><summary>{len(minor)} low / info findings</summary>", ""]
            for f in minor:
                lines += render(f)
            lines += ["</details>", ""]

    if output.get("limitations"):
        lines += ["<details><summary>What these tests cannot show</summary>", ""]
        lines += [f"- {text(l, 300)}" for l in output["limitations"]]
        lines += ["", "</details>", ""]

    m = agent.get("meta") or {}
    footer = []
    if meta.get("model"):
        footer.append(f"model `{cell(meta['model'], 60)}`")
    if m.get("num_turns") is not None:
        footer.append(f"{m['num_turns']} turns")
    if m.get("total_cost_usd") is not None:
        footer.append(f"${m['total_cost_usd']:.2f}")
    if meta.get("config_sha"):
        footer.append(f"agent config from base `{cell(meta['config_sha'], 12)}`")
    if meta.get("run_url"):
        footer.append(f"[run log and transcript]({meta['run_url']})")
    if footer:
        lines += ["---", "<sub>" + " · ".join(footer) + "</sub>"]

    body = "\n".join(lines)
    # GitHub limits comments to 65536 characters.
    if len(body) > 60000:
        body = body[:60000] + "\n\n…truncated; see the run log for the full report."
    sys.stdout.reconfigure(encoding="utf-8")
    print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
