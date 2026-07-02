#!/bin/bash
#
# Owloop for Claude Code
#
# Forked from the Ralph Wiggum loop; based on Geoffrey Huntley's Ralph Wiggum
# methodology: https://github.com/ghuntley/how-to-ralph-wiggum
#
# Combined with SpecKit-style specifications.
#
# Key principles:
# - Each iteration picks ONE task/spec to work on
# - Agent works until acceptance criteria are met
# - Only outputs <promise>DONE</promise> when truly complete
# - Bash loop checks for magic phrase before continuing
# - Fresh context window each iteration
# - Runs inside an isolated git worktree by default to protect the main repo
#
# Work sources (in priority order):
# 1. IMPLEMENTATION_PLAN.md (if exists) - pick highest priority task
# 2. specs/ folder - pick highest priority incomplete spec
#
# Usage:
#   ./scripts/owloop.sh              # Build mode (unlimited)
#   ./scripts/owloop.sh 20           # Build mode (max 20 iterations)
#   ./scripts/owloop.sh plan         # Planning mode (creates IMPLEMENTATION_PLAN.md)
#

set -e
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"

# Configuration
MAX_ITERATIONS=0  # 0 = unlimited
MODE="build"
CLAUDE_CMD="${CLAUDE_CMD:-claude}"
CLAUDE_MODEL="${CLAUDE_MODEL:-claude}"
PERMISSION_FLAG="--permission-mode auto"
TAIL_LINES=5
TAIL_RENDERED_LINES=0
ROLLING_OUTPUT_LINES=5
ROLLING_OUTPUT_INTERVAL=10
ROLLING_RENDERED_LINES=0

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

mkdir -p "$LOG_DIR"

# Source spec queue helpers
source "$SCRIPT_DIR/lib/spec_queue.sh"

show_help() {
    cat <<EOF
Owloop for Claude Code

基于 Geoffrey Huntley 的 Ralph Wiggum 方法论 + SpecKit 风格规范。
https://github.com/ghuntley/how-to-ralph-wiggum

用法:
  ./scripts/owloop.sh              # 构建模式，无限迭代
  ./scripts/owloop.sh 20           # 构建模式，最多 20 次迭代
  ./scripts/owloop.sh plan         # 规划模式（可选）

模式:
  build（默认）     挑选 spec/task 并实现
  plan              根据 specs 生成 IMPLEMENTATION_PLAN.md（可选）

工作来源（按顺序检查）:
  1. IMPLEMENTATION_PLAN.md - 存在则挑选最高优先级任务
  2. specs/ 目录 - 否则挑选最高优先级的未完成 spec

plan 模式是可选的，大多数项目可以直接从 specs 开始工作。

运行机制:
  1. 每次迭代通过 stdin 将 PROMPT.md 喂给 Claude
  2. Claude 挑选优先级最高的未完成 spec/task
  3. Claude 实现、测试并验证验收标准
  4. 只有验收标准全部满足，Claude 才会输出 <promise>DONE</promise>
  5. Bash 循环检查这个魔法短语
  6. 检测到则进入下一次迭代（全新上下文）
  7. 未检测到则本轮重试

Worktree:
  默认建议在独立 worktree 中运行，避免直接改动主仓库。
  首次运行会询问是否自动创建；创建后会 cd 进入该 worktree 再开始循环。
  设置 OWLOOP_SKIP_WORKTREE=1 可跳过该询问，直接在当前目录运行。

EOF
}

print_latest_output() {
    local log_file="$1"
    local label="${2:-Claude}"
    local target="/dev/tty"

    [ -f "$log_file" ] || return 0

    if [ ! -w "$target" ]; then
        target="/dev/stdout"
    fi

    if [ "$target" = "/dev/tty" ] && [ "$TAIL_RENDERED_LINES" -gt 0 ]; then
        printf "\033[%dA\033[J" "$TAIL_RENDERED_LINES" > "$target"
    fi

    {
        echo "最新 ${label} 输出（最后 ${TAIL_LINES} 行）："
        tail -n "$TAIL_LINES" "$log_file"
    } > "$target"

    if [ "$target" = "/dev/tty" ]; then
        TAIL_RENDERED_LINES=$((TAIL_LINES + 1))
    fi
}

