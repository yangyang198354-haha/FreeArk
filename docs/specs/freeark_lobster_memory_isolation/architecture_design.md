# 架构设计文档 — 方舟龙虾记忆隔离

```
file_header:
  document_id: ARCH-MEMORY-001
  project: FreeArk — freeark_lobster_memory_isolation
  version: 1.0.0-DRAFT
  status: DRAFT
  author_agent: sub_agent_system_architect (PM-orchestrated, PARTIAL_FLOW)
  created_at: 2026-05-26
  depends_on:
    - REQ-SPEC-MEMORY-001 (requirements_spec.md)
    - US-MEMORY-001 (user_stories.md)
    - ARCH-REASONING-001 (freeark_lobster_reasoning_stream/architecture_design.md，ADR-001~008 继承)
    - SKILL-MD (lobster-agent v2 SKILL.md，f04ccab，19 工具 PoC)
  context_snapshot: >
    OpenClaw 2026.5.20，Node.js 22.22.2，DeepSeek v4-flash，
    ChatConsumer v1.2（MOD-BE-01），OpenClawAdapter v1.3（MOD-BE-02），
    ChatView.vue v1.1，树莓派 Pi 5，
    OpenClaw workspace 全局共享（~/.openclaw/workspace/），
    FreeArk 后端完全无状态（ChatConsumer 不写 MySQL，session_key per-WS-connection）
  id_continuation: ADR-009 起（接续 freeark_lobster_reasoning_stream 的 ADR-008）
```

---

## 0. 增量说明

本文档是 **增量架构设计**，仅记录本期新增 ADR（ADR-009~ADR-013）。

ADR-001~008 定义继承自前序项目：
- `docs/sdlc/lobster-agent-api-channel/architecture_design.md`（ADR-001~005）
- `docs/specs/freeark_lobster_reasoning_stream/architecture_design.md`（ADR-006~008）

**强制约束（来自用户，优先级高于所有 ADR 决策）：**

| 约束编号 | 内容 |
|---------|------|
| ARCH-C-006 | 不能破坏 reasoning_stream 已部署的 v1.3 adapter / v1.2 consumer 行为（向后兼容） |
| ARCH-C-007 | 不能动 OpenClaw Gateway 协议（loopback :18789 是外部依赖，不归 FreeArk 管） |
| ARCH-C-008 | 人格锁定方案必须机器可验证（文件 hash / Git diff 等），不能仅靠人工约定 |
| ARCH-C-009 | 涉及 OpenClaw 能力的方案（agent.create / workspace 切换等），必须在 GROUP_C 启动前标注"需生产探查验证" |
| ARCH-C-010 | PM 约束：所有 ADR 的 `decision` 字段留作 `OPEN_FOR_USER_REVIEW`，由用户 CONFIRM |

---

## 1. 问题域分析

### 1.1 三个核心问题的架构映射

| 问题 | 需求 | 当前原因 | 解决方向 |
|------|------|---------|---------|
| P-1 记忆漂移 | REQ-FUNC-013, 014, 016 | OpenClaw memory/ 目录全局共享，session_key per-connection 无跨连接持久化 | 建立 per-user 记忆命名空间 + 跨连接持久化机制 |
| P-2 人格漂移 | REQ-FUNC-015 | 骨架文件（SOUL.md 等）无写保护，LLM 理论上可通过工具调用修改 | 骨架文件写保护 + 机器可验证机制 |
| P-3 历史记忆缺失 | REQ-FUNC-013, 016 | ChatConsumer session_key 为 UUID per-WS-connection，FreeArk 侧无持久化 | 用户级 session_key 复用 或 历史记忆注入 |

### 1.2 现有架构关键约束盘点

```
浏览器 WS → ChatConsumer.connect()
    → session_key = uuid4()   ← 每次新连接生成新 UUID，历史无法跨连接延续
    → augmented_message = "[__freeark_user__:username] message"   ← username 已注入
    → OpenClawAdapter.stream_chat(message, session_key)
        → OpenClaw Gateway (loopback :18789) 按 session_key 维护多轮上下文
        ← yield (kind, text) ← reasoning/content 已区分
    → WS send reasoning_token / stream_token / stream_end
```

**关键发现**：
- username 已在消息前缀中（FACT-06），OpenClaw 端**理论上**能提取用户身份
- `session_key` 是 OpenClaw 端多轮上下文的 key，决定"龙虾记得本次连接说了什么"
- FreeArk 侧 ChatConsumer 是完全无状态的（不写 DB），所有跨连接记忆能力必须从架构层新增

