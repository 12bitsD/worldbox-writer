# Proposal: Prompt 管理改造 — Markdown + JSON Catalog

> **Status**: Draft (2026-06-09)
> **作者**: Sisyphus
> **目标版本**: Sprint 28 (预估)
> **范围**: 仅 prompt 资源管理；不动 agent / engine / runtime

---

## 1. 背景

当前 prompt 管理（`src/worldbox_writer/prompting/registry.py` + `prompts/*.yaml`）有 3 个摩擦点：

1. **YAML 不适合写"长 prompt + 注释"**：system prompt 经常带负面约束、示例对话、变更理由，YAML 字符串里塞这些可读性差。
2. **agent ↔ prompt 映射写死在 agent 类里**：每个 agent 类构造时直接 `load("xxx_system")`，加新 prompt 要改 agent 代码。
3. **变更不透明**：改了 prompt 不知道哪个 agent 在用、改了什么、为什么改。

**目标**：
- Prompt 写成 markdown（含 frontmatter 元数据）
- agent ↔ prompt 的映射集中到一份 JSON catalog
- 加 prompt 不需要改任何 Python 代码
- 加载器支持热加载 + 自由覆盖

---

## 2. 目标设计

### 2.1 文件布局

```
src/worldbox_writer/prompts/
├── catalog.json                          # 唯一映射表（agent → [prompt files + variant]）
├── _schema.md                            # markdown / catalog schema 文档
├── director/
│   ├── director_init.md                  # 启动时规划
│   ├── director_intervention.md          # 用户介入
│   ├── director_title.md                 # 标题生成
│   └── _notes.md                         # 自由写变更说明
├── actor/
│   ├── actor_event.md
│   ├── actor_intent.md
│   └── _design.md
├── critic/
│   └── critic_review.md
├── gate_keeper/
│   ├── gate_keeper_validate.md
│   └── boundary_reviser.md
├── narrator/
│   ├── narrator_render.md
│   ├── narrator_fast_forward.md
│   └── style_variants.md                 # 多 variant 示例
├── node_detector/
│   └── node_detector.md
├── world_builder/
│   ├── world_builder_expand.md
│   ├── world_builder_location.md
│   └── example_factions.md
├── memory/
│   ├── memory_consistency.md
│   ├── memory_character_arc.md
│   ├── memory_summarize.md
│   └── reflection_policy.md
├── judge/
│   ├── judge_committee.md
│   └── judge_multi_chapter.md
└── _examples/
    └── minimal_template.md               # 给作者参考的最小模板
```

**关键点**：
- 目录按 `role` 分组，**不是强约束**（loader 用 glob 扫描，加深目录也行）
- `_` 前缀的文件被 loader 忽略（放注释、笔记、变更日志用）
- 同目录随便加 `.md` 即可生效，**不用改 catalog**（见 §2.4）

### 2.2 Markdown 文件 Schema

```markdown
---
id: director_init
version: 2.0
role: director
changelog:
  - v2.0 - 2026-06-15 - 收紧 premise 长度约束到 200 字以内
  - v1.0 - 2026-05-12 - 初版
tags: [planning, json_output, hard_constraint]
default_variant: standard
variants:
  standard:
    description: 标准规划（普通故事）
  short_premise:
    description: premise < 50 字时使用（更激进的扩写）
    patch: |
      - 当 premise 短于 50 字时，主动补充 1-2 个 world_rules
---

你是 WorldBox Writer 多智能体小说创作系统的导演 Agent。

## 你的任务
解析用户的故事前提，生成结构化的世界初始化数据。

## 硬约束
- **必须**只输出合法 JSON，不能有任何 markdown 代码块或额外文字
- 输出长度不超过 2048 token
- 角色名用中文真实人名，**禁止**使用"破局者""主角"等功能代号

## 输出 schema
```json
{
  "title": "世界标题",
  "premise": "...",
  "world_rules": ["..."]
}
```

## 反例
❌ 「我叫林轩，是破局者」 → 应该用真实姓名
```

**frontmatter 字段**：

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | ✅ | 全局唯一，agent 代码里 `load("id")` 用的就是它 |
| `version` | ✅ | semver；`PromptVersion` 校验 |
| `role` | ✅ | agent role 名（如 `director` / `actor` / `narrator`） |
| `changelog` | ❌ | 自由文本，每次版本变更追加 |
| `tags` | ❌ | 自由字符串数组，catalog 里可按 tag 过滤 |
| `default_variant` | ❌ | 默认选哪个 variant，不填则取主内容 |
| `variants.<name>.description` | ❌ | variant 描述 |
| `variants.<name>.patch` | ❌ | 相对主内容的 git-style patch（自动应用） |

