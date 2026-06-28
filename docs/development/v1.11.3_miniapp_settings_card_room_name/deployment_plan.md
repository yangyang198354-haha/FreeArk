<!--
  @feature    v1.11.3_miniapp_settings_card_room_name
  @version    1.11.3
  @status     DRAFT
  @author_agent sub_agent_devops_engineer
  @created    2026-06-28
  @description 微信小程序 v1.11.3 发布指引（纯文档，实际发布由用户操作）
-->

# v1.11.3 微信小程序发布指引

## 概述

本文档为微信小程序 v1.11.3（参数设置页区域二设备卡片显示具体房间名）的完整发布指引。

- 代码变更范围：`miniprogram/subpackages/control/pages/param-settings.vue`（单文件）
- 零后端改动，零新依赖，零数据库 migration
- 测试状态：vitest 22/22 PASS，`npm run build:mp-weixin` PASS

**重要说明**：本文档仅为指引，实际发布步骤（第 2 节 2.2~2.5）必须由用户本人在微信开发者工具和微信公众平台操作，子代理无法代为执行。

---

## 第 1 节：构建步骤

### 1.1 前置条件检查

**检查 v1.11.3 改动已在当前 commit：**

```powershell
cd C:\Users\胖子熊\MyProject\FreeArk
git log --oneline -5
```

确认最新提交包含 `param-settings.vue` 的 v1.11.3 改动（`deviceList` computed 新增 `roomNameMap` + `connectRoom()` 末尾追加 `_initPartState`/`loadStructure`）。

**检查 node_modules 已安装：**

```powershell
Test-Path C:\Users\胖子熊\MyProject\FreeArk\miniprogram\node_modules\.bin\vitest
```

返回 `True` 则已就绪；返回 `False` 则先执行安装：

```powershell
cd C:\Users\胖子熊\MyProject\FreeArk\miniprogram
npm install
```

### 1.2 构建命令

在 `miniprogram/` 目录执行：

```powershell
cd C:\Users\胖子熊\MyProject\FreeArk\miniprogram
npm run build:mp-weixin
```

等价的直接调用形式（效果相同）：

```powershell
cross-env UNI_INPUT_DIR=. uni build -p mp-weixin
```

### 1.3 构建产物路径

| 项目 | 路径 |
|------|------|
| 输出目录 | `miniprogram/dist/build/mp-weixin/` |
| 本次核心产物 | `dist/build/mp-weixin/subpackages/control/param-settings.js` |
| 构建成功标志 | 终端末行输出 `DONE  Build complete.` |

### 1.4 构建后验证

```powershell
# 确认输出目录存在且非空
Test-Path C:\Users\胖子熊\MyProject\FreeArk\miniprogram\dist\build\mp-weixin\subpackages\control\param-settings.js
```

返回 `True` 表示核心产物已生成。终端构建日志中无 `ERROR` 行（`warning` 可忽略）。

---

## 第 2 节：微信开发者工具发布流程

### 2.1 导入项目

