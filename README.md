# Skill Routing

语言：中文 | [English](README.en.md)

这是一套给 Codex/Claude Skills 用的任务链路矩阵。它不替代具体 skill，也不假装比 agent 自带的 skill 触发更聪明。它负责另一件事：把一个复杂任务拆成可追踪的阶段链路，标出每个阶段可用的 skill、依赖关系、并行机会和最终报告方式。

如果你已经装了很多 skill，问题通常不是"缺工具"，而是另一个问题：大任务来了以后，模型不知道先用哪个、后用哪个，也不知道什么时候该停下来合并结果。这套项目解决的就是这层调度问题。

## 它解决什么痛点

很多 skill 是孤立的。写作 skill 只管写作，截图 skill 只管截图，调试 skill 只管调试。真实任务往往不是这样。

比如"做一套小红书图文笔记"，它至少包含：

- 确认主题、平台和素材
- 生成标题和开头
- 写正文
- 设计封面方向
- 生成或渲染图片资产
- 整理发布清单

这些步骤有先后关系，也有可以并行的部分。标题探索和封面方向可以并行，正文和视觉资产也可能并行。最后需要一个 handoff，把文案、标签、资产和手动发布步骤放在一起。

这套 router 做四件事：

1. 把大任务拆成小阶段。
2. 给每个阶段匹配候选 skill。
3. 标出哪些阶段应该串行，哪些阶段可以并行。
4. 输出一条能解释清楚的路由链路，而不是只给一个模糊建议。

它不是万能执行器。当前版本主要负责规划、校验和输出链路；真正执行仍由 agent 或下游 skill 完成。

## skill 特色

- 分层路由：先分 domain，再分 layer，再分 stage，最后才选 skill。
- 可插拔模块：当前内置 `content-skill-routing` 和 `coding-skill-routing`，以后可以继续加新的 domain router。
- 本地能力扫描：安装时扫描用户已有 skill，生成 `local-skill-profile.generated.json`。没有下游 skill 也不会失败，只会给出推荐。
- 并行阶段标记：registry 里可以声明 `parallel_group`，适合拆给多 agent 并行处理。
- 过程可追踪：CLI 会输出每个阶段的 layer、依赖、候选 skill、agent 角色和报告模板。
- 机器可读计划：`plan-json` 可以输出结构化链路，方便接 UI、eval 或未来的执行器。
- 路由回归测试：内置 routing eval，检查提示词是否命中预期 module、pipeline、stage 和并行组。
- 不越界自动化：内容路由只准备发布材料，不登录平台、不发帖、不点赞、不评论。

## 什么时候值得用

适合用：

- 任务明显跨多个阶段，比如调研、写作、视觉、发布交接。
- 本地有很多 skill，需要一个稳定的组合方式。
- 团队想审计 agent 为什么用了这些 skill。
- 你要沉淀某类任务的标准打法，比如内容包、UI 改造、bug 修复、skill 开发。

不适合用：

- 一句话改写、简单问答、单文件小修。
- 只想让 agent 自动猜一个 skill。
- 没有稳定流程，任务每次都完全不同。

这个项目的价值不在"识别 skill"本身，而在把多个 skill 组织成可追踪的任务链。

## 当前包含的路由

### `skill-routing`

总路由。它负责识别任务属于哪个 domain，然后分发给对应 router。

示例：

```bash
python3 ~/.codex/skills/skill-routing/scripts/router_modules.py plan "帮我生成一套小红书图文笔记"
```

会分发到 `content-skill-routing`。

### `content-skill-routing`

内容、写作、创作者运营、视觉包装和手动发布交接。

它适合这些任务：

- 小红书/Rednote 图文笔记
- LinkedIn 帖子
- 文章、newsletter、脚本
- 标题、hook、选题
- 封面、卡片、缩略图、长截图
- 内容系统、选题库、复盘看板

### `coding-skill-routing`

代码、调试、测试、前端、后端、部署、GitHub 和 skill 开发。

它适合这些任务：

- 修 bug
- 做功能
- 改 UI
- 写测试
- 调 API
- 改数据库/后端
- 创建或维护 skill/plugin
- 准备 PR、commit、部署

## 路由链路长什么样

domain router 使用这个结构组织任务：

```text
layer -> stage -> candidate skill -> execution metadata -> report line
```

以小红书图文笔记为例，路由可能是：

```text
step 1: intake
step 2: title_hook + visual_direction 并行
step 3: draft + asset_generation 并行
step 4: voice_polish
step 5: handoff
```

CLI 会把过程打印出来，包括：

- 当前 stage 属于哪个 layer
- 是否并行执行
- 依赖哪些前置阶段
- 推荐哪些 skill
- 这个阶段的 agent 角色是什么
- 最后报告应该怎么写

如果需要机器读取：

```bash
python3 ~/.codex/skills/skill-routing/scripts/router_modules.py plan-json "帮我生成一套小红书图文笔记"
```

