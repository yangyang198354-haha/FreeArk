<file_header>
  project: v1.12.0_chat_persona_voice
  document_type: tech_stack
  status: DRAFT
  author_agent: sub_agent_system_architect
  created_at: 2026-07-05T00:00:00Z
  version: 0.1.0
  parent_invocation: GROUP_B_PHASE_03_04
  dependencies:
    - requirements_spec.md (v0.1.0, APPROVED)
    - architecture_design.md (v0.1.0, DRAFT)
</file_header>

# 技术选型表 — v1.12.0 方舟副官人格与语音输入

## 1. 技术选型总表

### 1.1 前端（微信小程序）

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|----------|-----------|-----------|------|------|
| 框架 | uni-app (Vue 3) | 3.x (现有) | 现有技术栈，无变更 | CON-04 | 无 | `<script setup>` + Composition API |
| 状态管理 | Pinia | 2.x (现有) | 现有技术栈，useChatStore 扩展 persona 字段 | CON-04, REQ-FUNC-005 | 低: store 字段增加但无结构变更 | useAuthStore/useChatStore/useOwnerStore 均已有 |
| HTTP 客户端 | 自定义 http.js | 现有 | 现有封装，封装 uni.request；新增 getPersona/updatePersona 方法 | — | 无 | 复用既有拦截器/错误处理 |
| WebSocket | ChatWebSocket | 现有 | 现有 RFC 6455 封装；connect URL 新增 active_sp 参数 | REQ-NFUNC-004 | 低: 仅 URL 参数增加 | 协议帧兼容（新增字段为 optional） |
| 聊天组件 | ChatBubble.vue | 现有 | streaming/reasoning/markdown/confirm 渲染，无变更 | REQ-NFUNC-004 | 无 | 人格/座舱信息由 LLM 回复内容体现，无需组件级变更 |
| UI 主题 | 赛博朋克 | 现有 | 暗色底 #05070f，霓虹色 #2ff4e0 | — | 无 | 语音按钮动画需使用主题色 |
| **语音输入插件** | **微信同声传译插件** | **0.3.6** (最新稳定版) | OQ-04 PM 确认"微信同声传译插件（客户端方案）"。零后端新增、零 pip install、微信官方维护、隐私合规（音频不出微信端）、免费 | REQ-FUNC-010~013, REQ-NFUNC-001/005, CON-01 | 中: 插件版本依赖微信客户端（需 >= 7.0.0 支持）；仅支持普通话；若插件下线需迁移方案 | APPID: `wxeb9a1a3c3cc0a0f3`；在 app.json plugins 段声明；使用 speechToText API |