---

## 2. 候选方案分析

### ADR-009：per-user 记忆隔离总体方案选择

**决策问题**：如何实现 per-user 对话历史持久化（REQ-FUNC-013）+ 记忆隔离（REQ-FUNC-014）？

**候选方案**：

---

#### 方案 A：FreeArk 端消息注入（OpenClaw 端无状态）

**原理**：
- FreeArk 后端在 MySQL 中新建 `chat_memory` 表，存储每个用户的对话历史摘要（user_id, content, timestamp）
- 每次新连接时，ChatConsumer 从 DB 读取该用户的历史摘要
- 将历史摘要以扩展系统提示词或消息前缀的方式注入到发给 OpenClaw 的第一条消息中
- OpenClaw 端 workspace 保持原样（全局共享），memory/ 目录可禁止写入
- session_key 继续使用 per-connection UUID（OpenClaw 侧无状态）

**架构变更点**：
- 新增 Django 数据库表 `chat_memory`（含 migration）
- ChatConsumer.connect() 新增 DB 读取历史摘要（async）
- ChatConsumer._handle_chat() 结束时，将对话摘要写入 DB（新增写逻辑）
- 摘要生成策略（完整存储 / 摘要压缩）需要额外决策

**优势**：
1. OpenClaw 侧零改动，ARCH-C-007（不动 Gateway 协议）完全满足
2. 历史数据在 FreeArk MySQL 中，有完整的 CRUD 控制（REQ-FUNC-017 用户清空/admin 管理 易于实现）
3. 跨设备/跨浏览器天然满足（REQ-NFR-014），因为数据在 DB 而非 session
4. 安全性高：用户隔离由 Django ORM 的 user_id 外键保证，API 层权限复用现有 DRF Token 认证
5. 可回退：新增的 DB 表和注入逻辑可独立关闭，不影响现有功能

**劣势 / 风险**：
1. ChatConsumer 从"完全无状态"变为"有 DB 写入"，违反当前架构原则（ADR-001 无状态，但该原则是为了避免 MySQL 写入引入竞态，不是铁律）
2. 对话结束时需要生成摘要：完整存储会导致数据量增长；摘要压缩需要额外 LLM 调用或规则定义（成本和延迟）
3. 注入方式需要 OpenClaw 能接受扩展的系统提示词或前缀消息——需验证 OpenClaw chat.send 的 params 是否支持 systemPrompt 字段注入
4. 历史摘要体积增大时，上下文窗口占用增加（REQ-FUNC-016 AC-016-03）

**OpenClaw 能力依赖**：
- 方案 A 变体 1（消息前缀扩充）：只需 chat.send 能接收扩展的 message 文本 → **当前已验证可用**（[__freeark_user__:username] 前缀已生效）
- 方案 A 变体 2（systemPrompt 字段）：需验证 OpenClaw chat.send 是否接受独立的 systemPrompt 参数 → **[需 GROUP_C 启动前生产探查验证，VERIFY-001]**

**是否需要 Django migration**：是（新增 `chat_memory` 表）

---

#### 方案 B：每用户一个 OpenClaw agent（agent.create）

**原理**：
- 利用 lobster-agent v2 SKILL.md 中的 `agent.create` 工具，为每个 FreeArk 用户在 OpenClaw 中创建独立的 agent 实例（如 `main_<user_id>`）
- ChatConsumer 根据登录用户名选择对应的 agent 路由（修改 OpenClawAdapter 的 agent 目标参数）
- 每个 agent 有自己的 session 和 workspace 上下文，天然隔离

**架构变更点**：
- OpenClawAdapter 需要支持 agent_name 参数（动态路由到 `main_<user_id>`）
- 首次登录用户：需要调用 OpenClaw `agent.create` 或等效 API 创建 agent 实例
- 用户注销时：需要调用 OpenClaw `agent.delete` 或等效 API 清理 agent
- 骨架文件（SOUL.md 等）的同步：每个 per-user agent 都需要一份骨架配置

**优势**：
1. OpenClaw 层天然隔离：每个 agent 实例完全独立（session、memory、工具集）
2. 无需 FreeArk 侧摘要生成，历史记忆由 OpenClaw 内部管理
3. 人格锁定更自然：每个 agent 的骨架文件各自独立，且全部来自只读骨架模板