watch_latest_output() {
    local log_file="$1"
    local label="${2:-Claude}"
    local target="/dev/tty"
    local use_tty=false
    local use_tput=false

    [ -f "$log_file" ] || return 0

    if [ ! -w "$target" ]; then
        target="/dev/stdout"
    else
        use_tty=true
        if command -v tput &>/dev/null; then
            use_tput=true
        fi
    fi

    if [ "$use_tty" = true ]; then
        if [ "$use_tput" = true ]; then
            tput cr > "$target"
            tput sc > "$target"
        else
            printf "\r\0337" > "$target"
        fi
    fi

    while true; do
        local timestamp
        timestamp=$(date '+%Y-%m-%d %H:%M:%S')

        if [ "$use_tty" = true ]; then
            if [ "$use_tput" = true ]; then
                tput rc > "$target"
                tput ed > "$target"
                tput cr > "$target"
            else
                printf "\0338\033[J\r" > "$target"
            fi
        fi

        {
            echo -e "${CYAN}[$timestamp] 最新 ${label} 输出（最后 ${ROLLING_OUTPUT_LINES} 行）：${NC}"
            if [ ! -s "$log_file" ]; then
                echo "（暂无输出）"
            else
                tail -n "$ROLLING_OUTPUT_LINES" "$log_file" 2>/dev/null || true
            fi
            echo ""
        } > "$target"

        sleep "$ROLLING_OUTPUT_INTERVAL"
    done
}

# Check whether we're already inside a linked git worktree, and if not,
# offer to create one under ../<repo>-owloop-wt/ so the main checkout stays clean.
setup_worktree() {
    if [ "${OWLOOP_SKIP_WORKTREE:-}" = "1" ]; then
        echo -e "${CYAN}○ 已跳过 worktree 隔离（OWLOOP_SKIP_WORKTREE=1），直接在当前目录运行${NC}"
        return 0
    fi

    if ! git rev-parse --is-inside-work-tree &>/dev/null; then
        echo -e "${YELLOW}⚠ 当前目录不是 git 仓库，跳过 worktree 检测${NC}"
        return 0
    fi

    if [ "$(pwd)" != "$MAIN_REPO_DIR" ]; then
        echo -e "${CYAN}✓ 已在独立 worktree 中运行: $(pwd)${NC}"
        return 0
    fi

    echo ""
    echo -e "${YELLOW}建议在独立 worktree 中运行以保护主仓库。是否自动创建？(Y/n)${NC}"

    if [ ! -t 0 ]; then
        echo -e "${CYAN}（非交互环境，跳过创建，直接在当前目录运行）${NC}"
        return 0
    fi

    local reply
    read -r -p "> " reply
    reply="${reply:-Y}"

    if [[ ! "$reply" =~ ^[Yy] ]]; then
        echo -e "${YELLOW}继续在当前目录运行（未使用 worktree）${NC}"
        return 0
    fi

    local wt_date wt_branch wt_path
    wt_date="$(date +%Y%m%d)"
    wt_branch="owloop/${wt_date}"
    wt_path="../$(basename "$PROJECT_DIR")-owloop-wt/owloop-${wt_date}"

    echo -e "${BLUE}创建 worktree: ${wt_path}（分支: ${wt_branch}）${NC}"

    if [ -d "$wt_path" ]; then
        echo -e "${CYAN}目录已存在，直接进入${NC}"
        cd "$wt_path"
    elif git worktree add "$wt_path" -b "$wt_branch"; then
        cd "$wt_path"
        echo -e "${GREEN}✓ 已创建并切换到 worktree: $(pwd)${NC}"
    elif git worktree add "$wt_path" "$wt_branch"; then
        echo -e "${CYAN}分支 $wt_branch 已存在，复用该分支${NC}"
        cd "$wt_path"
    else
        echo -e "${RED}✗ 创建 worktree 失败，继续在当前目录运行${NC}"
    fi
    echo ""
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        plan)
            MODE="plan"
            if [[ "${2:-}" =~ ^[0-9]+$ ]]; then
                MAX_ITERATIONS="$2"
                shift 2
            else
                MAX_ITERATIONS=1
                shift
            fi
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        [0-9]*)
            MODE="build"
            MAX_ITERATIONS="$1"
            shift
            ;;
        *)
            echo -e "${RED}未知参数: $1${NC}"
            show_help
            exit 1
            ;;
    esac
