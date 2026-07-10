# Skill Routing

语言：中文 | [English](README.en.md)

Skill Routing 是一个帮你整理本地 skills 的路由 skill。

它解决的问题很具体：当你装了很多 Codex / Claude skills 以后，agent 很容易不知道该用哪个。名字像、用途重叠、同名冲突、某个任务要连续用好几个 skills，这些都会让匹配变得不稳定。最后的结果通常是：明明本地有合适的 skill，却没被用上；或者用了一个差不多但不够贴合的。

Skill Routing 做的是另一层工作：先盘点你本地已经安装的 `SKILL.md`，整理出一个属于你的 skill profile；然后在你提出任务时，帮 agent 判断该直接用哪个 skill，还是走内容创作、编程这类多阶段 route pack。你的替换、fallback、禁用和冲突处理会被记住，后面不用每次重来。

它不是一个新的写作 skill，也不是一个新的编程 skill。它更像本地 skills 的调度台。

## 你可以怎么用

最自然的用法，不是自己敲一串命令，而是直接告诉你的 agent：

```text
使用 skill-routing 把这篇技术文章改写成小红书图文，并生成封面。
```

或者第一次安装时说：

```text
帮我安装 skill-routing 这个 skill：
https://github.com/ChakNS/skill-routing

安装后请初始化它，扫描并整理我本地已经安装的 skills。
```

如果你的 agent 支持显式调用 skill，也可以这样说：

```text
$skill-routing init
```

Claude Code 里通常是：

```text
/skill-routing init
```

不要直接使用 `/init`。这个名字通常已经被宿主工具占用。

## 它适合什么场景

适合这些情况：

- 你本地已经装了很多 skills，但经常不确定该用哪个。
- 你希望 agent 第一次使用时帮你整理本地 skills，而不是靠你手工维护清单。
- 你想用内容创作或编程 route pack，但不想被迫安装里面推荐的所有 skills。
- 你希望某个 skill 缺失时，可以选择安装、换成本地已有的 skill、交给普通 agent 处理，或者把这个节点关掉。
- 你希望这些选择被记住，慢慢变成贴合自己工作流的 routing profile。

不适合这些情况：

- 你只装了一两个 skills，平时也不会混淆。
- 你只是做一次简单问答或短文本改写。
- 你希望它自动安装任何来源不明的代码。
- 你需要的是完整自动执行系统，而不是 skill 匹配和任务路由。

## 第一次使用会发生什么

初始化时，Skill Routing 会扫描常见的本地 skills 目录，例如：

- `~/.agents/skills`
- `~/.claude/skills`
- `~/.codex/skills`

它只读取 `SKILL.md` 的说明和必要元信息，不会执行被扫描 skill 里的脚本。

扫描完成后，它会生成一个本地 profile，用来记录：

- 你安装了哪些 skills。
- 哪些 skill 名称重复，需要你选择可信路径。
- 哪些任务更适合走单个 skill。
- 哪些任务更适合走多阶段 route pack。
- 你对缺失 skill 做过哪些决定，比如替换、fallback 或禁用。
- 你给过哪些成功/失败反馈。

这个 profile 保存在你的本地 skills 目录下。项目升级时不会覆盖你的个人选择。

## 它会怎么帮你选 skill

Skill Routing 会把选择说清楚，而不是只丢给你一句“我觉得用这个”。

常见结果有几种：

- `direct`：直接使用一个已安装 skill。
- `pipeline`：使用一个多阶段 route pack，比如内容创作链路或编程链路。
- `composed_pipeline`：任务跨多个领域，例如“实现一个功能，并写一条发布帖”。
- `management`：这是初始化、刷新、盘点、冲突处理这类管理任务。
- `abstain`：证据不足，不强行匹配。

比如你说：

```text
使用 skill-routing 把这篇技术文章改写成小红书图文，并生成封面。
```

它可能会把任务拆成：理解原文、改写成小红书结构、生成标题方向、规划封面、最后交付。每个阶段都会优先匹配你本地已经有的 skill。如果某个推荐 skill 没装，它不会直接卡死，而是提示你选择下一步。

## 如果推荐的 skill 没装怎么办

route pack 里的推荐 skill 不是强制要求。你不需要一次性装齐所有东西。

遇到缺失 skill 时，你可以让 agent 做这几类处理：

```text
这个 skill 我想安装，请先告诉我来源和风险，再继续。
```

```text
这个 skill 先不用装，找一个我本地已有的替代 skill。
```

```text
这个阶段可以不用专门的 skill，直接让普通 agent 处理。
```

```text
以后这个 route pack 里不要再推荐这个 skill。
```

Skill Routing 会把你的选择写回 profile。下次再遇到类似任务，它会按你的偏好来。

## 内置 route packs

当前包含三个部分：

- `skill-routing`：负责初始化、本地 skill 盘点、冲突处理、缺失 skill 决策和总路由。
- `content-skill-routing`：适合文章、社媒帖子、小红书图文、封面、内容系统和创作者工作流。
- `coding-skill-routing`：适合功能开发、bug 修复、测试、前端、后端、OpenAI API、skill/plugin 开发和 PR 准备。

你可以只安装主路由，也可以安装内容包或编程包。推荐 skill 缺失时，路由会提示你处理，而不是要求你一次性装齐所有东西。

## 如果你想手动安装

更推荐让 agent 帮你安装和初始化。如果你确实想自己装，可以这样做：

```bash
git clone https://github.com/ChakNS/skill-routing.git
cd skill-routing
python3 scripts/install.py --target ~/.agents/skills --modules all
```

Claude Code 用户通常装到：

```bash
python3 scripts/install.py --target ~/.claude/skills --modules all
```

macOS / Linux 上也可以使用安装脚本，但只建议在你已经信任当前仓库内容后使用：

```bash
curl -fsSL https://raw.githubusercontent.com/ChakNS/skill-routing/main/scripts/install.sh | bash
```

## 安全边界

Skill Routing 会尽量保守。

- 它不会自动执行被扫描 skill 里的脚本。
- 它不会自动安装未知来源的代码。
- 它不会替你授予发帖、部署、提交 PR、数据库迁移等外部写权限。
- 它不能保证宿主 agent 一定会隐式触发它；skills 很多时，建议显式说“使用 skill-routing”。
- 证据不足时，它会返回 `abstain`，避免乱选。

## 自定义 route pack

如果你有一组自己的工作流，也可以把它做成 route pack。

一个简单 route pack 通常包含：

```text
your-skill-routing/
├── SKILL.md
├── references/
│   └── pipeline-registry.json
└── scripts/
    └── router_registry.py
```

相关文档：

- [architecture.md](docs/architecture.md)
- [evaluation.md](docs/evaluation.md)
- [profile.schema.json](skills/skill-routing/references/profile.schema.json)
- [route-pack.schema.json](skills/skill-routing/references/route-pack.schema.json)

## 许可证

MIT。详见 [LICENSE](LICENSE)。
