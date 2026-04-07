#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="open-router-key-viewer"
ICON_SVG="$ROOT_DIR/assets/open-router-key-viewer.svg"
ICON_DIR="$ROOT_DIR/build/icons"
ICON_PNG="$ICON_DIR/open-router-key-viewer.png"
ICON_ICO="$ICON_DIR/open-router-key-viewer.ico"

cd "$ROOT_DIR"

echo "Cleaning old artifacts..."
rm -rf build dist

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