### 1.2 后端（Django）

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|----------|-----------|-----------|------|------|
| Web 框架 | Django | 4.x (现有) | 现有技术栈，无变更 | CON-03 | 无 | 含 DRF + Channels |
| ASGI 服务器 | Daphne / Uvicorn | 现有 | 现有技术栈，无变更 | — | 无 | 生产使用 Uvicorn |
| 数据库 | PostgreSQL | 14+ (现有) | 现有技术栈；JSONField 使用 jsonb 原生类型 | REQ-NFUNC-003 | 无 | jsonb 支持索引、查询、部分更新 |
| ORM | Django ORM | 4.x (现有) | 现有技术栈；JSONField 原生支持 | CON-03 | 无 | `models.JSONField(default=dict, blank=True)` |
| **数据模型变更** | **CustomUser 新增 persona JSONField** | **Migration** | OQ-02 PM 确认"扩展 UserProfile 加 JSON 字段"。v1 人格维度仅 greeting_style + tone_style 两个键，JSONField 足够 | REQ-FUNC-004, REQ-NFUNC-003, OQ-02 | 低: ALTER TABLE ADD COLUMN 是向后兼容操作，不锁表 (PostgreSQL) | 新 migration 序号接续现有 00xx 序列 |
| **REST API** | **Django REST Framework** | **3.x (现有)** | 无新增依赖；新增 PersonaSerializer + 2 个视图函数 | REQ-FUNC-004, OQ-06 | 无 | 复用 IsOwnerUser 权限类 |
| 聊天编排 | LangGraph (StateGraph) | 0.2.x (现有) | 现有架构；orchestrator._expert 节点新增 persona_msg + cabin_msg 注入 | REQ-FUNC-001/002/007 | 低: 仅在 msgs 列表追加 SystemMessage，不改变图结构 | MemorySaver + interrupt/resume 不变 |
| LLM | DeepSeek v4-flash | 现有 (langchain_openai) | 现有架构；persona 和 cabin 指令通过 SystemMessage 注入，无协议变更 | REQ-FUNC-001/002 | 低: token 消耗增加 ~50-150 tokens/请求（persona + cabin ctx） | OpenAI 兼容协议，temperature=0.2 |
| LLM 库 | langchain-openai | 0.3.x (现有) | 现有架构；_ReasoningChatOpenAI 子类透传 reasoning_content | — | 无 | 已在生产验证 |
| WebSocket | Django Channels | 4.x (现有) | 现有 MiniAppChatConsumer 扩展；connected 帧新增 persona + cabin_status 可选字段 | REQ-NFUNC-004 | 无 | AsyncWebsocketConsumer 基类不变 |
| 工具注册 | TOOLS_BY_EXPERT | 现有 | experts.py ExpertSpec 注册表不变 | — | 无 | 无新增工具 |
| 提示装载 | prompts.py | 现有 | 从 agents/ 目录加载 SYSTEM_PROMPT.langgraph.md；persona 通过独立 SystemMessage 注入（不修改提示文件） | REQ-FUNC-001 | 无 | 架构决策 ADR-002/007：独立消息块注入，不修改静态提示文件 |
| 用户范围 | UserScope | 现有 | frozen dataclass；复用 is_unbound()/is_multi_bound() | REQ-FUNC-006/007/008 | 无 | build_user_scope() 不变 |

### 1.3 基础设施

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|----------|-----------|-----------|------|------|
| 数据库 Migration | Django Migration | 现有 | `python manage.py makemigrations` 自动生成 | REQ-NFUNC-003 | 低: 标准 Django migration 流程 | migration 文件: `api/migrations/00xx_customuser_persona.py` |
| **零新增第三方依赖** | **N/A** | **N/A** | ADR-003 确认微信同声传译插件为纯前端方案；persona 使用 Django ORM JSONField (内置)；无需 pip install 任何新包 | OQ-04, CON-03 | 无 | 这是设计目标，已达成 |
| 部署流程 | systemd + git pull | 现有 | 无变更 | — | 无 | 灰度先切 langgraph 路径验证 |

---

## 2. 依赖变更对比

### 2.1 新增依赖

| 依赖 | 层次 | 原因 |
|------|------|------|
| **微信同声传译插件** (wxeb9a1a3c3cc0a0f3) | 前端 | OQ-04 语音转文字（客户端方案，仅 app.json 声明） |
| 无 pip/pkg 新增 | 后端 | 全部使用现有技术栈 |

### 2.2 修改的现有组件

| 组件 | 变更类型 | 说明 |
|------|---------|------|
| CustomUser (models.py) | 字段新增 | `persona = JSONField(default=dict, blank=True)` |
| MiniAppChatConsumer (consumers.py) | 逻辑扩展 | connected 帧扩展；_handle_chat 透传 persona |
| orchestrator.py | 逻辑扩展 | _expert 节点追加 persona_msg + cabin_msg |
| adapter.py | 签名扩展 | stream_chat() 新增 persona, cabin_active_sp 参数 |
| prompts.py | 无变更 | 不修改静态提示文件 |
| experts.py | 无变更 | ExpertSpec 注册表不变 |
| urls_miniapp.py | 路由新增 | GET/PUT /api/miniapp/persona/ |
| chat.js (store) | 状态扩展 | 新增 persona + cabinStatus 字段和 actions |
| owner.js (store) | 无变更 | chat/index.vue 直接引用 |
| chat-ws.js | URL 扩展 | connect() 增加 active_sp query param |
| api.js | 方法新增 | getPersona(), updatePersona() |
| chat/index.vue | 逻辑重写 | onVoice() 重写；引入 useOwnerStore；connected 回调扩展 |
| app.json | 插件声明 | 新增 WechatSI 插件 |