done

cd "$PROJECT_DIR"

# Resolve the main repo checkout (first entry of `git worktree list` is always
# the primary working tree, regardless of which worktree this runs from).
MAIN_REPO_DIR="$PROJECT_DIR"
if git rev-parse --is-inside-work-tree &>/dev/null; then
    DETECTED_MAIN=$(git worktree list --porcelain 2>/dev/null | awk '/^worktree /{print $2; exit}') || true
    [ -n "$DETECTED_MAIN" ] && MAIN_REPO_DIR="$DETECTED_MAIN"
fi

# Session log (captures ALL output)
SESSION_LOG="$LOG_DIR/owloop_${MODE}_session_$(date '+%Y%m%d_%H%M%S').log"
exec > >(tee -a "$SESSION_LOG") 2>&1

# Check if Claude CLI is available
if ! command -v "$CLAUDE_CMD" &> /dev/null; then
    echo -e "${RED}错误: 未找到 Claude CLI${NC}"
    echo ""
    echo "请先安装 Claude Code CLI 并完成登录认证。"
    echo "https://claude.ai/code"
    exit 1
fi

# Protect the main repo by default: run from an isolated worktree
setup_worktree

# Determine which prompt to use based on mode and available files
if [ "$MODE" = "plan" ]; then
    PROMPT_FILE="PROMPT_plan.md"
else
    PROMPT_FILE="PROMPT_build.md"
fi

# Generate minimal PROMPT files — constitution.md already contains the full workflow
cat > "PROMPT_build.md" << 'BUILDEOF'
# Owloop — Build Mode

You are running inside an Owloop autonomous loop (Context A).

Read `.specify/memory/constitution.md` — it contains all project principles, workflow
instructions, work sources, and completion signal requirements.

Find the highest-priority incomplete work item, implement it completely, verify all
acceptance criteria, commit and push, then output `<promise>DONE</promise>`.
BUILDEOF

cat > "PROMPT_plan.md" << 'PLANEOF'
# Owloop — Planning Mode

You are running inside an Owloop autonomous loop in planning mode.

Read `.specify/memory/constitution.md` for project principles.

Study `specs/` and compare against the current codebase (gap analysis).
Create or update `IMPLEMENTATION_PLAN.md` with a prioritized task breakdown.
Do NOT implement anything.

When the plan is complete, output `<promise>DONE</promise>`.
PLANEOF

# Check prompt file exists
if [ ! -f "$PROMPT_FILE" ]; then
    echo -e "${RED}错误: 未找到 $PROMPT_FILE${NC}"
    exit 1
fi

# Build Claude flags — always run in Auto Mode
CLAUDE_FLAGS="-p --model $CLAUDE_MODEL $PERMISSION_FLAG"

# Get current branch
CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo "main")

# Check for work sources
HAS_PLAN=false
HAS_SPECS=false
SPEC_COUNT=0
INCOMPLETE_SPEC_COUNT=0
FIRST_INCOMPLETE_SPEC=""
[ -f "IMPLEMENTATION_PLAN.md" ] && HAS_PLAN=true
if [ -d "specs" ]; then
    SPEC_COUNT=$(count_root_specs "specs")
    INCOMPLETE_SPEC_COUNT=$(count_incomplete_root_specs "specs")
    [ "$SPEC_COUNT" -gt 0 ] && HAS_SPECS=true
    if [ "$INCOMPLETE_SPEC_COUNT" -gt 0 ]; then
        FIRST_INCOMPLETE_SPEC=$(get_first_incomplete_root_spec "specs")
    fi
