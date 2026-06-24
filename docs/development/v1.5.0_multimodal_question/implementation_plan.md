特性：多模态提问——用户图片输入与豆包视觉模型理解
版本：v1.5.0_multimodal_question
状态：DRAFT
日期：2026-06-24
作者：software-developer

---

# 实现计划 — v1.5.0 多模态提问

## 实现概览

- 总模块数：7（MOD-MQ-01 ~ MOD-MQ-07）
- 涉及文件：9 个（2 新增 + 7 修改）
- 实现顺序：依赖图拓扑排序（底层先实现，上层依赖后实现）

## 拓扑排序依赖图

```
MOD-MQ-07（配置+路由）← 被 MOD-MQ-03 读取
MOD-MQ-03（vision_service）← 被 MOD-MQ-02 和 MOD-MQ-05 调用
MOD-MQ-02（REST 视图）← 被 MOD-MQ-07 注册路由
MOD-MQ-06（orchestrator State 扩展）← 被 MOD-MQ-05 使用
MOD-MQ-05（adapter 扩展）← 被 MOD-MQ-04 调用
MOD-MQ-04（consumers 扩展）← 入口层
MOD-MQ-01（前端模块）← 依赖 REST 接口和 WS 协议
```

## 模块实现计划（按拓扑顺序）

| 序号 | MOD-ID | 模块名 | 文件路径 | 依赖前置模块 | 复杂度 | 状态 |
|------|--------|--------|----------|------------|--------|------|
| 1 | MOD-MQ-07 | 配置与路由扩展 | `freearkweb/freearkweb/settings.py`（修改）、`api/urls.py`（修改） | — | L | PLANNED |
| 2 | MOD-MQ-03 | 视觉服务模块 | `api/vision_service.py`（新增） | MOD-MQ-07 | H | PLANNED |
| 3 | MOD-MQ-02 | 图片预上传 REST 视图 | `api/views_chat_image.py`（新增） | MOD-MQ-03 | M | PLANNED |
| 4 | MOD-MQ-06 | LangGraph 编排图扩展 | `api/langgraph_chat/orchestrator.py`（最小修改） | — | L | PLANNED |
| 5 | MOD-MQ-05 | LangGraph 适配器扩展 | `api/langgraph_chat/adapter.py`（修改） | MOD-MQ-03、MOD-MQ-06 | M | PLANNED |
| 6 | MOD-MQ-04 | WS 消费者扩展 | `api/consumers.py`（修改） | MOD-MQ-03、MOD-MQ-05 | M | PLANNED |
| 7 | MOD-MQ-01 | 前端多模态输入模块 | `frontend/src/views/ChatView.vue`（修改）、`frontend/src/utils/api.js`（修改） | MOD-MQ-02 | M | PLANNED |

## 文件清单（按实现顺序）

### 步骤 1 — MOD-MQ-07：配置与路由

1. `FreeArkWeb/backend/freearkweb/freearkweb/settings.py`（追加 VLM 配置块）
2. `FreeArkWeb/backend/freearkweb/api/urls.py`（追加图片上传路由）

### 步骤 2 — MOD-MQ-03：视觉服务模块（新增）

3. `FreeArkWeb/backend/freearkweb/api/vision_service.py`

### 步骤 3 — MOD-MQ-02：REST 视图（新增）

4. `FreeArkWeb/backend/freearkweb/api/views_chat_image.py`

### 步骤 4 — MOD-MQ-06：orchestrator State 扩展

5. `FreeArkWeb/backend/freearkweb/api/langgraph_chat/orchestrator.py`（单行变更）

### 步骤 5 — MOD-MQ-05：adapter 扩展

6. `FreeArkWeb/backend/freearkweb/api/langgraph_chat/adapter.py`

### 步骤 6 — MOD-MQ-04：consumers 扩展

7. `FreeArkWeb/backend/freearkweb/api/consumers.py`

### 步骤 7 — MOD-MQ-01：前端模块

8. `FreeArkWeb/frontend/src/utils/api.js`（追加 uploadChatImage）
9. `FreeArkWeb/frontend/src/views/ChatView.vue`（图片选择/预览/发送/历史标注）

## 数据库变更

无新增 migration（ADR-MQ-002 决策：进程内 dict 存储，不落 DB）。

## 架构偏差记录

无架构偏差。

所有实现均严格遵循以下 ADR 决策：
- ADR-MQ-001：VLM 在 adapter 层外置调用（不在 LangGraph 节点内）
- ADR-MQ-002：进程内 dict 临时存储（无 Django CACHES / Redis / /tmp）
- ADR-MQ-003：VLM 描述文字追加到 user 消息（不存原图字节）

## 关键实现约束备注

1. base64 绝不进任何 logger 调用（CRITICAL 约束）
2. MIME 验证使用魔数字节检测（不依赖 python-magic / libmagic1，规避生产部署风险）
3. `persist_enhanced_message` kind 在 _pump 中识别但不转发前端
4. `upload_id` 格式校验（UUID4）在 consumers.receive 入口执行
5. 向后兼容：不含 image_upload_id 的 WS 消息行为与 v1.4.1 完全一致