### 2.3 不变更的现有组件（保障向下兼容）

| 组件 | 原因 |
|------|------|
| ChatBubble.vue | 人格/座舱信息由 LLM 回复内容体现，无需组件变更 |
| ArkTabBar.vue | 与本次迭代无关 |
| ChatConsumer (Web 端父类) | 本次仅影响 MiniAppChatConsumer，Web 管理后台不受影响 |
| LangGraph 图结构 | route → expert(fan-out) → gate → aggregate 结构不变 |
| TOOLS_BY_EXPERT | 无新增工具 |
| scope_enforcer.py | v1.8.0 已有，复用 |
| auth.js (store) | 无变更 |
| login/index.vue | 无变更 |
| home/index.vue | 无变更 (仅 chat/index.vue 引用 useOwnerStore) |

---

## 3. 数据层 Migration 策略

### 3.1 CustomUser.persona 字段 Migration

```python
# api/migrations/00xx_customuser_persona.py

from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('api', '00xx_previous_migration'),  # 接续最新 migration
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='persona',
            field=models.JSONField(
                default=dict,
                blank=True,
                verbose_name='人格偏好',
                help_text='{"greeting_style":"副官","tone_style":"尊敬的舰长大人"}'
            ),
        ),
    ]
```

- **迁移风险**: 极低
  - PostgreSQL `ALTER TABLE ADD COLUMN` 不锁表（`ADD COLUMN ... DEFAULT` 需 PostgreSQL 11+ 才不重写表; Django 的 `default=dict` 在 Python 层生效，不会在 DB 层设置列默认值，因此不重写表）
  - 新列为 nullable + 有应用层默认值（`default=dict`），存量数据自动获得 `{}`
  - 向下列: 旧代码不查询 persona 字段，无影响
- **回滚**: `migrate api <previous_migration>` — 移除列，无数据丢失（persona 的设置可通过 LLM 重新生成）

### 3.2 Schema 变更验证清单

- [ ] `python manage.py makemigrations` 生成正确的 migration 文件
- [ ] `python manage.py migrate` 在本地/CI PostgreSQL 上成功执行
- [ ] 存量 CustomUser 行查询正常（persona 为 `{}`）
- [ ] 新用户创建正常（persona 为 `{}`）
- [ ] `user.persona = {"greeting_style": "副官", "tone_style": "舰长"}; user.save()` 正常持久化
- [ ] `python manage.py migrate api <previous>` 回滚成功

---

## 4. 技术风险汇总

### 4.1 High Risk

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 微信同声传译插件下线或不兼容 | 语音输入功能完全失效 | 1) 插件为微信官方维护，下线概率极低；2) 模块化封装 voice-input.js，替换插件只需改该文件；3) 降级: onVoice 回退到 toast 占位（与当前行为一致） |

### 4.2 Medium Risk

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 微信同声传译插件仅支持普通话，不支持方言/英语 | 非普通话用户无法使用语音输入 | 1) v1.12.0 目标用户群体为中国业主，普通话为主；2) 文本输入始终为后备方案；3) 若未来需多语种，可评估切换到后端 ASR 方案 |
| persona JSONField 无 DB 层 schema 校验 | 应用层写入了不符合预期的 JSON 结构，导致 build_persona_message() 逻辑错误 | 1) PersonaSerializer 做严格的字段级校验；2) build_persona_message() 对异常值做防御性回退（缺失键→使用默认值） |
| LLM token 消耗增加 | persona + cabin 消息每请求增加 ~50-150 tokens，月费用上升 | 1) 增量可控（占单次请求 token 的 ~5-10%）；2) persona/cabin 消息长度固定，不随对话增长 |
| active_specific_part 来自前端 storage (非后端权威) | 切换设备或清缓存后，首次连接 active_sp 为空 | 1) 降级策略: active_sp 为空时注入全部绑定的房间；2) LLM 可反问用户具体房间 |

