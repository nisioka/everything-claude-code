#!/usr/bin/env bash
# VERSION ファイルの値を .claude-plugin/ 配下の JSON ファイルに同期する
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION_FILE="$REPO_ROOT/VERSION"
PLUGIN_JSON="$REPO_ROOT/.claude-plugin/plugin.json"
MARKETPLACE_JSON="$REPO_ROOT/.claude-plugin/marketplace.json"

if [[ ! -f "$VERSION_FILE" ]]; then
  echo "ERROR: VERSION file not found at $VERSION_FILE" >&2
  exit 1
fi

VERSION="$(tr -d '[:space:]' < "$VERSION_FILE")"

if [[ -z "$VERSION" ]]; then
  echo "ERROR: VERSION file is empty" >&2
  exit 1
fi

echo "Syncing version: $VERSION"

# plugin.json
tmp=$(mktemp)
jq --arg v "$VERSION" '.version = $v' "$PLUGIN_JSON" > "$tmp" && mv "$tmp" "$PLUGIN_JSON"
echo "  Updated $PLUGIN_JSON"

# marketplace.json
tmp=$(mktemp)
jq --arg v "$VERSION" '.metadata.version = $v | .plugins[0].version = $v' "$MARKETPLACE_JSON" > "$tmp" && mv "$tmp" "$MARKETPLACE_JSON"
echo "  Updated $MARKETPLACE_JSON"

echo "Done."
