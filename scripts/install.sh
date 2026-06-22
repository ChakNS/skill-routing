#!/usr/bin/env bash
set -euo pipefail

REPO="${ROUTING_SKILLS_REPO:-ChakNS/skill-routing}"
REF="${ROUTING_SKILLS_REF:-main}"
TARGET="${ROUTING_SKILLS_TARGET:-$HOME/.codex/skills}"
MODULES="${ROUTING_SKILLS_MODULES:-all}"
SOURCE_DIR="${ROUTING_SKILLS_SOURCE_DIR:-}"
NO_DEFAULT_SCAN_ROOTS="${ROUTING_SKILLS_NO_DEFAULT_SCAN_ROOTS:-0}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required to install skill-routing." >&2
  exit 1
fi

TMP_DIR=""
cleanup() {
  if [ -n "$TMP_DIR" ] && [ -d "$TMP_DIR" ]; then
    rm -rf "$TMP_DIR"
  fi
}
trap cleanup EXIT

if [ -n "$SOURCE_DIR" ]; then
  WORK_DIR="$SOURCE_DIR"
else
  TMP_DIR="$(mktemp -d)"
  ARCHIVE="$TMP_DIR/source.tar.gz"
  URL="https://github.com/$REPO/archive/$REF.tar.gz"

  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$URL" -o "$ARCHIVE"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$ARCHIVE" "$URL"
  else
    echo "curl or wget is required to download skill-routing." >&2
    exit 1
  fi

  tar -xzf "$ARCHIVE" -C "$TMP_DIR"
  INSTALL_PY="$(find "$TMP_DIR" -maxdepth 3 -type f -path "*/scripts/install.py" -print -quit)"
  if [ -z "$INSTALL_PY" ]; then
    echo "Unable to locate extracted skill-routing directory." >&2
    exit 1
  fi
  WORK_DIR="$(dirname "$(dirname "$INSTALL_PY")")"
fi

INSTALL_ARGS=(
  "$WORK_DIR/scripts/install.py"
  --target "$TARGET"
  --modules "$MODULES"
)

if [ "$NO_DEFAULT_SCAN_ROOTS" = "1" ]; then
  INSTALL_ARGS+=(--no-default-scan-roots)
fi

if [ "${ROUTING_SKILLS_SCAN_ROOT:-}" != "" ]; then
  IFS=":" read -r -a SCAN_ROOTS <<< "$ROUTING_SKILLS_SCAN_ROOT"
  for scan_root in "${SCAN_ROOTS[@]}"; do
    if [ -n "$scan_root" ]; then
      INSTALL_ARGS+=(--scan-root "$scan_root")
    fi
  done
fi

python3 "${INSTALL_ARGS[@]}"

echo
echo "Validate with:"
echo "  python3 $TARGET/skill-routing/scripts/router_modules.py validate"
