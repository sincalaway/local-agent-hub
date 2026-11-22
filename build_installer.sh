#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="${1:-1.0.0}"

if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Version must use MAJOR.MINOR.PATCH format (for example: 1.0.0)." >&2
  exit 2
fi
if ! command -v makensis >/dev/null 2>&1; then
  echo "NSIS 3 (makensis) is required to build the Windows installer." >&2
  exit 1
fi

mkdir -p "$ROOT/dist"
cd "$ROOT"
makensis -DAPP_VERSION="$VERSION" installer/LocalAgentHub.nsi
printf '\nInstaller created: %s\n' "$ROOT/dist/Local-Agent-Hub-Setup-${VERSION}.exe"