1. 打开微信开发者工具
2. 选择"导入项目"
3. 目录选择：`C:\Users\胖子熊\MyProject\FreeArk\miniprogram\dist\build\mp-weixin\`
   - **注意**：选 `dist/build/mp-weixin/`，不是 `miniprogram/` 根目录
4. 确认 AppID 与生产小程序 AppID 一致（不得使用测试号）

### 2.2 本地预览验证（上传前必做）

1. 在微信开发者工具点击"编译"，等待编译完成
2. 确认编译日志无 ERROR（Warnning 可忽略）
3. 切换到参数设置页：`subpackages/control/pages/param-settings`
4. 展开区域二（设备控制区），观察末端温控设备的卡片标题：
   - **预期**：显示具体房间名（如"主卧"、"书房"），不再显示"末端温控"
   - **异常**：显示空白、显示"undefined"、页面崩溃 → 停止发布，查看控制台报错
5. 检查系统设备卡片（主温控器、新风机等）标题：
   - **预期**：与 v1.11.2 一致，不受本次改动影响
6. 在区域二选择一个末端温控设备，确认参数下发功能（修改参数 → 点击下发）正常响应

### 2.3 上传（生成候选版本）

1. 在微信开发者工具点击工具栏"上传"按钮
2. 填写版本号：`1.11.3`
3. 填写版本描述：`参数设置页区域二末端温控设备卡片显示具体房间名`
4. 点击"上传"，等待上传完成提示

### 2.4 提交审核

1. 浏览器打开微信公众平台：https://mp.weixin.qq.com
2. 进入"版本管理"
3. 在"开发版本"列表中找到刚上传的 1.11.3 版本
4. 点击"提交审核"
5. 填写功能描述（示例）：

   > 参数设置页"我的设备"区域，末端温控设备（如风机盘管）卡片标题由通用名称改为显示实际安装房间名，方便业主区分控制各房间温控设备。

6. 提交后等待微信官方审核（通常 1~7 个工作日）

### 2.5 审核通过后发布

1. 登录微信公众平台 → "版本管理"
2. 在"审核版本"中找到 1.11.3，确认状态为"审核通过"
3. 点击"发布"
4. 选择全量发布（或按需选择灰度比例）
5. 确认发布后，在微信客户端（真机）进入小程序，验证线上版本已更新至 v1.11.3

---

## 第 3 节：NOT_TESTABLE AC 的手工验证清单

GROUP_D 测试中以下 4 个 AC 因需要 Vue 运行时而无法在 Vitest 层验证，须在微信开发者工具真实环境中手工确认。

---

### AC-003-03：structure 加载完成后卡片标题响应式自动更新

**场景**：用户首次进入参数设置页，structure 缓存已过期或不存在。

**模拟方法**：在微信开发者工具 → "清缓存" → 清除全部本地存储（或精确清除键名含 `owner_structure_` 的条目）。

**验证步骤**：
1. 执行清缓存操作
2. 打开参数设置页，立即盯住区域二末端温控卡片标题
3. 初始阶段（约 1~2 秒内，structure 请求未返回）：标题应显示"末端温控"
4. 网络请求返回后：标题应**自动变更**为具体房间名，无需手动刷新

**通过标准**：标题从"末端温控"变为房间名，过渡无白屏、无崩溃、无 JS 错误。

---

### AC-004-01：进入页面时主动触发 loadStructure（缓存命中，不发网络请求）

**场景**：structure 缓存有效（24h TTL 内），再次进入参数设置页应命中缓存。

**验证步骤**：
1. 确保参数设置页已加载过至少一次（本地已有 `owner_structure_{sp}` 缓存）
2. 退出页面，再重新进入参数设置页（不展开区域一）
3. 打开微信开发者工具 → Network 面板
4. 观察是否有 `/api/miniapp/owner/structure/` 请求发出

**通过标准**：卡片直接显示具体房间名（缓存命中），Network 面板无新的 structure 接口请求。

---

### AC-004-02：进入页面时主动触发 loadStructure（无缓存，发网络请求）

**场景**：structure 缓存不存在，进入参数设置页应触发网络请求。

**验证步骤**：
1. 在微信开发者工具 → "清缓存" → 清除全部（确保无 `owner_structure_*` 缓存）
2. 打开参数设置页
3. 在 Network 面板观察请求列表

**通过标准**：Network 面板出现一次 `/api/miniapp/owner/structure/` 请求，请求完成后卡片标题更新为具体房间名。

---

### AC-004-03：切换房间（specific_part 变化）时触发独立 loadStructure

**前置条件**：用户账号绑定了至少两个专有部分（two specific_part，例如 sp-A 和 sp-B）。

**验证步骤**：
1. 进入参数设置页，当前选中房间 A（specific_part=sp-A），卡片显示 sp-A 的房间名
2. 点击页面上方 picker，切换到房间 B（specific_part=sp-B）
3. 若 sp-B 的 structure 缓存不存在（可清除），在 Network 面板观察：
   - 切换后应出现针对 sp-B 的 `/api/miniapp/owner/structure/` 请求
   - 请求完成后，区域二卡片标题更新为 sp-B 的具体房间名
4. 再切换回房间 A，验证 sp-A 的卡片标题仍正确显示

**通过标准**：sp-B structure 请求独立发出；sp-A 数据不受影响（切回 sp-A 仍显示正确房间名）。

---

## 第 4 节：回滚方案

### 4.1 触发条件

若 v1.11.3 上线后出现以下任一问题，立即执行回滚：

- 末端温控卡片标题显示异常（崩溃、空白、显示错误房间名）
- 系统设备卡片（主温控器/新风机）的角色名被意外更改
- 参数设置区域二写链路异常（参数下发无响应或报错）

### 4.2 回滚步骤

**步骤 1：定位 v1.11.3 的 commit hash**

```powershell
cd C:\Users\胖子熊\MyProject\FreeArk
git log --oneline miniprogram/subpackages/control/pages/param-settings.vue
```

找到引入 v1.11.3 改动的 commit hash（示例：`abc1234`）。

**步骤 2：创建回滚 commit**

```powershell
git revert abc1234 --no-edit
```

`git revert` 创建一个新 commit 撤销指定改动，保留完整历史记录，比 `git reset --hard` 更安全。

**步骤 3：重新构建**

```powershell
cd C:\Users\胖子熊\MyProject\FreeArk\miniprogram
npm run build:mp-weixin
```

**步骤 4：重新上传并发布**

- 在微信开发者工具导入 `dist/build/mp-weixin/`
- 上传版本号建议：`1.11.3.1` 或 `1.11.3-hotfix`
- 按第 2 节流程走审核发布

### 4.3 回滚后验证

| 验证项 | 预期结果 |
|--------|---------|
| 末端温控卡片标题 | 重新显示"末端温控"（回到 v1.11.2 行为） |
| 系统设备卡片标题 | 与 v1.11.2 一致 |
| 参数下发功能 | 正常响应 |
| 区域一展开结构 | 不受影响 |

### 4.4 回滚影响范围

| 内容 | 影响 |
|------|------|
| `param-settings.vue` | 回滚两处改动，恢复至 v1.11.2 状态 |
| 后端代码 | 无影响（本次零后端改动） |
| 数据库 | 无影响（无 migration） |
| 其他前端文件 | 无影响（本次仅改 param-settings.vue） |

---

## 第 5 节：发布清单汇总

在正式执行发布前，逐项打勾确认：

```
发布前检查清单 v1.11.3
==================================================

构建阶段：
[ ] git log 确认 v1.11.3 改动（roomNameMap + connectRoom）已在当前 commit
[ ] npm run build:mp-weixin 执行成功，终端无 ERROR 行
[ ] dist/build/mp-weixin/subpackages/control/param-settings.js 文件存在

工具验证阶段（微信开发者工具）：
[ ] 导入 dist/build/mp-weixin/ 成功，编译无报错
[ ] 参数设置页区域二末端温控卡片显示具体房间名（非"末端温控"）
[ ] 系统设备（主温控器/新风机）卡片标题显示与 v1.11.2 一致
[ ] 参数下发功能（修改参数 → 点击下发）响应正常
[ ] 区域一展开结构显示正常

发布阶段（微信公众平台）：
[ ] 上传版本号填写：1.11.3
[ ] 版本描述填写完整
[ ] 提交审核
[ ] 审核通过后执行发布
[ ] 真机验证线上版本已更新至 v1.11.3
```