**劣势 / 风险**：
1. **[高风险] OpenClaw `agent.create` 工具在生产的可用性和行为未经验证**。SKILL.md v2（f04ccab）列出了该工具，但 PoC 仅验证了 19 工具中的 FreeArk API 调用类工具；agent.create 的 OpenClaw API 字段、副作用、持久化行为均不确定。**[需 GROUP_C 启动前生产探查验证，VERIFY-002]**
2. **扩展性问题**：每个用户对应一个 OpenClaw agent 实例，100 用户 = 100 个 agent，内存/磁盘开销不可预测（REQ-NFR-011）
3. 骨架同步复杂：骨架文件更新时需要对所有 per-user agent 执行同步，容易出现版本不一致
4. 用户生命周期管理（REQ-FUNC-017）复杂：注销时需调用 OpenClaw API 清理 agent，失败则产生孤儿 agent
5. 修改 OpenClawAdapter 的 agent 路由逻辑，需要测试与 ARCH-C-006（向后兼容 reasoning_stream）的兼容性
6. OpenClaw 并无 "workspace 切换" 的已知 RPC 接口（loopback :18789 ARCH-C-007 约束）

**OpenClaw 能力依赖**：
- `agent.create` 工具可用且支持持久化 agent → **[需生产探查验证，VERIFY-002]**
- 动态路由 agent_name 的 chat.send 参数格式 → **[需生产探查验证，VERIFY-003]**

**是否需要 Django migration**：可能（需要 DB 跟踪 per-user agent 名称映射）

---

#### 方案 C：OpenClaw workspace per-user 目录 + symlink 只读骨架

**原理**：
- 在树莓派上重构 OpenClaw workspace：
  - `~/.openclaw/workspace/shared/`：存放只读骨架（SOUL.md、AGENTS.md、TOOLS.md），通过文件系统权限或 symlink 保护
  - `~/.openclaw/workspace/users/<user_id>/`：per-user 目录，含 USER.md（个性化配置）和 memory/ 子目录
  - 通过 symlink 将 shared/ 的骨架链接到每个 user 目录中
- FreeArk 端需要在发消息前切换 OpenClaw 的 workspace 上下文到对应用户目录

**架构变更点**：
- 树莓派 OpenClaw workspace 目录结构需要重建
- 需要 OpenClaw 支持"切换 workspace"的 RPC 或配置机制
- 首次登录用户：需要在树莓派上创建 `~/.openclaw/workspace/users/<user_id>/` 目录并设置 symlink
- FreeArk 端 ChatConsumer / Adapter 需要能触发 workspace 切换

**优势**：
1. 骨架文件（SOUL.md 等）集中在 shared/，只需维护一份，人格一致性最强
2. symlink 天然实现"人格骨架只读"的物理隔离

**劣势 / 风险**：
1. **[最高风险] OpenClaw 是否支持运行时动态切换 workspace？** OpenClaw Gateway RPC v4 的已知接口是 chat.send 等（不含 workspace.switch），且 ARCH-C-007 约束不能修改 Gateway 协议。从外部触发 workspace 切换的机制未知。**[需 GROUP_C 启动前生产探查验证，VERIFY-004]**
2. 如果 OpenClaw 不支持 runtime workspace 切换，此方案在技术上不可行（非架构取舍，是硬约束）
3. 目录结构重建影响当前生产的 OpenClaw 运行状态（高风险操作）
4. symlink 在 OpenClaw 文件操作工具中的行为需要验证（LLM 工具是否会跟 symlink 写入？）

**OpenClaw 能力依赖**：
- 支持动态 workspace 切换 → **[需生产探查验证，VERIFY-004]**
- LLM 工具写文件时是否遵循 symlink 只读？ → **[需生产探查验证，VERIFY-005]**

**是否需要 Django migration**：否（记忆在文件系统，但用户目录创建需要文件系统操作）

---

#### 方案 D：Hybrid — FreeArk DB 存历史 + OpenClaw 端 stateless（方案 A 精简变体）

**原理**：
- 与方案 A 相似，但明确 OpenClaw 端完全无状态（不依赖 OpenClaw memory/ 目录）
- FreeArk MySQL 存储对话摘要（user_id, turn_summary, created_at）
- 每次对话前，ChatConsumer 构造"历史上下文消息"，以独立的消息（role: user/assistant）列表方式注入
- 明确不使用 OpenClaw workspace/memory/ 目录（设为禁写或忽略其内容）
- session_key 仍为 per-connection UUID

