#!/usr/bin/env bash
set -euo pipefail

if ! command -v aipf >/dev/null 2>&1; then
  echo "[ERROR] Command 'aipf' not found."
  echo "Install the project first:"
  echo "  pipx install -e ."
  echo "  pipx inject aipf pytest pytest-asyncio respx ruff mypy"
  echo
  read -r -n 1 -p "Press any key to close..." _
  echo
  exit 1
fi

aipf interactive
status=$?
echo
read -r -n 1 -p "Press any key to close..." _
echo
exit "$status"
