# 模块设计文档 v2 — 方舟龙虾 API 通道与知识增强

```
file_header:
  document_id: MOD-LOBSTER-002
  project: FreeArk — lobster-agent-api-channel
  version: 2.0.0
  status: APPROVED
  author_agent: system-architect (PM-orchestrated, SDLC 第二轮重设计)
  created_at: 2026-05-25
  supersedes: MOD-LOBSTER-001
  depends_on: ARCH-LOBSTER-002, REQ-SPEC-LOBSTER-002, PROBES-LOBSTER-001
  change_summary: >
    v1 → v2 变更：
    (1) MOD-SK-01 完全重写：Skill 入口从 index.js 改为 SKILL.md
    (2) CLI 执行体从 Node.js 改为 Python（推荐，待 ADR-005-PENDING-A 最终确认）
    (3) 新增 MOD-SK-02（SKILL.md 规范）
    (4) MOD-AG-01 更新 openclaw.json 字段（真实 schema）
    (5) MOD-BE-03 补充 Token 脱敏操作规范
    (6) 新增 MOD-PoC（PoC 最小验证模块设计）
    (7) 保留 MOD-BE-01、MOD-BE-02（已上线，不变）
  pending_items:
    - MOD-SK-01 CLI 协议细节标注 PENDING-A（等待 ADR-005-PENDING-A 解决）
    - MOD-SK-02 SKILL.md frontmatter 字段标注 PENDING-A（同上）
```

---

## 重要说明

以下标注 **[PENDING-A]** 的内容，依赖 ADR-005-PENDING-A 解决（即运行 PROBES-LOBSTER-001 §6 命令 D/E/F，
确认 bundled SKILL.md 格式和 CLI I/O 协议）。在 PENDING-A 解决前：
- 模块设计提供两种预设方案（独立进程 / 长驻进程），开发者在 PoC 时选择适用方案
- 开发不得在 PENDING-A 解决前启动（依赖 REQ-NFR-006 PoC 先行）

---

## MOD-SK-01（完全重写）：FreeArk Skill

**版本**：v2（v1 MOD-SK-01 完全废弃）

**位置**：`agents/freeark-skill/`（入仓库）

**职责**：
- 通过 SKILL.md 向 OpenClaw 声明 Agent 可调用的 FreeArk tool 列表
- CLI 执行体接收 OpenClaw 的调用参数，向 FreeArk REST API 发出 HTTP 请求
- 格式化响应，返回 Agent 易理解的结构化结果
- Tier-2 写操作：通过 SKILL.md 的 requires_confirmation 声明（若 schema 支持）配合 system prompt 规则双重保障

### 子模块一览

| 文件/目录 | 职责 | 状态 |
|----------|------|------|
| `SKILL.md` | Skill 主入口，OpenClaw 识别文件，声明所有 tool | 新建（见 MOD-SK-02） |
| `scripts/freeark_tool.py` | CLI 执行体统一入口（dispatch 到各 tool 函数） | 新建 |
| `scripts/tier1_readonly.py` | 14 个只读 tool 的 HTTP 调用实现 | 新建 |
| `scripts/tier2_write.py` | 5 个写操作 tool 的 HTTP 调用实现 | 新建 |
| `lib/freeark_client.py` | HTTP 客户端封装（统一 Token 头、超时、错误处理） | 新建 |
| `lib/formatters.py` | 响应格式化（API JSON → Agent 易理解摘要） | 新建 |
| `README.md` | 人类可读的 Skill 说明（非 OpenClaw 使用） | 新建 |

### CLI 执行体接口规范 [PENDING-A]

**预设方案 A：独立进程模式（每次 tool_call 启动新进程）**

适用场景：OpenClaw 每次 tool_call 时以子进程方式启动 CLI，stdin 传入参数，stdout 返回结果，进程完成后退出。