**与方案 A 的区别**：
- 方案 A 可以借助 OpenClaw 的多轮 session 能力（在单次连接内由 OpenClaw 维护上下文）
- 方案 D 明确只用消息列表注入，不依赖 OpenClaw 侧任何有状态机制，FreeArk 完全控制历史内容

**优势**：
1. 最简单、最可控、最可回退
2. OpenClaw 端完全无状态，对 OpenClaw 任何升级或变更的抵抗力最强
3. 历史数据完全在 FreeArk 控制范围内（MySQL），用户管理（清空/导出/审计）最易实现
4. 与现有 ARCH-C-007（不动 Gateway 协议）完全兼容

**劣势 / 风险**：
1. ChatConsumer 从"无状态"变为"有 DB 读写"（同方案 A 劣势 1）
2. 历史记忆以消息列表注入时，上下文 token 占用随历史增长（同方案 A 劣势 4）
3. OpenClaw 单次 session 内的多轮 context 与注入的历史消息可能产生语义重叠（但无害）
4. 摘要压缩策略仍需要决策（同方案 A 劣势 2）

**OpenClaw 能力依赖**：
- chat.send 能接收扩展的 message 文本（多行/长文本）→ **当前已验证，[__freeark_user__:...] 前缀已生效**
- 无其他 OpenClaw 侧依赖

**是否需要 Django migration**：是（新增 `chat_memory` 表）

---

### 方案对比矩阵

| 维度 | 方案 A（DB + 注入） | 方案 B（per-user agent） | 方案 C（per-user workspace） | 方案 D（Hybrid DB Stateless） |
|------|---------|---------|---------|---------|
| OpenClaw 端改动 | 零改动 | 需 agent.create | 需 workspace 切换 | 零改动 |
| FreeArk DB 改动 | 新增 1 表 | 可能需记录映射 | 不需要 | 新增 1 表 |
| OpenClaw 能力依赖验证 | VERIFY-001（可选） | VERIFY-002/003（必须） | VERIFY-004/005（必须） | 无（已验证） |
| 可扩展性（100 用户） | 可（DB 无限扩展） | 风险（100 agent 实例开销未知） | 可（目录开销小） | 可（DB 无限扩展） |
| 记忆管理（REQ-FUNC-017） | 易（DB CRUD） | 难（需 OpenClaw API） | 中（文件系统操作） | 易（DB CRUD） |
| 向后兼容（ARCH-C-006） | 高（不改 adapter/consumer 核心） | 中（需改 adapter 路由） | 不确定（workspace 切换影响现有流程） | 高（不改 adapter/consumer 核心） |
| 人格骨架锁定 | 需额外机制（骨架文件分离保护） | 中（per-agent 骨架独立但同步复杂） | 高（symlink 物理隔离） | 需额外机制（骨架文件分离保护） |
| 实现复杂度 | 中 | 高 | 高（含未知风险） | 中（最低） |
| 可回退性 | 高（DB 表可禁用，注入逻辑可关闭） | 低（agent 实例清理复杂） | 低（workspace 重构难以回退） | 高 |
| 技术风险 | 低 | 高（生产探查必须） | 极高（基础能力未验证） | 最低 |

---

**ADR-009 决策**：

```
decision: CONFIRMED — 方案 D（Hybrid DB Stateless）
confirmed_at: 2026-05-26
confirmed_by: 用户（AskUserQuestion 选项）

recommendation: 方案 D（Hybrid DB Stateless）作为首推。
  理由：
  1. 技术风险最低：不依赖任何未验证的 OpenClaw 能力，方案 A/B/C 都有不同程度的
     OpenClaw 能力依赖（VERIFY-001~005），方案 D 仅使用已验证的 chat.send 消息注入。
  2. 向后兼容最强：adapter v1.3 / consumer v1.2 核心逻辑不变，满足 ARCH-C-006。
  3. 管理能力最完整：REQ-FUNC-017（清空/admin/注销清理）全部通过 Django ORM 实现，
     与现有 FreeArk 权限体系天然集成。
  4. 可回退：DB 表和注入逻辑可独立关闭，不影响现有功能。

  方案 A 与方案 D 的区别仅在于是否利用 OpenClaw 侧 session 的有状态特性，
  对于本需求（跨连接持久化），两者都需要 DB 存储，方案 D 更明确简洁。

  如果用户希望深入利用 OpenClaw 原生能力（方案 B/C），
  必须先完成 VERIFY-002~005 生产探查，再评估。

alternatives_considered:
  - 方案 A：同方案 D，但依赖 OpenClaw systemPrompt 参数，需 VERIFY-001
  - 方案 B：技术风险高，需 VERIFY-002/003，推荐探查后再决定
  - 方案 C：技术风险极高，需 VERIFY-004/005，不推荐作为首选

user_review_required: true
user_review_items:
  - 是否接受方案 D（DB + 消息注入，不依赖 OpenClaw 侧任何有状态能力）？
  - 是否希望在 GROUP_C 前先执行 VERIFY-002/003 探查 OpenClaw agent.create 能力？
  - 是否愿意接受 ChatConsumer 新增 DB 写入（对话结束时写摘要到 MySQL）？
```

