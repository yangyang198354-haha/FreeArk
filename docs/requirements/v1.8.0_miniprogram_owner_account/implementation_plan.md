# 实现计划（Implementation Plan）

**版本**：v1.8.0_miniprogram_owner_account  
**日期**：2026-06-25  
**状态**：DRAFT  
**作者**：software-developer (SDLC Agent)  
**依赖**：architecture_design.md (APPROVED)，module_design.md (APPROVED)

---

## 实现顺序

按依赖关系从底层到上层依次实现，每步均有明确边界。

| 步骤 | 模块 | 文件 | 操作类型 |
|------|------|------|---------|
| 1 | MOD-180-01 | `api/models.py` | 末尾追加 |
| 2 | MOD-180-13 | `api/migrations/0041_*.py` | 新建 |
| 3 | MOD-180-02 | `api/middleware.py` | 最小插入（3行） |
| 4 | MOD-180-05 | `api/langgraph_chat/user_scope.py` | 新建 |
| 5 | MOD-180-06 | `api/langgraph_chat/scope_enforcer.py` | 新建 |
| 6 | MOD-180-07 | `api/langgraph_chat/orchestrator.py` | 最小插入 |
| 7 | MOD-180-08 | `api/langgraph_chat/fa_tools.py` | 最小插入（两处签名） |
| 8 | MOD-180-10 | `api/langgraph_chat/adapter.py` | 最小插入 |
| 9 | MOD-180-09 | `api/consumers.py` | 末尾追加新类 |
| 10 | — | `api/views.py` | 末尾追加 IsOwnerUser |
| 11 | MOD-180-03 | `api/views_miniapp.py` | 新建 |
| 12 | MOD-180-04 | `api/urls_miniapp.py` | 新建 |
| 13 | — | `freearkweb/urls.py` | 追加 include |
| 14 | — | `api/routing.py` | 追加 WS 路由 |
| 15 | — | `freearkweb/settings.py` | 追加 WECHAT 配置 |
| 16 | MOD-180-11 | `miniprogram/utils/chat-ws.js` | 单行修改 |
| 17 | — | `miniprogram/tests/chat-ws.spec.js` | 单行修改 |
| 18 | 文档修正 | `docs/.../architecture_design.md` | 修正笔误 |

---

## 关键约束

- 每步改动范围严格限于架构文档 §8.1 和 tech_stack.md 改动清单
- 现有文件改动仅追加或最小插入，不重构、不删除、不重排现有代码
- 迁移 dependencies 填真实最新号 0040
- 不 git commit，不接触生产
