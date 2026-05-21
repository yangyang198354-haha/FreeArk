# 部署计划 — BUG-CSRF-001 修复 (v0.5.7)
# version: v0.5.7_csrf_relogin
# author_agent: sub_agent_devops_engineer (orchestrated by main_agent_pm)
# status: DRAFT — 等待用户 CONFIRM 后执行
# date: 2026-05-21

---

## 1. 部署概览

| 项目 | 内容 |
|------|------|
| 修复版本 | v0.5.7_csrf_relogin |
| 变更文件 | `frontend/src/utils/api.js`, `frontend/src/components/Layout.vue` |
| 变更类型 | 纯前端 JavaScript/Vue 修改，无 DB migration，无后端变更 |
| 前端构建 | 需要 `npm run build` 重新打包（在开发机执行） |
| 部署方式 | 生产服务器执行 `git pull` + 静态文件同步 |
| 预计停机时间 | 0（前端静态文件替换，无需重启后端服务） |
| 回滚方式 | `git revert` + 重新构建 + 重新部署 |

---

## 2. 生产环境信息

| 项目 | 值 |
|------|---|
| 生产服务器 | 树莓派，内网 192.168.31.51 |
| 外网访问 | et116374mm892.vicp.fun:57279 |
| 前端静态文件目录 | `/home/pi/freeark-prod/FreeArkWeb/frontend/dist/` |
| 后端服务 | freeark-backend.service（Waitress，本次不重启） |
| 部署工具 | plink（SSH）+ git pull |

---

## 3. 前置条件（部署前检查）

- [ ] 本次修复的 commit 已推送到 `main` 分支（`git log` 确认）
- [ ] 前端已在开发机完成 `npm run build`，`dist/` 目录已更新
- [ ] 构建产物已通过本地验证（登录/登出/再登录链路）
- [ ] 生产服务器可通过 plink 连接（SSH 密钥正常）
- [ ] 已收到 PM 的 PRODUCTION_DEPLOY_CONFIRM 信号

---

## 4. 部署步骤

### Step 1: 开发机 — 提交并推送代码

```bash
cd C:\Users\yanggyan\MyProject\FreeArk

# 确认变更文件
git status

# 添加变更
git add FreeArkWeb/frontend/src/utils/api.js
git add FreeArkWeb/frontend/src/components/Layout.vue
git add FreeArkWeb/backend/freearkweb/api/tests/test_csrf_relogin.py
git add docs/bugfix/v0.5.7_csrf_relogin/

# 提交
git commit -m "fix(auth): BUG-CSRF-001 登出后再登录 CSRF token 失效

根因：handleLogout 未调用后端 logout 端点，未清除 cachedCSRFToken 内存缓存，
     导致 Django rotate_token() 后前端持有过期 CSRF token。

修复：
- api.js: clearCSRFToken() 重置缓存；getCSRFToken() 改为每次从 cookie 读取；
          ensureCSRFToken() 优先从 cookie 读；新增 api.logout() 方法
- Layout.vue: handleLogout 改为 async，调用 api.logout() + 清除 csrftoken cookie

测试: 14 个新增自动化测试全部通过，覆盖 AC-1~AC-4"

# 推送到 main 分支
git push origin main
```

### Step 2: 开发机（Windows PowerShell）— 提交推送源码

```powershell
cd C:\Users\yanggyan\MyProject\FreeArk
git push origin main

# 确认推送成功
git log origin/main --oneline -3
```

**注**：`.gitignore` 中包含 `dist/`，构建产物不追踪到 git，由生产服务器自行构建。

### Step 3: 生产服务器 — SSH 登录

```bash
# 内网直连
ssh yangyang@192.168.31.51
# 或外网
plink -ssh yangyang@et116374mm892.vicp.fun -P 57279
```

### Step 4: 生产服务器 — git pull 拉取源码

```bash
cd /home/yangyang/Freeark/FreeArk

# 查看待拉取内容
git fetch origin
git log HEAD..origin/main --oneline

# 拉取
git pull origin main
```

**预期输出**：包含 `api.js`、`Layout.vue`、`test_csrf_relogin.py` 等变更文件。

### Step 5: 生产服务器 — 前端重新构建

```bash
cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/frontend

# 执行构建（源码已更新，需重新打包）
npm run build
```

**预期**：构建成功，`dist/` 目录更新，无 ERROR。若失败，**停止，不继续**。

### Step 6: 生产服务器 — 部署静态文件至 Nginx 目录

```bash
# 查看 nginx 静态文件目录
grep -r "root " /etc/nginx/sites-enabled/ 2>/dev/null || grep "root " /etc/nginx/nginx.conf

# 将构建产物复制到 nginx 服务目录（按实际路径调整 NGINX_STATIC）
NGINX_STATIC=/usr/share/nginx/html   # 请按实际 nginx.conf 调整
sudo cp -r dist/* ${NGINX_STATIC}/

# 验证
ls -la ${NGINX_STATIC}/index.html
```

### Step 7: 后端服务验证（无需重启）

```bash
# 本次仅修改前端，后端服务无需重启
systemctl is-active freeark-web.service
# 预期: active

# 健康检查
curl -s http://localhost/api/health/
# 预期: {"status": "ok"}
```

---

## 5. 部署后端到端验证

部署完成后，在浏览器中手工执行：

```
1. 访问 http://192.168.31.51（或外网地址）
2. 登录（用户名/密码）→ 确认登录成功
3. 点击「退出登录」
   - 打开 DevTools Network 面板
   - 确认 /api/auth/logout/ POST 请求返回 200
   - 打开 DevTools Application > Cookies
   - 确认 csrftoken cookie 已清除
4. 再次登录 → 确认无 CSRF 错误，跳转至首页
5. 执行一个 POST 操作（如访问需要 POST 的功能）→ 确认正常
```

---

## 6. 回滚计划

若部署后出现问题，执行以下步骤：

```bash
# Step R1: 在开发机 revert 本次提交
git revert HEAD --no-edit
git push origin main

# Step R2: 生产服务器 git pull
plink -ssh pi@192.168.31.51 -batch "cd /home/pi/freeark-prod && git pull origin main"

# Step R3: 重新构建前端（如需）
# （本地执行 npm run build，再 commit dist/ 产物，push）

# Step R4: 验证回滚成功
curl -s http://192.168.31.51/api/health/
```

**回滚时间预估**: < 5 分钟

**无需 DB 回滚**（本次无 migration）。

---

## 7. 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| `npm run build` 失败 | 低 | 中 | 本地先测试构建，失败则排查依赖 |
| git pull 冲突 | 极低 | 低 | 生产服务器只做 pull，不直接修改文件 |
| Nginx 缓存旧静态文件 | 低 | 低 | 浏览器强制刷新（Ctrl+Shift+R）可绕过；Nginx 不缓存动态资产 |
| dist/ 未在 git 追踪中 | 需确认 | 中 | 确认 .gitignore 配置，必要时添加 dist/ 到追踪 |

---

## 8. 等待授权

**本部署计划当前状态：DRAFT**

生产部署（Step 4 的 `git pull`）需等待用户明确 CONFIRM 信号，PM 收到确认后方可执行 Step 4-6。