```python
# scripts/freeark_tool.py 接口（预设方案 A）
#!/usr/bin/env python3
"""
FreeArk Skill CLI 执行体（方案 A：独立进程模式）

输入（stdin 或 CLI args，取决于 [PENDING-A] 实测结果）：
  JSON: {"tool": "freeark_get_realtime_params", "params": {"specific_part": "3-1-702-702"}}

输出（stdout）：
  JSON: {"success": true, "data": {...}, "summary": "中文摘要，Agent 可直接引用"}
  JSON: {"success": false, "error": "错误描述（中文）", "http_status": 404}

退出码：
  0 — 正常（success=true 或可恢复的业务错误）
  1 — CLI 本身错误（参数不合法、环境变量缺失）
"""
import sys, json, os
from tier1_readonly import TIER1_HANDLERS
from tier2_write import TIER2_HANDLERS

def main():
    # 从 stdin 或 argv 读取参数（[PENDING-A]：取决于 OpenClaw CLI 协议）
    # 预设：从 stdin 读 JSON
    raw = sys.stdin.read().strip()
    if not raw:
        # 备选：从 argv 读（某些 OpenClaw 版本可能以 --json='{...}' 传参）
        if len(sys.argv) > 1:
            raw = sys.argv[1]
        else:
            print(json.dumps({"success": False, "error": "无输入参数"}))
            sys.exit(1)
    
    call = json.loads(raw)
    tool_name = call.get("tool")
    params = call.get("params", {})
    
    handlers = {**TIER1_HANDLERS, **TIER2_HANDLERS}
    if tool_name not in handlers:
        print(json.dumps({"success": False, "error": f"未知 tool: {tool_name}"}))
        sys.exit(1)
    
    result = handlers[tool_name](params)
    print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    main()
```

**预设方案 B：长驻进程模式（stdin/stdout 多轮通信）**

适用场景：OpenClaw 启动一个长驻 CLI 进程，每次 tool_call 向 stdin 写一行 JSON，CLI 从 stdout 返回一行 JSON，进程持续运行直到 Gateway 重启。

```python
# scripts/freeark_tool.py 接口（预设方案 B）
#!/usr/bin/env python3
"""FreeArk Skill CLI 执行体（方案 B：长驻进程模式）"""
import sys, json
from tier1_readonly import TIER1_HANDLERS
from tier2_write import TIER2_HANDLERS

HANDLERS = {**TIER1_HANDLERS, **TIER2_HANDLERS}

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        call = json.loads(line)
        tool_name = call.get("tool")
        params = call.get("params", {})
        result = HANDLERS[tool_name](params) if tool_name in HANDLERS else \
                 {"success": False, "error": f"未知 tool: {tool_name}"}
    except Exception as e:
        result = {"success": False, "error": str(e)}
    print(json.dumps(result, ensure_ascii=False), flush=True)
```

**[PENDING-A]**：PoC 阶段实测后选定方案 A 或 B，删除未采用的方案，更新本文档。

### HTTP 客户端规范（lib/freeark_client.py）

```python
# lib/freeark_client.py — 接口规范（实现细节略，开发阶段补充）
import os, requests

FREEARK_BASE = os.environ.get("FREEARK_API_BASE", "http://127.0.0.1:8000")
FREEARK_TOKEN = os.environ.get("FREEARK_AGENT_TOKEN")  # [PENDING-A]：变量名待 ADR-005a 确认

class FreeArkClient:
    """统一 HTTP 客户端，强制 loopback 地址 + Token 鉴权"""
    
    def __init__(self):
        if not FREEARK_TOKEN:
            raise RuntimeError("FREEARK_AGENT_TOKEN 环境变量未设置")
        # 硬检查：只允许调用 127.0.0.1:8000（防 SSRF）
        if "127.0.0.1:8000" not in FREEARK_BASE:
            raise RuntimeError(f"非法 API 地址：{FREEARK_BASE}")
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Token {FREEARK_TOKEN}",
            "Content-Type": "application/json",
        })
    
    def get(self, path: str, params: dict = None, timeout: int = 5) -> dict:
        """Tier-1 只读请求，超时 5 秒"""
        resp = self._session.get(f"{FREEARK_BASE}{path}", params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    
    def post(self, path: str, data: dict, timeout: int = 8) -> dict:
        """Tier-2 写操作请求，超时 8 秒（含 MQTT ACK 等待）"""
        resp = self._session.post(f"{FREEARK_BASE}{path}", json=data, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    
    def log_token_hint(self) -> str:
        """安全日志：仅返回 Token 前 8 字符"""
        return FREEARK_TOKEN[:8] + "..." if FREEARK_TOKEN else "NOT_SET"
```

