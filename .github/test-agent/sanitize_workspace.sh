#!/usr/bin/env bash
# Replace the agent configuration in a pull request checkout with the trusted
# copy from the base branch.
#
# Usage: sanitize_workspace.sh <trusted-checkout> <pr-checkout>
#
# A pull request can change .claude/, CLAUDE.md or .mcp.json. If the agent
# loaded those from the PR, the PR author (or text injected into it) could
# widen the agent's tools or rewrite its instructions while it holds an API
# key. So the agent always runs with the configuration from the base branch;
# changes to it take effect after review and merge.
set -euo pipefail

trusted="$1"
work="$2"

find "$work" -path "$work/.git" -prune -o \
  \( -name CLAUDE.md -o -name CLAUDE.local.md -o -name .mcp.json -o -name AGENTS.md \) -print0 |
  xargs -0 -r rm -f --
find "$work" -path "$work/.git" -prune -o -type d -name .claude -print0 |
  xargs -0 -r rm -rf --

cp -R "$trusted/.claude" "$work/.claude"
echo "Agent configuration taken from the base branch ($(git -C "$trusted" rev-parse --short HEAD))."
