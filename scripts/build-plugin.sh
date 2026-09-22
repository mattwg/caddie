#!/usr/bin/env bash
# Builds releases/caddie-plugin-<version>.zip from the plugin sources
# at the repo root (.claude-plugin/, agents/, output-styles/, skills/) -
# exactly what a user unpacks with `claude --plugin-dir`.
#
# Usage: scripts/build-plugin.sh
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

version=$(python3 -c "import json; print(json.load(open('.claude-plugin/plugin.json'))['version'])")
out="releases/caddie-plugin-${version}.zip"

mkdir -p releases
rm -f "$out"
zip -rX "$out" .claude-plugin agents output-styles skills -x '*.DS_Store'

echo "built: $out"