**主内容**：去掉 frontmatter 后剩下的全部 markdown，**整个作为 system prompt 原文**。包含 ``` 代码块、emoji、中英混排都保留原样。

**为什么用 patch 而不是 override**：避免 prompt 重复；改 variant 时只看到差异。

### 2.3 Catalog JSON Schema

文件：`src/worldbox_writer/prompts/catalog.json`

```json
{
  "schema_version": 1,
  "description": "Agent → Prompt 映射表。新增 agent 或 prompt 时只改这里。",
  "agents": {
    "director": {
      "prompts": [
        { "id": "director_init", "default_variant": "standard" },
        { "id": "director_intervention", "default_variant": null },
        { "id": "director_title", "default_variant": null }
      ],
      "primary": "director_init"
    },
    "actor": {
      "prompts": [
        { "id": "actor_event", "default_variant": null },
        { "id": "actor_intent", "default_variant": null }
      ],
      "primary": "actor_intent"
    },
    "critic": {
      "prompts": [{ "id": "critic_review" }],
      "primary": "critic_review"
    },
    "narrator": {
      "prompts": [
        { "id": "narrator_render", "default_variant": "standard" },
        { "id": "narrator_fast_forward", "default_variant": null }
      ],
      "primary": "narrator_render"
    }
  },
  "tag_index": {
    "fast_forward": ["narrator_fast_forward"],
    "json_output": ["director_init", "actor_intent", "actor_event"],
    "long_form": ["narrator_render"]
  }
}
```

**字段说明**：

| 字段 | 必填 | 说明 |
|---|---|---|
| `agents.<role>.prompts` | ✅ | 这个 role 可以用的所有 prompt（**白名单**）|
| `agents.<role>.primary` | ❌ | 哪个是默认（agent 代码 `load()` 不带 id 时用这个）|
| `agents.<role>.prompts[].id` | ✅ | prompt id（必须能在 prompts 目录下找到对应 .md）|
| `agents.<role>.prompts[].default_variant` | ❌ | 这个 agent 调用时默认用哪个 variant，覆盖 frontmatter 里的 |
| `tag_index.<tag>` | ❌ | 反向索引：tag → prompt ids（agent 可按 tag 选 prompt）|

### 2.4 加载器 API

`src/worldbox_writer/prompting/registry.py` 重写为：

```python
@dataclass(frozen=True)
class PromptRef:
    id: str
    variant: str | None = None

@dataclass(frozen=True)
class PromptTemplate:
    id: str
    version: str
    role: str
    system: str               # 主内容
    variant_patches: dict[str, str] = field(default_factory=dict)
    source_path: Path | None = None

class PromptCatalog:
    """扫描 prompts/ 目录，构建 id → file 索引；加载 catalog.json。"""

    def __init__(self, prompts_dir: Path | None = None):
        self.prompts_dir = prompts_dir or self._default_dir()
        self._index: dict[str, Path] = {}         # id → .md path
        self._catalog: dict = {}                  # catalog.json 内容
        self._mtime_cache: dict[Path, int] = {}
        self.reload()                              # 启动时全量扫一次

    def reload(self) -> None:
        """重新扫描 prompts/ 目录；mtime 没变就不重解析。"""
        ...

    def list_for_role(self, role: str) -> list[PromptRef]:
        """返回 catalog 中该 role 的所有 prompt ref（白名单过滤）。"""
        ...

    def get(self, ref: PromptRef) -> PromptTemplate:
        """加载单个 prompt。带 variant 时应用 patch。"""
        ...

    def resolve_default(self, role: str, *, variant: str | None = None) -> PromptTemplate:
        """返回该 role 的 primary prompt（catalog 里有定义）。"""
        ...
```

**agent 代码变成**：

```python
# agents/director.py
class DirectorAgent:
    def __init__(self, llm: Any = None) -> None:
        self.llm = llm
        self.catalog: PromptCatalog = get_catalog()        # 进程级单例

    def _system_prompt(self, *, variant: str | None = None) -> str:
        ref = PromptRef(id="director_init", variant=variant)
        return self.catalog.get(ref).system
```

或者更简洁：
```python
# agents/director.py
class DirectorAgent:
    def _system_prompt(self) -> str:
        return get_catalog().resolve_default("director").system
