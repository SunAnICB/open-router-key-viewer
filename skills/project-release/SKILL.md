---
name: project-release
description: Use this skill when working in the OpenRouter Key Viewer repository and the user wants to summarize recent changes, prepare release notes, create a git tag, publish a GitHub release, or upload the built onefile binary asset for a versioned release.
---

# Project Release

Use this skill only for the `open-router-key-viewer` repository when the task is to summarize recent changes and publish a release.

## Scope

This skill is specific to this project:

- Python desktop app managed with `uv`
- Single version source:
  - `pyproject.toml`
- Build script:
  - `./scripts/release.sh`
- Main binary output:
  - `dist/open-router-key-viewer`

## Release Workflow

1. Confirm repository state.
   - Run `git status --short`
   - Do not release from a dirty worktree unless the user explicitly wants that

2. Confirm target version.
   - Check `pyproject.toml`
   - Treat `[project].version` as the only source of truth

3. Summarize changes since the previous tag.
   - Use `git tag --list`
   - Use `git log --oneline <last-tag>..HEAD`
   - Group notes into a few user-facing bullets, not a commit dump
   - Prefer features, behavior changes, packaging changes, and documentation updates

4. Confirm GitHub CLI availability before release operations.
   - Run `gh auth status`
   - Run `gh repo view SunAnICB/open-router-key-viewer`
   - If `gh` is unavailable or auth is invalid, stop and report that clearly

5. Create and push the release tag.
   - Tag format is `vX.Y.Z`
   - Example:
     - `git tag -a v0.2.0 -m "Release v0.2.0"`
     - `git push origin v0.2.0`

6. Create the GitHub release.
   - Use `gh release create`
   - Title should match the tag, for example `v0.2.0`
   - Notes should be short and grouped under a heading such as `## Highlights`

7. Upload the binary asset if requested or if the release should include a runnable build.
   - Build with `./scripts/release.sh`
   - This script requires ImageMagick `convert`
   - Upload with:
     - `gh release upload vX.Y.Z dist/open-router-key-viewer --clobber`

8. Verify the release contents.
   - Run `gh release view vX.Y.Z --json assets,url`
   - Confirm the asset is present when expected

## Notes Style

- Keep release notes concise
- Prefer 3 to 6 bullets
- Focus on what changed for users:
  - new features
  - behavior changes
  - platform-specific support
  - packaging or distribution changes

Avoid:

- raw commit lists
- internal refactor details unless user-visible
- speculative statements

## Project-Specific Reminders

- The floating window is currently intended for `X11/xcb`
- GNOME top bar indicator support may also be release-worthy when present in the current branch
- If a release asset is uploaded, use the output from `./scripts/release.sh` instead of inventing a custom build path
- If the repository already has a release for the target tag, update assets with `--clobber` rather than creating duplicate filenames