---

### ADR-010：对话历史摘要策略

**决策问题**：在 ADR-009 决策为方案 A 或 D（DB 存储）的前提下，历史记忆如何存储和注入？

**候选方案**：

---

#### 方案 10-A：完整对话日志存储 + 截断注入

- MySQL 中存储每条消息的原始文本（user_message, assistant_message, timestamp）
- 注入时取最近 N 条消息（如最近 20 条），超出截断

优势：实现最简单；历史完整可审计
劣势：长期使用后 token 消耗增加；截断可能丢失早期重要信息

---

#### 方案 10-B：滚动摘要（Summary Rolling）

- 在每次对话结束时，用规则（或 LLM）生成一段摘要，追加到用户的记忆条目中
- 注入时以摘要为主（固定长度），不注入原始消息列表

优势：上下文 token 消耗稳定；历史越多不会越占上下文
劣势：需要定义摘要规则（或额外 LLM 调用）；早期摘要方法存在信息损耗

---

#### 方案 10-C：关键事件提取（Key Facts）

- 每次对话结束后，提取"用户透露的关键事实"（如偏好、姓名、特定话题），以键值对存储
- 注入时以键值对列表拼接为上下文

优势：注入内容高度精炼，token 消耗最低
劣势：事实提取规则复杂；可能遗漏细节；初期实现成本较高

---

**ADR-010 决策**：

```
decision: CONFIRMED — 方案 10-A（完整日志 + 最近 N=20 轮截断注入）
confirmed_at: 2026-05-26
confirmed_by: 用户（AskUserQuestion 选项）
parameters:
  - N = 20 轮（user + assistant 各算一轮，共 40 条消息）
  - reasoning 内容不存不注入（节省 token）
  - 预计注入成本 ~2-4k tokens/请求

recommendation: 方案 10-A（完整日志 + 截断注入）作为 GROUP_C 初期实现。
  理由：
  1. 实现最简单，GROUP_C 工作量最小。
  2. 截断策略（最近 N 条）对大多数日常对话场景已足够。
  3. 10-B/10-C 可在后续迭代中叠加。

  初期参数建议（可由用户调整）：
  - DB 存储：每条消息的 user_message 和 assistant_content（不存 reasoning）
  - 注入窗口：最近 20 轮（40 条消息，约 5000 token，根据 Pi 5 性能调整）
  - 注入格式：消息前缀扩展（在 [__freeark_user__:username] 后附加历史摘要块）

user_review_required: true
user_review_items:
  - 是否接受方案 10-A（完整日志 + 截断）作为初期实现？
  - 注入窗口参数（最近 N 轮）是否合适？默认建议 20 轮。
  - 历史记忆中是否需要包含 reasoning 内容？建议不存（节省 token），仅存 content。
```

---

### ADR-011：人格骨架锁定机制

**决策问题**：如何实现机器可验证的人格骨架写保护（REQ-FUNC-015、REQ-NFR-012）？

**候选方案**：

---

#### 方案 11-A：文件系统权限锁定（chmod 444）

- 将骨架文件（SOUL.md、AGENTS.md、TOOLS.md）设为只读（`chmod 444`）
- OpenClaw LLM 工具尝试写入时，OS 拒绝（Permission denied）
- 哈希基准：在部署时计算文件 SHA-256，存入 `.openclaw/workspace/.skeleton_hashes.txt`
- 巡检脚本：每次部署后或定期运行，比对当前哈希与基准

优势：最底层防护，不依赖 OpenClaw 配置；机器可验证（哈希比对）
劣势：`yangyang` 账号（非 root）的文件，`chmod 444` 对同用户进程防护有限——同 UID 进程仍可 `chmod u+w` 后写入；需要额外的 ACL/chattr 保护才能防止同 UID 绕过