```

### 2.5 自由性边界

**允许**：
- 任意位置加 `*.md` 文件，loader glob 扫描自动注册
- 任意深度的子目录（`prompts/director/special/draft.md` 也能找到）
- `id` 命名自由，只要 catalog.json 里引用了就行
- `_` 前缀的文件被忽略
- `changelog` / `tags` / `description` 全是自由文本

**约束**（最小化）：
- `id` 在 catalog.json 里**必须显式列出**（agent 不会自动"猜"可用 prompt）
- `id` 在全局唯一（重复时启动失败 + 报错哪个文件冲突）
- `version` 必填
- frontmatter 解析失败时**报错并指出文件**，不静默

**设计哲学**：底层完全自由（想加文件随便加），上层有一个 JSON 索引（让 agent 知道哪些 prompt 存在）。两层都简单。

---

## 3. 迁移路径

### 3.1 一次性迁移脚本

写 `scripts/migrate_prompts_to_md.py`（一次性，可删）：

```python
# 伪代码
1. 读每个 src/worldbox_writer/prompts/*.yaml
2. 提取 frontmatter（id, version, role, changelog）
3. system 段 → markdown body
4. user_template → 单独的 "## user_template" section
5. variants → frontmatter.variants
6. 写回 src/worldbox_writer/prompts/<role>/<id>.md
7. 收集所有 id 生成 catalog.json 草稿
8. 跑 make test-backend 验证
9. 删原 .yaml 文件
```

**手工校对**：迁移后需要 review 每份 .md（YAML 字符串转 markdown 有可能引入转义问题）。

### 3.2 兼容性窗口

- 保留 `prompts/*.yaml` 6 个 sprint
- registry 启动时同时扫描 `.yaml` 和 `.md`；catalog.json 优先
- 6 sprint 后删 `.yaml` 支持

### 3.3 灰度上线

1. **Sprint 28a**：写迁移脚本，把 director 1 个 agent 切到 .md，验证
2. **Sprint 28b**：切 critic + gate_keeper
3. **Sprint 28c**：切 actor + narrator
4. **Sprint 28d**：切 world_builder + node_detector + memory + judge
5. **Sprint 29**：删 .yaml 支持

每个 sprint 跑：
- `make test-backend` (必须 100% pass)
- 跑一次 e2e dual-loop 对比（确保 prompt 内容没变）
- 检查 Prompt Inspector 输出是否一致

### 3.4 风险 & 缓解

| 风险 | 缓解 |
|---|---|
| YAML → MD 转义出错（特别是 `|` block scalar） | 迁移后做"原文比对"测试：同一 prompt 加载后字符串必须完全一致 |
| Markdown body 含 frontmatter 边界符 `---` | 用 `+++` 或 fenced code block 包装 |
| Catalog.json 漏配 id → agent 加载失败 | 启动时校验：catalog 引用的 id 必须能在磁盘找到 |
| 热加载性能 | 已有 mtime 缓存；只解析改过的文件 |
| 用户不小心删了文件 | 启动时打印"已注册 N 个 prompt 来自 M 个文件"，缺失文件 warning |

---

## 4. 不在本次范围

- ❌ **不动 `agent_profiles.yaml`** — temperature/max_tokens/top_p 仍由 profile 决定（gotcha #13）
- ❌ **不动 `narrator_input_v2` 默认值**（历史命名残留，见 gotcha #4）
- ❌ **不动 prompt 内容** — Sprint 28 是结构改造，prompt 调优走别的 ticket
- ❌ **不引入版本回滚** — 走 git 而非 prompt registry

---

## 5. 验收标准

Sprint 29 结束时，必须满足：

- [ ] `prompts/` 目录下**没有 `.yaml` 文件**
- [ ] 22 个 agent profile 全部能加载到正确 prompt（与 Sprint 27 baseline 字节级一致）
- [ ] `make test-backend` 通过 298+ 个测试
- [ ] `make typecheck` 通过
- [ ] e2e dual-loop 对比报告 `__eq__` 通过（prompt 文本未漂移）
- [ ] `docs/architecture/DESIGN.md` §10 "LLM 接入与 Prompt Registry" 已更新
- [ ] `docs/architecture/DESIGN.md` §13 gotcha #13 改成"profile_id 不热加载，prompt .md 热加载（mtime 缓存）"
- [ ] `docs/development/DEVELOPMENT.md` 增加一节"加一个新 prompt" 教程（5 步，10 行以内）
- [ ] `catalog.json` 有 schema 校验（启动时 fail-fast）

---

## 6. 实施时间估算

| 子任务 | 工作量 |
|---|---|
| Markdown loader 改造 | 1 人天 |
| Catalog loader + JSON schema 校验 | 0.5 人天 |
| 迁移脚本 | 0.5 人天 |
| 手工 review 10 份 .md | 0.5 人天 |
| 灰度 4 个 sprint × 0.25 人天 | 1 人天 |
| 文档更新（DESIGN + DEVELOPMENT）| 0.25 人天 |
| **合计** | **3.75 人天** |

---

## 7. 开放问题（请决策）

1. **catalog.json 的存放位置**：`src/worldbox_writer/prompts/catalog.json` vs `config/prompt_catalog.json`？
2. **是否需要 Web UI 让非工程师改 prompt**：V1 暂不做，先 file-based？
3. **variant 数量上限**：合理约束（≤5 个）vs 完全自由？
4. **prompt id 命名规范**：`{role}_{action}` (如 `director_init`) vs 完全自由？

---

## 8. 参考

- 当前实现：`src/worldbox_writer/prompting/registry.py`
- 当前 prompt 文件：`src/worldbox_writer/prompts/*.yaml` (10 个)
- DESIGN.md §10：<docs/architecture/DESIGN.md>
- DESIGN.md §13 gotcha #13：profile vs prompt 热加载差异

