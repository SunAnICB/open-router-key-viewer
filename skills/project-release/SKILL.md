---
name: project-release
description: Use this skill when working in the OpenRouter Key Viewer repository and the user wants to publish a release. The current project flow is GitHub Actions first: confirm version state, bump if needed, create and push the tag, then report the Actions run URL and Release URL for manual verification.
---

# Project Release

Use this skill only for the `open-router-key-viewer` repository when the task is to publish a versioned release.

## Current Release Flow

This repository now uses GitHub Actions as the default release path.

Canonical flow:

1. Confirm repository state
2. Confirm whether the version has already been bumped
3. If not bumped yet, update the version first
4. Create and push tag `vX.Y.Z`
5. Let GitHub Actions build and publish the release
6. Return the Actions run URL and Release URL so the user can verify the result

Do not default to `gh release create` or manual asset upload unless the workflow is broken and the user explicitly wants a fallback.

## Scope

This skill is specific to this project:

- Python desktop app managed with `uv`
- Version source of truth:
  - `pyproject.toml`
- Tag format:
  - `vX.Y.Z`
- GitHub Actions workflow:
  - `.github/workflows/release.yml`
- Local build script remains available only for fallback or manual verification:
  - `./scripts/release.sh`

## Release Workflow

1. Confirm repository state.
   - Run `git status --short`
   - Be careful with unrelated uncommitted changes
   - If the worktree is dirty, decide whether release-related files should be committed separately, stashed, or handled another way

2. Confirm target version.
   - Read `pyproject.toml`
   - Treat `[project].version` as the source of truth for release version

3. Check whether version bump is already done.
   - If the intended release version is already present in `pyproject.toml`, do not bump again
   - If the user wants a release but version was not bumped yet, bump the version first using the project versioning rules
   - Prefer patch/minor/major judgment based on actual completed changes, not planned changes

4. Create and push the release tag.
   - Tag format must be `vX.Y.Z`
   - Tag must match `[project].version`
   - Typical commands:
     - `git tag vX.Y.Z`
     - `git push origin vX.Y.Z`

5. Check GitHub Actions status.
   - Use `gh run list --workflow release.yml --limit 5`
   - Identify the run triggered by the pushed tag
   - If needed, inspect with `gh run view <run-id>`

6. Return verification URLs.
   - Actions run URL:
     - `https://github.com/SunAnICB/open-router-key-viewer/actions/runs/<run-id>`
   - Release URL:
     - `https://github.com/SunAnICB/open-router-key-viewer/releases/tag/vX.Y.Z`
   - Explicitly tell the user to check:
     - workflow success
     - release creation
     - binary asset presence

## Response Expectations

When using this skill, the CLI response should clearly state:

- current version
- whether a bump was needed
- final tag pushed
- Actions run URL
- Release URL
- whether the workflow is still running, failed, or succeeded

Keep it operational and short. Avoid long release notes unless the user explicitly asks for them.

## Fallback

Only use manual release steps if GitHub Actions is unavailable or broken and the user wants a fallback.

Fallback path:

- local build with `./scripts/release.sh`
- manual GitHub inspection or `gh release` operations

This is fallback only, not the default workflow.

## Guardrails

- Do not create a release tag that does not match `pyproject.toml`
- Do not silently skip version confirmation
- Do not assume local build output is the canonical release asset when Actions is available
- Do not overwrite tags or release history unless the user explicitly asks for rewrite / force-push behavior