**关键约束**：
- `FREEARK_AGENT_TOKEN` 从环境变量读取，不硬编码，不在日志中打印完整值
- HTTP 目标地址仅允许 `127.0.0.1:8000`（hardcheck，防 SSRF）
- Tier-1 超时 5 秒，Tier-2 超时 8 秒（MQTT ACK 等待）

---

## MOD-SK-02（新增）：SKILL.md 规范

**位置**：`agents/freeark-skill/SKILL.md`

**职责**：OpenClaw 识别此文件，读取 Skill 的能力声明、tool 列表、exec 命令，
决定 Agent 何时触发此 Skill 以及如何调用 CLI。

### SKILL.md 结构预设（[PENDING-A]：字段名待实测确认）

以下为基于 PROBES-LOBSTER-001 §3 推断的预设格式，实际格式以 bundled SKILL.md 示例为准。
**开发时必须用 bundled 示例格式覆盖此预设。**

```markdown
---
name: freeark-skill
version: 2.0.0
description: |
  方舟龙虾专用 API 工具集。通过此 Skill，你可以查询 FreeArk 系统的设备状态、
  能耗数据、PLC 参数，以及执行受控的设备参数下发操作。
  所有数据来自树莓派本地的 FreeArk REST API（http://127.0.0.1:8000）。

# [PENDING-A]: exec 字段的精确语法取决于 bundled SKILL.md 示例的格式
# 预设方案 A（独立进程模式）：
exec: python3 /home/yangyang/Freeark/FreeArk/agents/freeark-skill/scripts/freeark_tool.py

# 预设方案 B（长驻进程模式，若 OpenClaw 支持）：
# exec_persistent: python3 /home/yangyang/Freeark/FreeArk/agents/freeark-skill/scripts/freeark_tool.py

# [PENDING-A]: env 字段（Token 注入）的精确语法待 ADR-005a 确认
# 若 openclaw.json 的 secrets 段注入，此处可能不需要显式声明
# 预设：
env:
  FREEARK_API_BASE: "http://127.0.0.1:8000"
  # FREEARK_AGENT_TOKEN: 从 openclaw.json secrets 或 skill env 注入，不在 SKILL.md 硬编码

tools:
  # Tier-1 只读 tools（Agent 可直接调用，无需用户确认）
  - name: freeark_get_realtime_params
    description: "查询指定设备的实时传感器参数（温度、湿度、CO₂浓度、风量等）。specific_part 格式：<楼>-<单元>-<房号前缀>-<设备ID>，例如 9-1-31-3104"
    parameters:
      type: object
      properties:
        specific_part:
          type: string
          description: "设备 ID，格式 <楼>-<单元>-<房号前缀>-<设备ID>"
      required: [specific_part]

  - name: freeark_get_usage_daily
    description: "查询指定设备的日用量数据，支持分页和时间过滤"
    parameters:
      type: object
      properties:
        specific_part: {type: string}
        energy_mode: {type: string, description: "能耗模式：制冷/制热/除湿/新风"}
        start_time: {type: string, description: "ISO 8601 格式"}
        end_time: {type: string, description: "ISO 8601 格式"}
      required: [specific_part]

  - name: freeark_get_usage_period
    description: "查询指定设备某时间段的用量汇总"
    parameters:
      type: object
      properties:
        specific_part: {type: string}
        energy_mode: {type: string}
        start_time: {type: string}
        end_time: {type: string}
      required: [specific_part, start_time, end_time]

  - name: freeark_get_usage_monthly
    description: "查询指定设备的月度用量数据"
    parameters:
      type: object
      properties:
        specific_part: {type: string}
        energy_mode: {type: string}
        month: {type: string, description: "格式 YYYY-MM"}
      required: [specific_part]

  - name: freeark_get_plc_status
    description: "查询所有或指定 PLC 的连接状态（在线/离线）"
    parameters:
      type: object
      properties:
        specific_part: {type: string, description: "可选，不填则返回全量"}

  - name: freeark_get_dashboard_summary
    description: "获取系统仪表盘摘要数据（总能耗、在线率等）"
    parameters:
      type: object
      properties: {}

  - name: freeark_get_services_status
    description: "获取 FreeArk 系统各服务的运行状态"
    parameters:
      type: object
      properties: {}

  - name: freeark_get_power_status
    description: "获取各区域的供电状态"
    parameters:
      type: object
      properties: {}

  - name: freeark_get_device_params
    description: "查询指定设备的可写参数列表（含当前值）"
    parameters:
      type: object
      properties:
        specific_part: {type: string}
      required: [specific_part]

  - name: freeark_get_write_records
    description: "查询写操作历史记录，可按设备和时间范围过滤"
    parameters:
      type: object
      properties:
        specific_part: {type: string, description: "可选"}
        start_time: {type: string, description: "可选"}
        end_time: {type: string, description: "可选"}

  - name: freeark_get_device_tree
    description: "获取指定业主的设备树（所有下属设备列表）"
    parameters:
      type: object
      properties:
        owner_id: {type: integer}
      required: [owner_id]

  - name: freeark_get_service_detail
    description: "获取单个系统服务的详细状态信息"
    parameters:
      type: object
      properties:
        service_name: {type: string, description: "systemd 服务名，如 freeark-backend"}
      required: [service_name]

  - name: freeark_get_plc_latest
    description: "获取所有 PLC 的最新参数（全量快照）"
    parameters:
      type: object
      properties: {}

  - name: freeark_get_dashboard_trend
    description: "获取系统趋势数据（用于图表展示）"
    parameters:
      type: object
      properties: {}

  # Tier-2 写操作 tools（必须经 Agent 展示操作摘要 + 用户确认才可调用）
  - name: freeark_write_device_params
    description: |
      [Tier-2 写操作，调用前必须在对话中展示操作摘要并等待用户输入"确认"]
      下发 PLC 设备参数写命令（经 MQTT 路由到硬件）。
      仅允许 WRITABLE_SUFFIXES 白名单内的参数（_temp_setting/_switch/_mode）。
    # [PENDING-A]: requires_confirmation 字段是否支持，取决于 bundled 示例
    # requires_confirmation: true
    parameters:
      type: object
      properties:
        specific_part: {type: string}
        items:
          type: array
          items:
            type: object
            properties:
              param_name: {type: string}
              value: {}
        operator_override:
          type: string
          description: "格式 openclaw-agent::<chatuser>，由 ChatConsumer 前缀注入提取"
      required: [specific_part, items]

  - name: freeark_trigger_refresh
    description: |
      [Tier-2 写操作，需用户确认]
      触发指定设备的按需数据采集刷新。
    parameters:
      type: object
      properties:
        specific_part: {type: string}
      required: [specific_part]

  - name: freeark_service_action
    description: |
      [Tier-2 写操作，需用户确认，高危]
      对 FreeArk 系统服务执行管理操作（start/stop/restart）。
      注意：stop 操作会中断对应服务功能。
    parameters:
      type: object
      properties:
        service_name: {type: string}
        action:
          type: string
          enum: [start, stop, restart]
      required: [service_name, action]

  - name: freeark_sync_device_tree
    description: |
      [Tier-2 写操作，需用户确认]
      触发单户设备树同步操作。
    parameters:
      type: object
      properties:
        specific_part: {type: string}
      required: [specific_part]

  - name: freeark_batch_sync_device_tree
    description: |
      [Tier-2 写操作，需用户确认]
      批量设备树同步操作（影响范围广，请谨慎使用）。
    parameters:
      type: object
      properties:
        owner_ids:
          type: array
          items: {type: integer}
      required: [owner_ids]
---

# FreeArk Skill

方舟龙虾专用工具集，提供对 FreeArk 三恒系统管理平台的 API 访问能力。

## 使用说明

- **Tier-1 只读 tools**：可直接调用，无需用户确认。查询类操作不会修改任何数据。
- **Tier-2 写操作 tools**：调用前必须向用户展示操作摘要，等待用户输入「确认」后方可执行。
  格式示例：
  > 准备执行：修改 9-1-31-3104 的 cooling_temp_setting → 26°C。
  > 目标设备：3104 室空调。
  > 输入「确认」继续，输入「取消」放弃。

## 版本信息

- 版本：2.0.0
- 适用：FreeArk v0.5.9+，OpenClaw 2026.5.20
- 作者：SDLC 第二轮 system-architect
```

