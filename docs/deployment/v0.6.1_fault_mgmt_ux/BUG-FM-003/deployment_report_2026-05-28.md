# BUG-FM-003 生产部署报告

| 项 | 值 |
|---|---|
| BUG 编号 | BUG-FM-003 |
| 标题 | 故障管理页面"故障类型/设备类型"过滤器无效 |
| commit | `94fb3fd fix(fault-mgmt): 故障类型/设备类型过滤器无效 (BUG-FM-003)` |
| 部署日期 | 2026-05-28 |
| 部署人 | Claude Code (Opus 4.7) |
| 目标环境 | 生产 — 树莓派 `192.168.31.51` / `et116374mm892.vicp.fun:57279` |
| 部署方式 | plink/ssh + `git pull` + `npm run build`（符合"禁 pscp"硬约束） |
| 部署结果 | ✅ 成功 |
| 服务重启 | 无（纯前端变更） |

---

## 1. 变更范围

仅前端变更 + 测试 + 文档：

| 文件 | 类型 |
|---|---|
| `FreeArkWeb/frontend/src/views/FaultManagementView.vue` | 前端修复（`fetchFaultEvents` 改用 `URLSearchParams`） |
| `FreeArkWeb/backend/freearkweb/api/tests_fault_event.py` | 新增 `TestFaultFilterParamFormatCompat` 11 个回归用例 |
| `docs/troubleshooting/BUG-FM-003_fault_type_device_type_filter_invalid.md` | RCA |

后端零改动，无 DB migration，无 systemd unit 变更。

---

## 2. 部署前置检查

| 检查项 | 结果 |
|---|---|
| 生产 HEAD（拉取前） | `c7aa7fd feat(fault-mgmt): v0.6.1 UX 调整...` |
| 生产分支 | `main` |
| 本地修改文件（不入仓的"长期本地修改"） | `.env`、`heartbeat_broker_config.json`、`package-lock.json` — 均为 skill §2 已记录的预期项 |
| 本次 commit 范围 vs 本地修改 | `git diff --name-only c7aa7fd..94fb3fd` 三个文件 **零交集**，无冲突风险 |
| SSH 连通性 | OpenSSH 密钥登录可用，免密 |

---

## 3. 部署步骤执行记录

### Step 1 — 拉代码
```
cd /home/yangyang/Freeark/FreeArk && git pull origin main
```
结果：
```
Updating c7aa7fd..94fb3fd
Fast-forward
 .../api/tests_fault_event.py    | 187 +++++++++++
 .../views/FaultManagementView.vue|  37 ++--
 ...BUG-FM-003_...md              | 153 +++++++++++++
 3 files changed, 361 insertions(+), 16 deletions(-)
```

### Step 2 — 验证代码落地
- `git log -1 --oneline` → `94fb3fd fix(fault-mgmt): 故障类型/设备类型过滤器无效 (BUG-FM-003)` ✅
- `grep -n URLSearchParams FaultManagementView.vue`：
  - 行 315：`// 修复方案：改用 URLSearchParams 手动 append，保证生成`
  - 行 317：`const qs = new URLSearchParams()`
  ✅ 修复代码已在生产源文件中

### Step 3 — 备份现 dist
```
cp -r dist /home/yangyang/FreeArk_backup/dist_backup_20260528211200
```
✅ 备份成功

### Step 4 — 构建前端
```
cd FreeArkWeb/frontend && npm run build
```
- `✓ built in 20.69s` ✅
- 新 chunk：`dist/assets/FaultManagementView-Vc0C7zHl.js`（7.86 kB / gzip 3.23 kB）
- chunk 内含 `URLSearchParams`（grep 命中 1 处），修复进入 minified bundle ✅

### Step 5 — 后端无需重启
本次为纯前端变更，`freeark-backend` 未操作。`systemctl is-active freeark-backend` → `active`。

### Step 6 — 烟测
```
curl http://127.0.0.1:8080/api/health/
→ {"status":"ok","message":"FreeArk Web API 服务正常运行"}
```
✅

---

## 4. 风险与回滚

### 风险评估
- ✅ 纯前端 minified bundle 替换，无 schema 变更、无 API 变更、无服务停机
- ✅ 修复逻辑等价：前端将原本错误的 `params: {fault_type: [...]}`（axios 序列化为 `fault_type[]=...`）改为 `URLSearchParams` 逐项 append（`fault_type=...&fault_type=...`），后端 `getlist('fault_type')` 行为不变
- ✅ 11 个回归用例覆盖单选/多选/组合/清除/非法值，全部通过

### 回滚方案
若发现回归，最快回滚：
```bash
ssh -p 57279 yangyang@et116374mm892.vicp.fun \
  'cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/frontend && \
   rm -rf dist && \
   cp -r /home/yangyang/FreeArk_backup/dist_backup_20260528211200 dist'
```
（nginx 静态文件，复制完成即生效，无需 reload。）

如需同时回滚源码：
```bash
cd /home/yangyang/Freeark/FreeArk && git reset --hard c7aa7fd
```

---

## 5. 生产验证建议（请用户验证）

打开故障管理页面 `http://et116374mm892.vicp.fun:<外网映射端口>/`，依次验证：

1. **单选故障类型**：勾选"通信"，列表只显示通信类故障
2. **多选故障类型**：同时勾选"通信"+"传感器"，列表显示这两类
3. **单选设备类型**：勾选"客厅温控器"，列表只显示该型号设备的故障
4. **多选设备类型**：勾选"客厅温控器"+"新风机"，列表显示这两类设备
5. **组合筛选**：故障类型 + 设备类型 + 仅活动，三条件交集生效
6. **清除筛选**：清空所有筛选条件，恢复显示近 7 天全量故障

⚠️ 浏览器若加载了旧 chunk（缓存），需要 **Ctrl+F5 强制刷新** 或清缓存才能加载新 `FaultManagementView-Vc0C7zHl.js`。

---

## 6. 关联文档

- RCA：`docs/troubleshooting/BUG-FM-003_fault_type_device_type_filter_invalid.md`
- 部署计划：`docs/deployment/v0.6.1_fault_mgmt_ux/BUG-FM-003/deployment_plan.md`
- 上一个相关部署（v0.6.1 故障管理 UX）：`docs/deployment/v0.6.1_fault_mgmt_ux/`