多阶段任务的结果建议按这个格式收尾：

```text
stage -> selected skill or fallback -> execution -> evidence/gate -> status
```

## 扩展场景包模式

这套项目的扩展方式不是把所有规则塞进一个巨大的 `SKILL.md`。更稳的方式是"场景包"。

一个场景包通常包含：

```text
your-router/
├── SKILL.md
├── references/
│   ├── pipeline-registry.json
│   ├── route-tables.md
│   └── routing-fixtures.md
└── scripts/
    └── router_registry.py
```

新增场景包时，主要做三件事：

1. 写一个 domain router，比如 `design-skill-routing` 或 `marketing-skill-routing`。
2. 在 `pipeline-registry.json` 里定义 layers、stages、skills 和 pipelines。
3. 把它注册到 `skill-routing/references/router-modules.json`。

推荐的 registry 结构：

```json
{
  "layers": [],
  "stages": [],
  "skills": [],
  "pipelines": []
}
```

其中 `pipelines[].stages[]` 可以使用：

- `step`: 第几步
- `stage`: 阶段名
- `candidate_skills`: 候选 skill
- `execution`: `serial` 或 `parallel`
- `parallel_group`: 并行组名
- `depends_on`: 依赖阶段
- `agent_role`: 这个阶段的 agent 职责

这就是"大任务拆小环节，再把 skill 串成链路"的核心。

## 安装

发布到 GitHub 后，用户可以一行安装：

```bash
curl -fsSL https://raw.githubusercontent.com/ChakNS/skill-routing/main/scripts/install.sh | bash
```

如果你 fork 了这个仓库，可以用 `ROUTING_SKILLS_REPO` 指向自己的版本。

默认会安装到：

```text
~/.codex/skills
```

只安装总路由和内容路由：

```bash
curl -fsSL https://raw.githubusercontent.com/ChakNS/skill-routing/main/scripts/install.sh | \
  ROUTING_SKILLS_MODULES=main,content \
  bash
```

指定安装目录：

```bash
curl -fsSL https://raw.githubusercontent.com/ChakNS/skill-routing/main/scripts/install.sh | \
  ROUTING_SKILLS_TARGET=~/.codex/skills \
  bash
```

指定额外扫描目录：

```bash
curl -fsSL https://raw.githubusercontent.com/ChakNS/skill-routing/main/scripts/install.sh | \
  ROUTING_SKILLS_SCAN_ROOT=~/my-skills:~/team-skills \
  bash
```

本地开发时可以直接运行：

```bash
python3 scripts/install.py --target ~/.codex/skills --modules all
```

## 安装器会做什么

安装脚本会：

1. 复制选中的 router skills 到目标目录。
2. 扫描已有 skill 目录里的 `SKILL.md`。
3. 生成 `skill-routing/references/router-modules.json`。
4. 给每个 domain router 生成 `local-skill-profile.generated.json`。

默认扫描这些目录：

```text
~/.codex/skills
~/.claude/skills
~/.cc-switch/skills
~/AISkills
```

## 验证

从仓库根目录运行：

```bash
python3 scripts/smoke_test.py
```

只跑路由回归评估：

```bash
python3 scripts/evaluate_routes.py
```

评估样例放在 `evals/routing-evals.json`。它会检查：

- 是否命中预期 module
- 是否命中预期 pipeline
- 是否包含关键 stages
- 是否保留应有的 parallel groups

验证已安装的 router：

```bash
python3 ~/.codex/skills/skill-routing/scripts/router_modules.py validate
python3 ~/.codex/skills/content-skill-routing/scripts/router_registry.py validate
python3 ~/.codex/skills/coding-skill-routing/scripts/router_registry.py validate
```

试一下路由计划：

```bash
python3 ~/.codex/skills/skill-routing/scripts/router_modules.py plan "帮我生成一套小红书图文笔记"
python3 ~/.codex/skills/content-skill-routing/scripts/router_registry.py plan "生成一套小红书图文笔记，包含标题、正文、封面方向和发布清单"
python3 ~/.codex/skills/coding-skill-routing/scripts/router_registry.py plan "改进这个skill安装器并补测试"
```

## 目录结构

```text
skill-routing/
├── LICENSE
├── README.md
├── README.en.md
├── evals/
│   └── routing-evals.json
├── scripts/
│   ├── evaluate_routes.py
│   ├── install.py
│   ├── install.sh
│   └── smoke_test.py
└── skills/
    ├── skill-routing/
    ├── content-skill-routing/
    └── coding-skill-routing/
```

## 发布前检查

1. 运行 `python3 scripts/smoke_test.py`。
2. 如发布 fork，确认 README 和 `scripts/install.sh` 中的默认仓库名正确。
3. 用临时目录安装一次，检查生成的 profile。
4. 确认中文和英文 README 的安装命令一致。

## 许可证

MIT。详见 [LICENSE](LICENSE)。