**[PENDING-A] 关键提示**：
以上 SKILL.md 中的 YAML frontmatter 字段名（`exec`, `env`, `tools`, `parameters`, `requires_confirmation` 等）
均为推断值，必须与 bundled SKILL.md 示例（PROBES-LOBSTER-001 §6 命令 D/E/F 的输出）对比校正后才能使用。
字段名不匹配将导致与第一轮相同的 "Invalid config" 错误。

---

## MOD-AG-01（更新）：方舟龙虾 Agent 配置

**位置**：`~/.openclaw/openclaw.json`（Pi 本地，不入仓库）；system prompt 源文件入仓库

**v2 变更内容**（基于 PROBES-LOBSTER-001 真实 schema）：

```json
{
  "agent": {
    "main": {
      "name": "方舟龙虾",
      "systemPrompt": "<从仓库 docs/sdlc/lobster-agent-api-channel/agent_system_prompt_v2.md 读取>",
      "skills": ["freeark-skill"]
    }
  },
  "skills": {
    "allowBundled": [],
    "load": {
      "extraDirs": ["/home/yangyang/Freeark/FreeArk/agents"],
      "watch": false
    }
  }
}
```

**注**：
- `skills.load.extraDirs` 设置为 `agents/` 目录（freeark-skill 的父目录），不是 `agents/freeark-skill/` 本身
- `watch: false` 在生产环境禁用文件监视（生产不需要热重载，减少资源消耗）
- `agent.main.skills` 字段格式（字符串数组）需实测确认（PROBES-LOBSTER-001 §8）
- `allowBundled: []` 不启用 bundled skill，避免加载不必要的 Skill