### 4.3 Low Risk

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| connected 帧体积增大 | 新增 persona + cabin_status 字段增加 JSON payload ~200 bytes | 一次性传输（仅 connect 时发送），影响可忽略 |
| useChatStore 膨胀 | persona/cabinStatus 字段使 chat store 增加 ~10 行 | 尚在合理范围（当前 store ~50 行），若未来继续膨胀可拆分子 store |
| migration 在大型 User 表上执行时间 | 用户表规模预计 < 10K 行，ALTER TABLE 耗时 < 1s | 在低峰期（凌晨）执行 migration |

---

## 5. 技术约束遵守情况

| 约束 ID | 约束描述 | 遵守情况 |
|---------|---------|---------|
| CON-01 | 语音输入必须使用微信小程序原生 API 或官方插件 | 遵守: 微信同声传译插件 (wxeb9a1a3c3cc0a0f3) 是微信官方插件 |
| CON-02 | 语音输入功能仅限微信小程序端 | 遵守: VoiceInput 组件仅在 miniprogram/ 目录，后端无语音相关代码 |
| CON-03 | 人格偏好存储需与 Django ORM + PostgreSQL 兼容 | 遵守: 使用 Django 内置 JSONField + PostgreSQL jsonb |
| CON-04 | 状态管理使用 Pinia | 遵守: 扩展 useChatStore（现有 Pinia store），不引入新状态库 |
| CON-05 | 座舱绑定信息已通过 UserScope 传递至后端 | 遵守: 复用现有 build_user_scope()，扩展 cabin context 注入 |
| OQ-01 | v1 人格维度: greeting_style + tone_style | 遵守: persona JSONField 仅存储这两个键 |
| OQ-02 | 扩展 CustomUser 加 JSON 字段（非新建表） | 遵守: CustomUser 新增 persona JSONField |
| OQ-03 | 独立系统消息块注入房号上下文 | 遵守: ADR-002 — 第二个 SystemMessage 块 |
| OQ-04 | 微信同声传译插件（客户端方案） | 遵守: VoiceInput 纯前端模块，零后端新增 |
| OQ-05 | 多座舱默认用 activeSpecificPart | 遵守: ADR-004 — 优先活跃房间，降级列出全部 |
| OQ-06 | 支持后续修改人格 (US-003 升级) | 遵守: ADR-005 — PUT /api/miniapp/persona/ 端点 |

---

## 6. 非功能需求覆盖验证

| REQ-NFUNC | 描述 | 技术保障 |
|-----------|------|---------|
| REQ-NFUNC-001 | 音频采样率 >= 16000 Hz | 微信同声传译插件内部处理，默认满足 ASR 要求 |
| REQ-NFUNC-002 | 语音识别 5 秒内返回 | 微信同声传译插件在微信客户端本地处理，延迟 < 3s（实测经验） |
| REQ-NFUNC-003 | 人格持久化事务性 | Django ORM 写入 CustomUser.persona → PostgreSQL 事务保证 |
| REQ-NFUNC-004 | 向下兼容现有聊天功能 | WS 协议仅扩展 optional 字段；LangGraph 图结构不变；所有现有代码路径不变 |
| REQ-NFUNC-005 | 音频不落盘 | 微信同声传译插件在微信沙箱内完成录音+识别，不产生可访问的文件 |

---

## 7. 版本约束汇总

| 组件 | 最低版本 | 推荐版本 | 约束原因 |
|------|---------|---------|---------|
| 微信客户端 | 7.0.0+ | 最新版 | 同声传译插件最低要求（实际市面设备均已满足） |
| uni-app | 3.0+ | 现有 | `<script setup>` + Pinia 支持 |
| PostgreSQL | 11+ | 14+ (现有) | ALTER TABLE ADD COLUMN 不重写表（PostgreSQL 11+） |
| Django | 4.x | 现有 | JSONField 原生支持 |
| 微信同声传译插件 | 0.3.5+ | 0.3.6 | speechToText API 稳定版 |
| Python | 3.10+ | 现有 | Django 4.x 要求 |
</file_header>
