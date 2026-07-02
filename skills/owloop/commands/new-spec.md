---
name: owloop-spec
description: 通过交互式提问引导用户写出高质量的、约束导向（constraint-oriented）的 Owloop spec，自动编号后写入 specs/ 目录。当用户输入 /owloop-spec，或说“帮我写 spec”“帮我写个 spec”“新建一个 spec”等类似请求时使用。
---

# 交互式创建 Owloop Spec

引导用户通过问答产出一份可以直接喂给 Owloop 循环的 spec 文件。

Owloop spec 的核心是**约束导向**：只有 Requirements 不够，必须让 agent 知道「范围多大」「什么绝对不能碰」「怎么用命令验证完成」，否则无人值守的循环容易跑偏、瞎改一通。全程用中文提问；生成的 spec 文件的小节标题保持模板中的英文（`## Requirements` 等），内容忠实用中文填写用户的原话，不做没必要的翻译。

## 步骤 1：一句话意图

先问用户：

> 你想让 agent 做什么？用一句话描述。

在拿到具体、可执行的一句话描述之前不要往下走。如果回答过于宽泛（比如“优化一下代码”“改善性能”“重构一下”），追问一次，要求给出更具体的目标：改哪个功能、解决什么问题、为什么要做。

## 步骤 2：追问关键问题

基于第一步的回答，追问以下 4 个问题。可以合并成一条消息里的编号列表一次性问出去，但每一条都要拿到具体、可落地的回答——用户含糊带过（比如“都可以”“你随意”）的，追问一次，要求举例或给出实际路径/命令。如果用户在第一句话里已经顺带回答了某一条，不要机械重复，直接确认理解并跳过。

1. **范围**：“涉及哪些文件/目录？”——要精确到具体文件或目录路径，不接受“整个项目”这种回答。
2. **排除项（Exclusions）**：“有哪些绝对不能碰的东西？”——文件、模块、行为都算。如果用户想不出来，主动提示常见的排除项：数据库 schema、公共 API/响应格式、无关模块、配置文件（如 `pyproject.toml`、`uv.lock`）。这是防止自主循环跑偏最关键的一节，不能跳过或留空。
3. **验收标准（Acceptance Criteria）**：“怎么验证做完了？有没有可以跑的命令？”——目标是拿到形如「命令 → 预期输出」的可执行验收项，而不是“功能正常”这种主观判断。提问前先看一眼仓库里已有的测试/lint/构建命令（`pyproject.toml`、`package.json` scripts、`Makefile`、README 里写的命令等），把猜到的命令作为默认建议一起问出去（例如“是不是跑 `uv run pytest` 和 `uv run ruff check`？”），让用户确认或修正，而不是让用户从零想命令。
4. **代码风格（Style）**：“项目有什么编码风格约定？”——同样先看一眼涉及范围内的现有文件或相邻模块，猜一个“参照 XX 文件的写法”作为默认建议，让用户确认或补充，而不是空手让用户回答。

## 步骤 3：生成 spec 文件

拿到以上信息后：

1. **确认当前模板结构**：读取 `templates/spec-template.md`，以其中的小节顺序和标题为准（若与本文描述不一致，以该文件当前内容为准）。核心结构是：`# Feature: [name]` → `## Priority: [1-5]` → `## Requirements` → `## Acceptance Criteria` → `## Exclusions` → `## Style` → `## Verification` → 末尾一行 `Output when complete: <promise>DONE</promise>`。

2. **生成短名**：从一句话意图中提炼一个 2-4 个词的英文 kebab-case 短名（保留技术术语/缩写，如 OAuth2、API），用于文件名，例如 `add-rate-limiting`、`fix-login-redirect`。

3. **确定编号并保持与已有文件相同的补零位数**（避免 `01-x.md` 和 `002-y.md` 混用导致按字典序排序时顺序错乱——`specs/` 里的调度是纯字典序，参见 `scripts/lib/spec_queue.sh`）：

   ```bash
   mkdir -p specs
   last=$(find specs -maxdepth 1 -type f -name '[0-9]*.md' 2>/dev/null \
     | sed -E 's#.*/([0-9]+)-.*#\1#' | sort -n | tail -1)

   if [ -z "$last" ]; then
     padded="001"          # specs/ 为空或不存在：从 001 开始
   else
     width=${#last}         # 沿用已有文件的位数（比如 owloop init 生成的 01-example.md 是 2 位）
     next_num=$((10#$last + 1))
     padded=$(printf "%0${width}d" "$next_num")
   fi

   echo "specs/${padded}-<短名>.md"
   ```

4. **按模板结构写入 `specs/<编号>-<短名>.md`**：
   - `# Feature: [name]` —— 用一句话意图整理出的标题（中文）
   - `## Priority: [1-5]` —— 默认 `3`；如果用户话里透出明确的紧急/阻塞信号，调到 `1`；如果用户说不着急，调到 `5`
   - `## Requirements` —— 一句话意图 + 步骤 2「范围」问题的细节，说清楚要做什么
   - `## Acceptance Criteria` —— 把步骤 2 第 3 问的答案整理成 `- [ ] 命令 → 预期输出` 这样的清单，每一条都必须是可以直接执行的 shell 命令，不能是主观描述
   - `## Exclusions` —— 步骤 2 第 2 问的答案，逐条列出具体文件/目录/行为
   - `## Style` —— 步骤 2 第 4 问的答案
   - `## Verification` —— 完成前必须跑一遍的命令（通常和 Acceptance Criteria 里的命令重合或是其子集），放进一个 `bash` 代码块
   - 最后一行内容必须和模板一致：Output when complete: `<promise>DONE</promise>`（Owloop 循环靠这个精确字符串判断任务是否真正完成，一个字符都不能改）

## 步骤 4：审阅与确认

生成后，把完整文件内容展示给用户，明确问：

> 这份 spec 可以吗？需要调整哪里？

- 用户确认没问题 → 结束，告知生成的文件路径。可以顺带提一句怎么跑循环（`owloop run` 或 `./scripts/owloop.sh`），但不用展开讲。
- 用户提出修改 → 编辑文件后再次完整展示，重复确认，直到用户满意为止。不要在没有明确确认的情况下就当作完成。
