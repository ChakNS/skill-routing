# Skill Routing

语言：中文 | [English](README.en.md)

把多个 Codex/Claude Skills 组织成一条可追踪的任务链。

你可以把它理解成一个 workflow router：用户给出一个复杂任务，它先判断任务属于内容、代码还是其他场景，再拆成几个阶段，给每个阶段匹配合适的 skill，并标出哪些阶段可以并行处理。

它不是另一个写作 skill，也不是另一个代码 skill。它负责把已有 skills 串起来。

## 一行安装

```bash
curl -fsSL https://raw.githubusercontent.com/ChakNS/skill-routing/main/scripts/install.sh | bash
```

默认安装到：

```text
~/.codex/skills
```

安装后可以验证：

```bash
python3 ~/.codex/skills/skill-routing/scripts/router_modules.py validate
```

## 先试一下

内容任务：

```bash
python3 ~/.codex/skills/skill-routing/scripts/router_modules.py plan "帮我生成一套小红书图文笔记"
```

你会看到类似这样的链路：

```text
content -> xhs_note_package
step 1: intake
step 2: title_hook + visual_direction 并行
step 3: draft + asset_generation 并行
step 4: voice_polish
step 5: handoff
```

代码任务：

```bash
python3 ~/.codex/skills/skill-routing/scripts/router_modules.py plan "修复这个 React 测试失败，并验证浏览器表现"
```

机器可读输出：

```bash
python3 ~/.codex/skills/skill-routing/scripts/router_modules.py plan-json "帮我生成一套小红书图文笔记"
```

## 适合谁

适合你，如果：

- 你已经装了不少 skills，但复杂任务经常不知道该按什么顺序调用。
- 你希望把"调研 -> 写作 -> 视觉 -> 交付"这类流程固定下来。
- 你希望 agent 在完成任务后说清楚用了哪些阶段、哪些 skill、哪些证据。
- 你在做团队内部的 skill/workflow 体系，需要可复用、可审计的路由规则。

不适合你，如果：

- 你只需要一句话改写、简单问答、单文件小修。
- 你只想让 agent 自动猜一个 skill。
- 你的任务没有稳定流程，每次都完全不同。

这里真正有用的不是"识别 skill"本身。很多 agent 已经能做单步 skill 触发。真正有用的是把多个 skills 组织成可追踪的任务链。

## 它能做什么

当前内置三个 skills：

- `skill-routing`：总路由。判断任务该交给哪个 domain router。
- `content-skill-routing`：内容、写作、创作者运营、视觉包装、手动发布交接。
- `coding-skill-routing`：代码、调试、测试、前端、后端、部署、GitHub、skill 开发。

### 内容路由适合

- 小红书/Rednote 图文笔记
- LinkedIn 帖子
- 文章、newsletter、脚本
- 标题、hook、选题
- 封面、卡片、缩略图、长截图
- 内容系统、选题库、复盘看板

### 代码路由适合

- 修 bug
- 做功能
- 改 UI
- 写测试
- 调 API
- 改数据库/后端
- 创建或维护 skill/plugin
- 准备 PR、commit、部署

## 它怎么组织任务

每个 domain router 都按这个结构工作：

```text
layer -> stage -> candidate skill -> execution metadata -> report
```

也就是：

- `layer`：大类，比如 evidence、creation、packaging、build、quality。
- `stage`：小阶段，比如 research、draft、asset_generation、test_authoring。
- `candidate skill`：这个阶段建议使用哪些 skill。
- `execution metadata`：串行、并行、依赖关系、agent 角色。
- `report`：最后如何说明过程。

多阶段任务建议用这个格式收尾：

```text
stage -> selected skill or fallback -> execution -> evidence/gate -> status
```

## 安装选项

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

如果你 fork 了这个仓库：

```bash
curl -fsSL https://raw.githubusercontent.com/your-name/skill-routing/main/scripts/install.sh | \
  ROUTING_SKILLS_REPO=your-name/skill-routing \
  bash
```

## 安装器会做什么

安装脚本会：

1. 复制选中的 router skills 到目标目录。
2. 扫描已有 skill 目录里的 `SKILL.md`。
3. 生成 `skill-routing/references/router-modules.json`。
4. 给每个 domain router 生成 `local-skill-profile.generated.json`。

默认扫描：

```text
~/.codex/skills
~/.claude/skills
~/.cc-switch/skills
~/AISkills
```

下游 skills 不是硬依赖。缺了某个推荐 skill 时，router 会把它标成 recommendation，而不是直接失败。

## 扩展自己的场景包

你可以增加新的 domain router，比如：

- `design-skill-routing`
- `marketing-skill-routing`
- `research-skill-routing`
- `ops-skill-routing`

一个场景包通常长这样：

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

核心是 `pipeline-registry.json`：

```json
{
  "layers": [],
  "stages": [],
  "skills": [],
  "pipelines": []
}
```

一个 pipeline stage 可以声明：

- `step`: 第几步
- `stage`: 阶段名
- `candidate_skills`: 候选 skill
- `execution`: `serial` 或 `parallel`
- `parallel_group`: 并行组名
- `depends_on`: 依赖阶段
- `agent_role`: 这个阶段的 agent 职责

写好后，把新 router 注册到：

```text
skill-routing/references/router-modules.json
```

## 本地验证

如果你 clone 了仓库，可以运行：

```bash
python3 scripts/smoke_test.py
python3 scripts/evaluate_routes.py
```

单独验证已安装的 router：

```bash
python3 ~/.codex/skills/skill-routing/scripts/router_modules.py validate
python3 ~/.codex/skills/content-skill-routing/scripts/router_registry.py validate
python3 ~/.codex/skills/coding-skill-routing/scripts/router_registry.py validate
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

## 边界

- 这是 routing matrix，不是完整执行引擎。
- 它会规划链路、输出结构化计划、检查路由规则。
- 真正执行仍由 agent 和下游 skills 完成。
- 内容路由只准备发布材料，不登录平台、不发帖、不点赞、不评论。

## 许可证

MIT。详见 [LICENSE](LICENSE)。
