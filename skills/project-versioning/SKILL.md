---
name: project-versioning
description: 用于这个项目的版本号管理：当用户要求更新版本、判断这次该升 patch/minor/major、或在 release 前确认版本号时使用。先检查已完成改动，给出建议并征求确认，然后只更新 pyproject.toml 中的版本号。
---

# Project Versioning

用于这个项目的版本号判断与更新。

适用场景：

- 用户要求“更新版本号”
- 用户要求“判断这次该升 patch / minor / major”
- 用户准备 release 前，想先确认版本号

本项目采用“改动完成后再更新版本号”的流程：

- 先完成代码和文档改动
- 再根据实际改动判断版本号类型
- 先给出建议并征求确认
- 用户确认后再修改版本号

## Source Of Truth

本项目版本号单点来源：

- `pyproject.toml`

运行时版本读取已经跟随包元数据：

- `src/open_router_key_viewer/__init__.py`
- `src/open_router_key_viewer/services/openrouter.py`

除非项目结构未来发生变化，否则不要为了“同步版本号”去改别的文件。

## Workflow

1. 先检查当前改动，再决定版本建议。
   - `git status --short --branch`
   - `git diff --stat`
   - `git diff --name-only`
   - `git log --oneline -n 10`
   - 必要时阅读实际变更文件，判断是否是用户可见改动、破坏性改动、还是纯内部调整

2. 根据已完成的改动推荐版本类型。
   - `major`：存在明确破坏性变更、不兼容行为变化、旧用法需要调整
   - `minor`：新增了用户可见的新功能、新页面、新工作流或明显扩展能力
   - `patch`：修 bug、UI 优化、文档更新、打包调整、内部清理、兼容性小改进

3. 修改前必须先向用户确认。
   - 说明当前版本
   - 说明建议的 bump 类型
   - 说明建议的新版本号
   - 说明判断依据
   - 明确等待用户确认，不要直接改文件

4. 用户确认后再修改版本号。
   - 只修改 `pyproject.toml` 中的 `[project].version`
   - 本项目不使用 `-dev` 后缀
   - 统一使用 `MAJOR.MINOR.PATCH`

5. 修改后做最小验证。
   - 重新读取 `pyproject.toml`，确认新版本已写入
   - 必要时验证运行时版本读取，例如：
     - `uv run python -c "from open_router_key_viewer import __version__; print(__version__)"`

## Decision Heuristics

- 拿不准时，优先保守
- 多个小修复通常仍然是 `patch`
- “新增功能 + 若干修复”通常是 `minor`
- 只有在破坏性影响明确时才建议 `major`
- 如果用户指定了版本类型，也要先做一次合理性检查，再说明是否匹配

## Response Pattern

确认前建议用这种格式：

```md
当前版本：`0.2.1`
建议升级：`minor`
目标版本：`0.3.0`
原因：本次新增了用户可见功能，且没有破坏现有行为。

确认后我再修改 `pyproject.toml`。
```

确认后：

- 更新 `pyproject.toml`
- 验证新版本
- 向用户说明实际改动内容

## Guardrails

- 不要在功能未完成前提前 bump 版本
- 版本更新时不要顺手修改无关文件
- 不要为这个项目引入额外的预发布后缀或复杂流程
- 如果未来出现新的版本单点来源，先重新确认再改