**system prompt 版本化**：
- 仓库路径：`docs/sdlc/lobster-agent-api-channel/agent_system_prompt_v2.md`
- v2 相比 v1：§4 "API 调用规则"段更新为匹配 SKILL.md 抽象；其余 §1-§3/§5 基本复用

---

## MOD-BE-01（已上线，不变）：ChatConsumer chatuser 前缀注入

**位置**：`FreeArkWeb/backend/freearkweb/api/consumers.py`

**状态**：DEPLOYED — `[__freeark_user__:<username>]` 前缀已上线。**本模块 v2 不变更。**

CLI 执行体（MOD-SK-01）在处理 Tier-2 写操作时，从 Agent 转发的参数中提取 chatuser：
- Agent 通过 system prompt 规则，将 message 开头的 `[__freeark_user__:<username>]` 前缀提取为 chatuser
- CLI 执行体在 `freeark_write_device_params` 函数中将 `operator_override` 设置为 `openclaw-agent::<chatuser>`
- FreeArk views 层的 `operator_override` 字段已支持此格式（已上线）

---

## MOD-BE-02（已上线，不变）：operator_override 字段与 effective_operator 落库

**位置**：`api/serializers_device_settings.py`, `api/views_device_settings.py`

**状态**：DEPLOYED。**本模块 v2 不变更。**

