#!/usr/bin/env bash
# Refresh skills/minitest-cli/reference/ from minitap-ai/agent-skills (public).
#
# The three reference files are rendered by testing-service CI from its knowledge
# fragments, which is why they are not hand-edited here. testing-service publishes
# them to agent-skills; this copies the newest ones into the skill that ships in the
# wheel. The release workflow runs it so a release always carries current references.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

git clone --quiet --depth 1 https://github.com/minitap-ai/agent-skills.git "$work/agent-skills"
source_dir="$work/agent-skills/skills/minitest-cli/reference"
target_dir="$root/skills/minitest-cli/reference"

test -d "$source_dir" || { echo "agent-skills has no skills/minitest-cli/reference" >&2; exit 1; }
rm -rf "$target_dir"
cp -R "$source_dir" "$target_dir"
echo "Synced references:"; ls -1 "$target_dir"