fi

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}                 OWLOOP (Claude Code) 启动中                 ${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${BLUE}模式:${NC}       $MODE"
echo -e "${BLUE}模型:${NC}       $CLAUDE_MODEL"
echo -e "${BLUE}提示词:${NC}     $PROMPT_FILE"
echo -e "${BLUE}分支:${NC}       $CURRENT_BRANCH"
echo -e "${YELLOW}权限模式:${NC}   auto ($PERMISSION_FLAG)"
echo -e "${BLUE}Worktree:${NC}   $([ "$(pwd)" != "$MAIN_REPO_DIR" ] && echo "$(pwd)" || echo "未使用（主仓库）")"
[ -n "$SESSION_LOG" ] && echo -e "${BLUE}日志:${NC}       $SESSION_LOG"
[ $MAX_ITERATIONS -gt 0 ] && echo -e "${BLUE}最大迭代:${NC}   $MAX_ITERATIONS 次"
echo ""
echo -e "${BLUE}工作来源:${NC}"
if [ "$HAS_PLAN" = true ]; then
    echo -e "  ${GREEN}✓${NC} IMPLEMENTATION_PLAN.md（将使用该文件）"
else
    echo -e "  ${YELLOW}○${NC} IMPLEMENTATION_PLAN.md（未找到，没关系）"
fi
if [ "$HAS_SPECS" = true ]; then
    echo -e "  ${GREEN}✓${NC} specs/ 目录（共 $SPEC_COUNT 个 spec，$INCOMPLETE_SPEC_COUNT 个未完成）"
    if [ "$HAS_PLAN" = false ] && [ "$INCOMPLETE_SPEC_COUNT" -gt 0 ]; then
        echo -e "    ${CYAN}下一个未完成:${NC} $FIRST_INCOMPLETE_SPEC"
    fi
else
    echo -e "  ${RED}✗${NC} specs/ 目录（未找到 .md 文件）"
fi
echo ""

# Exit early if all specs are complete and no plan
if [ "$MODE" = "build" ] && [ "$HAS_PLAN" = false ] && [ "$HAS_SPECS" = true ] && [ "$INCOMPLETE_SPEC_COUNT" -eq 0 ]; then
    echo -e "${GREEN}全部 $SPEC_COUNT 个 spec 均已完成，无事可做。${NC}"
    echo -e "${CYAN}如需继续，请在 specs/ 中新增一个不含 'Status: COMPLETE' 的 spec。${NC}"
    exit 0
fi

echo -e "${CYAN}循环会在每轮迭代后检查是否出现 <promise>DONE</promise>。${NC}"
echo -e "${CYAN}Agent 必须先验证验收标准，才能输出该标记。${NC}"
echo ""
echo -e "${YELLOW}按 Ctrl+C 停止循环${NC}"
echo ""

ITERATION=0
CONSECUTIVE_FAILURES=0
MAX_CONSECUTIVE_FAILURES=3

while true; do
    # Check max iterations
    if [ $MAX_ITERATIONS -gt 0 ] && [ $ITERATION -ge $MAX_ITERATIONS ]; then
        echo -e "${GREEN}已达到最大迭代次数: $MAX_ITERATIONS${NC}"
        break
    fi

    ITERATION=$((ITERATION + 1))
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

    echo ""
    echo -e "${PURPLE}════════════════════ 第 $ITERATION 轮 ════════════════════${NC}"
    echo -e "${BLUE}[$TIMESTAMP]${NC} 开始第 $ITERATION 轮迭代"
    echo ""

    # Log file for this iteration
    LOG_FILE="$LOG_DIR/owloop_${MODE}_iter_${ITERATION}_$(date '+%Y%m%d_%H%M%S').log"
    : > "$LOG_FILE"
    WATCH_PID=""

    if [ "$ROLLING_OUTPUT_INTERVAL" -gt 0 ] && [ "$ROLLING_OUTPUT_LINES" -gt 0 ] && [ -t 1 ] && [ -w /dev/tty ]; then
        watch_latest_output "$LOG_FILE" "Claude" &
        WATCH_PID=$!
    fi

    # Run Claude with prompt via stdin, capture output
    CLAUDE_OUTPUT=""
    if CLAUDE_OUTPUT=$(cat "$PROMPT_FILE" | "$CLAUDE_CMD" $CLAUDE_FLAGS 2>&1 | tee "$LOG_FILE"); then
        if [ -n "$WATCH_PID" ]; then
            kill "$WATCH_PID" 2>/dev/null || true
            wait "$WATCH_PID" 2>/dev/null || true
        fi
        echo ""
        echo -e "${GREEN}✓ Claude 执行完成${NC}"

        # Check if DONE promise was output (accept both DONE and ALL_DONE variants)
        if echo "$CLAUDE_OUTPUT" | grep -qE "<promise>(ALL_)?DONE</promise>"; then
            DETECTED_SIGNAL=$(echo "$CLAUDE_OUTPUT" | grep -oE "<promise>(ALL_)?DONE</promise>" | tail -1)
            echo -e "${GREEN}✓ 检测到完成信号: ${DETECTED_SIGNAL}${NC}"
            echo -e "${GREEN}✓ 任务成功完成！${NC}"
            CONSECUTIVE_FAILURES=0

            # For planning mode, stop after one successful plan
            if [ "$MODE" = "plan" ]; then
                echo ""
                echo -e "${GREEN}规划完成！${NC}"
                echo -e "${CYAN}运行 './scripts/owloop.sh' 开始构建。${NC}"
                echo -e "${CYAN}或者删除 IMPLEMENTATION_PLAN.md，直接从 specs 开始工作。${NC}"
                break
            fi
        else
            echo -e "${YELLOW}⚠ 未检测到完成信号${NC}"
            echo -e "${YELLOW}  Agent 没有输出 <promise>DONE</promise> 或 <promise>ALL_DONE</promise>${NC}"
            echo -e "${YELLOW}  说明验收标准尚未满足。${NC}"
            echo -e "${YELLOW}  将在下一轮重试...${NC}"
            CONSECUTIVE_FAILURES=$((CONSECUTIVE_FAILURES + 1))
            print_latest_output "$LOG_FILE" "Claude"

            if [ $CONSECUTIVE_FAILURES -ge $MAX_CONSECUTIVE_FAILURES ]; then
                echo ""
                echo -e "${RED}⚠ 已连续 $MAX_CONSECUTIVE_FAILURES 轮未完成。${NC}"
                echo -e "${RED}  Agent 可能卡住了，可以考虑：${NC}"
                echo -e "${RED}  - 查看 $LOG_DIR 中的日志${NC}"
                echo -e "${RED}  - 简化当前 spec${NC}"
                echo -e "${RED}  - 手动修复阻塞问题${NC}"
                echo ""
                CONSECUTIVE_FAILURES=0
            fi
        fi
    else
        if [ -n "$WATCH_PID" ]; then
            kill "$WATCH_PID" 2>/dev/null || true
            wait "$WATCH_PID" 2>/dev/null || true
        fi
        echo -e "${RED}✗ Claude 执行失败${NC}"
        echo -e "${YELLOW}查看日志: $LOG_FILE${NC}"
        CONSECUTIVE_FAILURES=$((CONSECUTIVE_FAILURES + 1))
        print_latest_output "$LOG_FILE" "Claude"
    fi

    # Push changes after each iteration (if any)
    git push origin "$CURRENT_BRANCH" 2>/dev/null || {
        if git log origin/$CURRENT_BRANCH..HEAD --oneline 2>/dev/null | grep -q .; then
            echo -e "${YELLOW}推送失败，创建远程分支...${NC}"
            git push -u origin "$CURRENT_BRANCH" 2>/dev/null || true
        fi
    }

    # Brief pause between iterations
    echo ""
    echo -e "${BLUE}等待 2 秒后进入下一轮...${NC}"
    sleep 2
done

echo ""
echo -e "${GREEN}═══ OWLOOP 完成 ═══${NC}"
echo -e "${BLUE}分支:${NC} $CURRENT_BRANCH"
echo -e "${BLUE}迭代:${NC} $ITERATION 次"
if [ "$(pwd)" != "$MAIN_REPO_DIR" ]; then
    echo -e "${BLUE}Worktree:${NC} $(pwd)"
    echo ""
    echo -e "${CYAN}审查:${NC} git log --oneline HEAD~${ITERATION}..HEAD"
    echo -e "${CYAN}合并:${NC} cd $MAIN_REPO_DIR && git merge $CURRENT_BRANCH"
    echo -e "${CYAN}丢弃:${NC} git worktree remove $(pwd)"
else
    echo -e "${BLUE}Worktree:${NC} 未使用（本次在主仓库运行）"
fi
echo ""
