<!--
  @file implementation_plan.md
  @module v1.11.0_miniprogram_owner_home
  @author sub_agent_software_developer
  @version 1.11.0
  @status ACTIVE
  @created 2026-06-27
  @description v1.11.0 实现计划：模块实现顺序、文件清单、依赖图
-->

# 实现计划 — v1.11.0 微信小程序业主端功能迭代

## 实现概览

- 总模块数：5（MOD-1110-BE-01, MOD-1110-BE-02, MOD-1110-FE-01, MOD-1110-FE-02, MOD-1110-FE-03）
- 总文件变更数：6（新建 3，修改 3）
- 实现顺序：叶节点先行（无依赖的基础模块先实现），被依赖模块优先

## 模块实现计划（按拓扑顺序）

| 序号 | MOD-ID | 模块名 | 文件路径 | 依赖前置模块 | 复杂度 | 状态 |
|------|--------|--------|---------|------------|--------|------|
| 1 | MOD-1110-BE-01 | miniapp_owner_realtime_params 视图 | `FreeArkWeb/backend/freearkweb/api/views_miniapp_device_settings.py`（追加） | 无（复用现有 utils） | H | PLANNED |
| 2 | MOD-1110-BE-02 | miniapp_owner_ondemand_refresh 视图 | `FreeArkWeb/backend/freearkweb/api/views_miniapp_device_settings.py`（追加） | 无（复用现有 ondemand 逻辑） | M | PLANNED |
| 3 | (路由注册) | urls_miniapp.py 路由追加 | `FreeArkWeb/backend/freearkweb/api/urls_miniapp.py`（修改） | MOD-1110-BE-01, MOD-1110-BE-02 | L | PLANNED |
| 4 | MOD-1110-FE-03 | api.js 新增调用项 | `miniprogram/utils/api.js`（追加） | 无（依赖现有 http.js） | L | PLANNED |
| 5 | MOD-1110-FE-01 | useMqttClient.js | `miniprogram/utils/useMqttClient.js`（新建） | MOD-1110-FE-03（间接，无硬依赖） | H | PLANNED |
| 6 | MOD-1110-FE-02 | param-settings.vue（扩展） | `miniprogram/subpackages/control/pages/param-settings.vue`（改造） | MOD-1110-FE-01, MOD-1110-FE-03 | H | PLANNED |
| 7 | (测试) | 后端单元测试 | `FreeArkWeb/backend/freearkweb/api/tests/test_miniapp_owner_v1110.py`（新建） | MOD-1110-BE-01, MOD-1110-BE-02 | M | PLANNED |

## 改动文件清单

### 新建文件

| 文件路径 | 类型 | 说明 |
|---------|------|------|
| `miniprogram/utils/useMqttClient.js` | 新建 | MOD-1110-FE-01：MQTT 全局单例 composable |
| `FreeArkWeb/backend/freearkweb/api/tests/test_miniapp_owner_v1110.py` | 新建 | v1.11.0 后端单元测试（归属过滤/越权403/分组逻辑） |
| `docs/development/v1.11.0_miniprogram_owner_home/implementation_plan.md` | 新建 | 本文件 |
| `docs/development/v1.11.0_miniprogram_owner_home/code_review_report.md` | 新建 | 代码评审报告 |

### 修改文件

| 文件路径 | 类型 | 说明 |
|---------|------|------|
| `FreeArkWeb/backend/freearkweb/api/views_miniapp_device_settings.py` | 追加 | MOD-1110-BE-01/BE-02：新增两个视图函数 |
| `FreeArkWeb/backend/freearkweb/api/urls_miniapp.py` | 追加路由 | 注册两个新端点 |
| `miniprogram/utils/api.js` | 追加 | MOD-1110-FE-03：两个新 API 封装函数 |
| `miniprogram/subpackages/control/pages/param-settings.vue` | 扩展改造 | MOD-1110-FE-02：追加"我的房产"区 + MQTT 迁移到单例 |

## 架构偏差记录

| 偏差ID | 偏差描述 | 原 ADR 决策 | 偏差原因 |
|--------|---------|------------|---------|
| DEV-01 | 路径A超时后**不**自动降级路径B | architecture_design.md 数据流4.2中标注 [ASSUMPTION] "超时后是否自动降级B，还是仅提示用户重试" | 用户已拍板："路径A超时仅提示'设备未响应，请确认设备在线'，不自动降级路径B"（见任务描述关键已定项）。代码实现为仅提示，按钮恢复，不调用路径B。 |

## 拓扑排序依赖图验证

```
MOD-1110-BE-01 ──► views.py 现有工具（只读，无环）
MOD-1110-BE-02 ──► views.py device_ondemand_refresh 内核（只读，提取私有函数，无环）
urls_miniapp   ──► MOD-1110-BE-01, MOD-1110-BE-02（注册）
MOD-1110-FE-03 ──► http.js（只读，无环）
MOD-1110-FE-01 ──► ScreenMqtt（只读，无环）
MOD-1110-FE-02 ──► MOD-1110-FE-01, MOD-1110-FE-03（已实现）

验证：无循环依赖，拓扑排序合法。
```