---

#### 方案 11-B：chattr +i 不可变属性

- 使用 `sudo chattr +i SOUL.md AGENTS.md TOOLS.md` 设置不可变 bit
- 即使 root 也无法在不先移除 +i 的情况下修改文件
- 哈希巡检同方案 11-A

优势：最强的 OS 级写保护，防止任何进程（含 LLM 工具进程）修改
劣势：需要 `sudo chattr`（需 yangyang 有 sudo 权限，生产已确认有 NOPASSWD）；授权修改时需先 `sudo chattr -i` 再改再 `sudo chattr +i`（流程可接受）

---

#### 方案 11-C：Git 哈希追踪（仅检测，无物理锁）

- 骨架文件纳入 Git 追踪（已在仓库中），任何修改会反映在 `git status`
- 巡检脚本运行 `git diff --name-only HEAD` 检测骨架文件是否有未提交修改
- 优化：结合 git pre-commit hook 防止意外提交

优势：最轻量；利用现有 Git 基础设施；哈希追踪由 Git 内置
劣势：只能检测修改，不能物理阻止修改；如果文件不在 Git 追踪范围（如 per-user workspace 文件）则无效；Pi 上的 OpenClaw workspace 不一定与 FreeArk 仓库在同一工作树

---

#### 方案 11-D：SKILL.md 约束（LLM 行为层）

- 在 SKILL.md 中明确声明"禁止修改骨架文件"的工具使用约定
- 依赖 LLM 遵守约定，不做物理保护

优势：零操作成本
劣势：完全不满足 REQ-NFR-012（机器不可验证）；用户需求明确要求"不能仅靠约定"；REJECT

---

**ADR-011 决策**：

```
decision: CONFIRMED — 方案 11-B（chattr +i）+ 方案 11-C（Git 哈希追踪）组合
confirmed_at: 2026-05-26
confirmed_by: 用户（AskUserQuestion 选项："chattr+i 锁 + USER.md 废弃个性化（推荐）"）
locked_files:
  - ~/.openclaw/workspace/AGENTS.md
  - ~/.openclaw/workspace/SOUL.md
  - ~/.openclaw/workspace/TOOLS.md
  - ~/.openclaw/workspace/USER.md  （详见 ADR-012：废弃个性化功能后只锁通用默认值）

recommendation: 方案 11-B（chattr +i）+ 方案 11-C（Git 哈希追踪）组合使用。
  理由：
  1. chattr +i 提供 OS 级最强防护（ARCH-C-008 机器可验证的写保护）
  2. Git 哈希追踪提供可审计的变更检测（REQ-NFR-012 完整性审计）
  3. 两者组合：物理保护（chattr）+ 检测审计（git diff），互补
  4. chattr +i 在 Pi 5（Debian 13）上可用，yangyang 有 sudo NOPASSWD

  实施流程：
  1. 部署时：sudo chattr +i SOUL.md AGENTS.md TOOLS.md USER.md
  2. 记录哈希基准：sha256sum SOUL.md AGENTS.md TOOLS.md USER.md > .skeleton_hashes
  3. 巡检命令：sha256sum -c .skeleton_hashes（输出 OK/FAILED，机器可判断）
  4. 授权修改：sudo chattr -i <file> → 修改 → 重新计算哈希 → sudo chattr +i <file>

  注意：USER.md 的处理需要额外决策（见 ADR-012）。
  方案 11-A 单独使用不足（同 UID 绕过风险），方案 11-D 直接拒绝。

user_review_required: true
user_review_items:
  - 是否接受 chattr +i 对骨架文件的 OS 级锁定？
  - USER.md 是否纳入骨架锁定范围？（若 per-user 个性化由 DB 实现，则 USER.md 
    可以不再是骨架文件，而是废弃/锁定为默认值）
  - .skeleton_hashes 文件存放位置（生产 Pi 上的路径）由用户指定还是由 GROUP_C 确定？
```

---

### ADR-012：USER.md 与个性化配置的处理方式

**决策问题**：USER.md 当前包含全局用户称呼配置（"老板"等），需要 per-user 个性化（REQ-FUNC-014 AC-014-03）。如何处理？

**候选方案**：

---

#### 方案 12-A：废弃 USER.md，个性化通过记忆注入实现

