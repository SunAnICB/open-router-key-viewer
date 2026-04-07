#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: $0 <tag> [title]" >&2
  echo "Example: $0 v0.1.0 \"v0.1.0\"" >&2
  exit 1
fi

TAG="$1"
TITLE="${2:-$TAG}"
ASSET_PATH="$ROOT_DIR/dist/open-router-key-viewer"

cd "$ROOT_DIR"

if [[ "$(git branch --show-current)" != "main" ]]; then
  echo "Releases must be created from main." >&2
  exit 1
fi

echo "Pushing main..."
git push origin main

if git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "Tag $TAG already exists locally."
else
  echo "Creating tag $TAG..."
  git tag "$TAG"
fi

echo "Pushing tag $TAG..."
git push origin "$TAG"

echo "Building release asset..."
"$ROOT_DIR/scripts/release.sh"

if [[ ! -f "$ASSET_PATH" ]]; then
  echo "Release asset not found: $ASSET_PATH" >&2
  exit 1
fi

if gh release view "$TAG" >/dev/null 2>&1; then
  echo "Release $TAG already exists, uploading latest asset..."
  gh release upload "$TAG" "$ASSET_PATH" --clobber
else
  echo "Creating GitHub release $TAG..."
  gh release create "$TAG" "$ASSET_PATH" --title "$TITLE" --generate-notes
fi

echo "GitHub release complete: $TAG"
