#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="open-router-key-viewer"
ICON_SVG="$ROOT_DIR/assets/open-router-key-viewer.svg"
ICON_DIR="$ROOT_DIR/build/icons"
ICON_PNG="$ICON_DIR/open-router-key-viewer.png"
ICON_ICO="$ICON_DIR/open-router-key-viewer.ico"
BUILD_INFO_PY="$ROOT_DIR/src/open_router_key_viewer/_build_info.py"
BUILD_INFO_BACKUP="$ROOT_DIR/build/_build_info.py.bak"

cd "$ROOT_DIR"

echo "Cleaning old artifacts..."
rm -rf build dist

mkdir -p "$ROOT_DIR/build"
cp "$BUILD_INFO_PY" "$BUILD_INFO_BACKUP"
trap 'cp "$BUILD_INFO_BACKUP" "$BUILD_INFO_PY" >/dev/null 2>&1 || true' EXIT

BUILD_COMMIT="$(git rev-parse HEAD)"
if [[ -n "$(git status --short)" ]]; then
  BUILD_DIRTY="True"
else
  BUILD_DIRTY="False"
fi

cat > "$BUILD_INFO_PY" <<EOF
"""Embedded build metadata.

This file may be rewritten by release tooling before packaging.
"""

BUILD_COMMIT = "$BUILD_COMMIT"
BUILD_DIRTY = $BUILD_DIRTY
EOF

echo "Preparing icon assets..."
mkdir -p "$ICON_DIR"
if ! command -v convert >/dev/null 2>&1; then
  echo "ImageMagick 'convert' is required to generate the release icon." >&2
  exit 1
fi
convert "$ICON_SVG" "$ICON_PNG"
convert "$ICON_PNG" "$ICON_ICO"

echo "Building onefile binary..."
uv run pyinstaller open_router_key_viewer.spec --noconfirm --clean 2>&1 | sed '/QFluentWidgets Pro is now released/d'

echo "Build complete."
echo "Binary:"
echo "  $ROOT_DIR/dist/$APP_NAME"