- 将 USER.md 设为只读骨架（锁定默认值），不再通过文件配置个性化
- 用户个性化偏好（称呼、语言习惯等）存储在 FreeArk DB（chat_memory 或独立的 user_preference 表）
- 通过历史记忆注入机制传递给 LLM
- USER.md 骨架内容改为通用性描述，不含特定用户名

优势：与 ADR-009 方案 D 完全一致，个性化信息统一由 DB 管理；USER.md 可被 chattr +i 锁定
劣势：USER.md 失去原有作用（需要修改骨架内容）

---

#### 方案 12-B：per-user USER.md 文件（配合方案 C workspace 结构）

- 每个用户有自己的 USER.md（在 per-user workspace 目录中）
- 依赖方案 C 的 workspace 切换能力

劣势：依赖 VERIFY-004/005，高风险

---

**ADR-012 决策**：

```
decision: CONFIRMED — 方案 12-A（废弃 USER.md 个性化功能，DB 统一管理）
confirmed_at: 2026-05-26
confirmed_by: 用户（AskUserQuestion 选项捆绑于 ADR-011）
post_decision_behavior:
  - USER.md 保留为通用默认值，chattr +i 锁定
  - 用户级"叫老板"等个性化通过 chat_message 注入或新增 user_preference 表
  - GROUP_C 实现时需替换 USER.md 中含特定称呼的字段为通用占位

recommendation: 方案 12-A（废弃 USER.md 个性化功能，统一由 DB 注入管理）。
  理由：
  1. 与 ADR-009 方案 D 一致，避免引入额外依赖
  2. USER.md 可被 chattr +i 锁定为通用默认值（不含特定用户信息）
  3. 个性化通过 DB 的 user_preference 表管理，比文件方式更可靠

user_review_required: true
user_review_items:
  - 是否接受废弃 USER.md 的个性化功能，改由 DB 管理用户偏好？
  - USER.md 的"默认"内容保留什么？（如默认称呼"用户"，还是去掉称呼字段）
```

---

### ADR-013：FreeArk DB 表结构（记忆持久化表设计）

**决策问题**：在 ADR-009 选择方案 D 的前提下，Django 新增哪些表/字段？

**候选方案**：

---

#### 方案 13-A：单表 chat_memory（轻量设计）

```sql
CREATE TABLE api_chat_memory (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id         INT NOT NULL,          -- FK → auth_user.id
    role            VARCHAR(20) NOT NULL,  -- 'user' | 'assistant'
    content         TEXT NOT NULL,         -- 消息正文（不含 reasoning）
    created_at      DATETIME(6) NOT NULL,
    INDEX idx_user_created (user_id, created_at DESC)
);
```

注入时取 `WHERE user_id=? ORDER BY created_at DESC LIMIT N*2`（N 轮 = 2N 条），按时间升序排列后拼接为上下文消息块。

优势：最简洁；单表无 JOIN；生命周期管理（清空/删除）为简单 DELETE
劣势：无会话分组（无法区分"第1次连接的对话"和"第2次连接的对话"）

---

#### 方案 13-B：两表（chat_session + chat_memory）

```sql
CREATE TABLE api_chat_session (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id         INT NOT NULL,          -- FK → auth_user.id
    session_key     VARCHAR(36) NOT NULL,  -- OpenClaw session_key（UUID）
    started_at      DATETIME(6) NOT NULL,
    ended_at        DATETIME(6),
    INDEX idx_user_started (user_id, started_at DESC)
);

CREATE TABLE api_chat_message (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id      BIGINT NOT NULL,       -- FK → api_chat_session.id
    role            VARCHAR(20) NOT NULL,
    content         TEXT NOT NULL,
    created_at      DATETIME(6) NOT NULL,
    INDEX idx_session (session_id, created_at ASC)
);
```

优势：可按会话查看历史；session_key 可追溯（调试用）；审计能力更强
劣势：两表 JOIN；实现略复杂；admin 管理需要两步操作

---

**ADR-013 决策**：

