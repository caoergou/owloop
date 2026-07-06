我已经确认了根因：未提交的 `cli.py` 重构（one-command 流程改造）在改写主 banner 命令列表时，意外删掉了 `owloop init` 和 `owloop version` 两行，而现有测试 `tests/test_cli.py::test_banner_and_command_list` 明确断言这两行必须存在——目前该测试处于失败状态。这与之前给出的选项 (a)「把 `owloop version` 重新加回主 banner 帮助列表」完全吻合，且范围极小（1 个文件、几行代码），可以直接写单个 spec。

# Spec: restore-banner-command-list

**Status**: COMPLETE

## Priority: 1

## Depends On
- none

## Requirements
- [x] 在 `src/owloop/cli.py` 的 `main()` 函数中，找到无子命令时打印 `Commands:` 列表的代码块（当前只打印 `owloop spec` / `owloop run` / `owloop status` / `owloop report`）
- [x] 补回被最近一次 one-command 流程重构（未提交改动）意外删除的 `owloop init` 和 `owloop version` 两行，使用与相邻行一致的 `console.print("  [bold]owloop xxx[/]    说明")` 格式
- [x] 搜索代码库确认没有其它地方（如 README、SKILL.md）重复维护这份命令列表需要同步更新
- [x] 不要改动 one-command 流程（`goal` 参数分支）、`_ensure_init`、`spec`/`report` 命令本身的任何逻辑，只修复 banner 文本

## Acceptance Criteria
- [x] `uv run pytest tests/test_cli.py -k test_banner_and_command_list -q` → 1 passed
- [x] `uv run python -c "from click.testing import CliRunner; from owloop.cli import main; r = CliRunner().invoke(main); print('owloop init' in r.output, 'owloop version' in r.output, 'owloop spec' in r.output, 'owloop report' in r.output)"` → 输出 `True True True True`
- [x] `uv run pytest tests/test_cli.py -q` → 0 failed

## Exclusions
- Do NOT modify the `goal` argument one-command flow logic in `main()` (the block starting with `# ── One-command flow: owloop "goal" ──`)
- Do NOT modify `_ensure_init`, `spec()`, `report()`, or `version()` command implementations
- Do NOT modify `pyproject.toml`, `uv.lock`, or `.gitignore`
- Do NOT modify, delete, or comment out existing tests in `tests/test_cli.py`

## Style
- Follow the existing adjacent `console.print("  [bold]owloop xxx[/]  说明")` markup pattern already used in the same block for `spec`/`run`/`status`/`report`

## Stuck Behavior

## Verification
Run the acceptance criteria commands after each change.

## Baseline
- 直接用 `CliRunner().invoke(main)` 验证（因系统当前有大量残留 pytest 进程占满 CPU，`uv run pytest` 单独运行会超时/极慢，已改用直接调用验证）：当前 banner 输出中 `owloop init` 和 `owloop version` 均不存在（仅有 `owloop spec` / `owloop run` / `owloop status` / `owloop report`）
- `tests/test_cli.py::test_banner_and_command_list` 当前状态：失败（断言 `"owloop init" in result.output` 和 `"owloop version" in result.output` 不成立）