---

## MOD-BE-03（补充）：Agent 服务账号 Token 管理

**位置**：FreeArk 数据库（Django CustomUser 表），Token 明文仅存 Pi 本地 openclaw.json

**状态**：服务账号已建（DB id=8），Token 明文已销毁（部署报告 §3.2）。

**v2 新增操作规范（REQ-NFR-007 落地）**：

Token 重新生成的标准操作流程：
```bash
SSH="ssh -o BatchMode=yes -o UserKnownHostsFile=/c/fa-home/.ssh/known_hosts \
     -i /c/fa-home/.ssh/id_ed25519 -p 57279 -o ConnectTimeout=20 \
     yangyang@et116374mm892.vicp.fun"

# 重新生成 Token（必须全文脱敏）
$SSH '/home/yangyang/Freeark/FreeArk/venv/bin/python \
  /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb/manage.py \
  create_openclaw_agent_user --force-regenerate-token 2>&1 \
  | sed -E "s/[a-f0-9]{40}/[REDACTED-40HEX]/g"'

# 将新 Token（明文）存入 Pi 临时文件（以便后续写入 openclaw.json）
# 注意：此步需单独运行不带脱敏的命令并将输出仅写入 Pi 本地文件，不传到 Claude 上下文
$SSH 'PLAIN_TOKEN=$(/home/yangyang/Freeark/FreeArk/venv/bin/python \
  /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb/manage.py \
  create_openclaw_agent_user --force-regenerate-token --output-token-only 2>/dev/null); \
  echo "$PLAIN_TOKEN" > /tmp/.fa_token && chmod 600 /tmp/.fa_token && \
  echo "Token stored in /tmp/.fa_token ($(wc -c < /tmp/.fa_token) chars, DO NOT PRINT)"'
```

**约束**：
- Token 明文不得出现在 Claude 对话上下文（所有控制台输出必须经脱敏管道）
- Token 用完后立即从 /tmp 清除：`rm -f /tmp/.fa_token`

---

## MOD-PoC（新增）：最小可行 Skill（PoC 里程碑）

**职责**：实现仅 1 个 tool（`freeark_get_realtime_params`）的最小 Skill，
验证 SKILL.md 格式和 CLI 调用协议，作为扩展到 19 个 tool 的前置门控。

**文件列表（PoC 阶段）**：

| 文件 | 内容 |
|------|------|
| `agents/freeark-skill/SKILL.md` | 仅含 1 个 tool：freeark_get_realtime_params |
| `agents/freeark-skill/scripts/freeark_tool_poc.py` | 仅实现 get_realtime_params，硬编码 PoC 逻辑 |

**PoC 验收标准**（见 ARCH-LOBSTER-002 §9.4）：
1. Gateway 启动无 "Invalid config" 错误
2. `openclaw skills list` 可见 freeark-skill
3. Agent 对话中实际触发 freeark_get_realtime_params，返回真实 FreeArk 数据
4. PoC PASS 记录写入 code_review_report_v2.md

---

## 不变模块汇总

以下 v1 模块在 v2 中**不变更**：

| 模块 | 位置 | v2 状态 |
|------|------|---------|
| MOD-BE-01 (ChatConsumer 前缀) | `api/consumers.py` | DEPLOYED，不改 |
| MOD-BE-02 (operator_override) | `api/serializers/views_device_settings.py` | DEPLOYED，不改 |
| OpenClawAdapter | `api/openclaw_adapter.py` | 不变 |
| FreeArk REST API 端点 | `api/views*.py`, `api/urls.py` | 不变 |
| Nginx 配置 | `/etc/nginx/sites-enabled/freeark` | 不变 |
| OpenClaw Control UI 反代 | `/etc/nginx/sites-enabled/freeark-openclaw` | 不变 |