```
decision: CONFIRMED — 方案 13-B（chat_session + chat_message 两表）
confirmed_at: 2026-05-26
confirmed_by: 用户（AskUserQuestion 选项）
chat_message.content_encryption: NO（用户未要求加密；后续如有合规要求再加列级加密）

recommendation: 方案 13-B（chat_session + chat_message 两表）。
  理由：
  1. 会话粒度追踪对 admin 审计（REQ-FUNC-017c）和调试有价值
  2. 注入时仍可按 user_id 跨 session 查询最近 N 条消息（不必然 JOIN）
  3. 生命周期管理：清空用户记忆 = DELETE FROM chat_session WHERE user_id=? 
     （CASCADE 删除 chat_message），操作清晰

  表名前缀建议：api_chat_session / api_chat_message（Django 约定）
  Migration 文件由 GROUP_C 开发者生成（manage.py makemigrations api）

user_review_required: true
user_review_items:
  - 是否接受两表设计（13-B）？或者更偏向简单单表（13-A）？
  - 是否需要对 chat_message.content 字段做加密存储？（用户隐私考量）
  - chat_session.ended_at 在 ChatConsumer disconnect 时写入，是否接受这个写入时机？
```

---

## 3. 生产探查验证清单

以下验证项必须在 GROUP_C 启动前完成（若选择对应方案）：

| 验证编号 | 内容 | 影响方案 | 验证方法（文档规划，GROUP_C 执行） |
|---------|------|---------|--------------------------------|
| VERIFY-001 | OpenClaw chat.send 是否支持独立的 systemPrompt 参数（区别于 message 文本拼接） | 方案 A 变体 2 | 通过临时 logger 捕获 OpenClaw 接受/拒绝的字段；或查看 chat.send RPC schema |
| VERIFY-002 | OpenClaw agent.create 工具在生产是否可用、参数格式、持久化行为 | 方案 B | 通过 lobster-agent v2 SKILL.md 的工具调用接口实测 |
| VERIFY-003 | chat.send 是否支持动态指定 agent_name 参数（路由到 main_<user_id>） | 方案 B | 同 VERIFY-002，实测参数 |
| VERIFY-004 | OpenClaw 是否支持运行时切换 workspace 路径（RPC 或配置文件） | 方案 C | 查看 OpenClaw RPC v4 文档；实测 :18789 端点 |
| VERIFY-005 | OpenClaw LLM 工具写文件时是否遵循 symlink（是否跟随链接写入原文件） | 方案 C | 在测试环境创建 symlink 后触发 LLM 写操作，观察结果 |

**如果 ADR-009 最终确定为方案 D，则只有 VERIFY-001 可选（不强制），VERIFY-002~005 均可跳过。**

---

## 4. 架构约束汇总（本期新增）

| 约束编号 | 内容 | 来源 |
|---------|------|------|
| ARCH-C-006 | 不破坏 reasoning_stream v1.3 adapter / v1.2 consumer 行为 | 用户强制约束 |
| ARCH-C-007 | 不动 OpenClaw Gateway 协议（:18789 loopback） | 用户强制约束 |
| ARCH-C-008 | 人格锁定必须机器可验证 | 用户强制约束 |
| ARCH-C-009 | 涉及 OpenClaw 能力的方案需生产探查验证后才能进入 GROUP_C | 用户强制约束 |
| ARCH-C-010 | ADR decision 留 OPEN_FOR_USER_REVIEW，由用户 CONFIRM | PM 约束 |
| ARCH-C-011 | 若选方案 D：ChatConsumer disconnect 时写摘要，需确保 async DB 写入不阻塞 WS 关闭 | 本期新增 |
| ARCH-C-012 | DB 写入使用 Django ORM（sync_to_async 包装），不使用原生 SQL | 本期新增 |

---

## 5. 模块影响评估（与 reasoning_stream 已有模块的关系）

| 模块 | 版本 | 本期改动性质 | 兼容性 |
|------|------|------------|-------|
| MOD-BE-02 (openclaw_adapter.py v1.3) | v1.3 | 不改动（方案 D 不需要修改 adapter） | 完全兼容 |
| MOD-BE-01 (consumers.py v1.2) | v1.2 | 新增 connect() 时读历史、disconnect() 时写记录 | 需验证 async 写不影响现有流程 |
| MOD-FE-01 (ChatView.vue v1.1) | v1.1 | 可选：新增"清空记忆"按钮（REQ-FUNC-017b） | 独立新增，不影响现有 reasoning 展示 |
| MOD-BE-NEW (chat_session/message Models) | 新建 | 全新 Django Model + Migration | 独立新增 |
| MOD-BE-API (views.py 或新 admin_views.py) | 新增端点 | 新增 memory CRUD API（REQ-FUNC-017a~c） | 独立新增，不影响现有 API |
| MOD-OPS-SKEL (骨架文件保护脚本) | 新建 | 新建 scripts/skeleton_guard.sh | 独立，不影响任何 Python 代码 |
