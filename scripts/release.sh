#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="open-router-key-viewer"

cd "$ROOT_DIR"

echo "Cleaning old artifacts..."
rm -rf build dist

echo "Building onefile binary..."
uv run pyinstaller open_router_key_viewer.spec --noconfirm --clean

echo "Build complete."
echo "Binary:"
echo "  $ROOT_DIR/dist/$APP_NAME"
