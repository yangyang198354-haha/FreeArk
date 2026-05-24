/**
 * FreeArk Skill — 入口文件
 *
 * OpenClaw Skill 注册入口。遵循 OpenClaw 2026.5.20 的 Skill API 规范。
 *
 * 职责：
 *   1. 读取环境配置，执行启动校验
 *   2. 注册全部 Tier-1（14 个只读）+ Tier-2（5 个写操作）tool function
 *   3. 对外 export 符合 OpenClaw Skill 框架要求的 module.exports 结构
 *
 * 安全要点：
 *   - FREEARK_AGENT_TOKEN 从 process.env 读取，不硬编码
 *   - Token 在日志中仅输出前 8 字符
 *   - 所有 Tier-2 tool 内部有硬性 confirmed 门控，与 Agent 规则双重保险
 *
 * 使用（OpenClaw openclaw.json 配置）：
 *   {
 *     "skills": {
 *       "freeark-skill": {
 *         "path": "/home/yangyang/Freeark/FreeArk/agents/freeark-skill/index.js",
 *         "env": {
 *           "FREEARK_API_BASE": "http://127.0.0.1:8000",
 *           "FREEARK_AGENT_TOKEN": "<从 Django admin 生成的 agent token>"
 *         }
 *       }
 *     }
 *   }
 *
 * 文档引用: ARCH-LOBSTER-001 §4.1, DECISIONS-LOBSTER-001 CONFIRM-1/CONFIRM-8
 */

'use strict';

const { logStartup } = require('./client');
const tier1 = require('./tools/tier1_readonly');
const tier2 = require('./tools/tier2_write');

// ─────────────────────────────────────────────────────────────────
// Tool Schema 定义
// OpenClaw 使用这些 schema 向 LLM 描述可用工具
// ─────────────────────────────────────────────────────────────────

const TOOL_SCHEMAS = [
  // ─── Tier-1 只读 Tools ───────────────────────────────────────
  {
    name: 'freeark_get_realtime_params',
    description: '[Tier-1 只读] 查询 FreeArk 设备的实时参数（温度、湿度、CO₂ 等传感器数据）。无需用户确认，可直接调用。',
    parameters: {
      type: 'object',
      properties: {
        specific_part: { type: 'string', description: '设备标识符，格式 "<楼>-<单元>-<房号前缀>-<设备ID>"，如 "3-1-7-702" 或 "9-1-31-3104"' },
      },
      required: ['specific_part'],
    },
  },
  {
    name: 'freeark_get_usage_daily',
    description: '[Tier-1 只读] 查询设备日用量数据，支持按 specific_part、energy_mode（制冷/制热）、日期范围过滤。无需用户确认。',
    parameters: {
      type: 'object',
      properties: {
        specific_part: { type: 'string', description: '设备标识符（可选，不填返回全量）' },
        energy_mode: { type: 'string', enum: ['制冷', '制热'], description: '供能模式（可选）' },
        start_date: { type: 'string', description: '开始日期 YYYY-MM-DD（可选）' },
        end_date: { type: 'string', description: '结束日期 YYYY-MM-DD（可选）' },
        page: { type: 'integer', description: '页码（可选，默认 1）' },
      },
      required: [],
    },
  },
  {
    name: 'freeark_get_usage_period',
    description: '[Tier-1 只读] 查询指定时间段内的汇总用量，适合"上周用了多少"、"本月截止今天"等场景。无需用户确认。',
    parameters: {
      type: 'object',
      properties: {
        specific_part: { type: 'string', description: '设备标识符（可选）' },
        energy_mode: { type: 'string', enum: ['制冷', '制热'], description: '供能模式（可选）' },
        start_time: { type: 'string', description: '开始时间 ISO8601（可选）' },
        end_time: { type: 'string', description: '结束时间 ISO8601（可选）' },
      },
      required: [],
    },
  },
  {
    name: 'freeark_get_usage_monthly',
    description: '[Tier-1 只读] 查询月度用量数据，适合月度报告和同比分析。无需用户确认。',
    parameters: {
      type: 'object',
      properties: {
        specific_part: { type: 'string', description: '设备标识符（可选）' },
        energy_mode: { type: 'string', enum: ['制冷', '制热'], description: '供能模式（可选）' },
        year_month: { type: 'string', description: '年月 YYYY-MM（可选）' },
      },
      required: [],
    },
  },
  {
    name: 'freeark_get_plc_status',
    description: '[Tier-1 只读] 查询 PLC 连接状态。不填 specific_part 返回所有 PLC 状态；填写则查询单台设备。无需用户确认。',
    parameters: {
      type: 'object',
      properties: {
        specific_part: { type: 'string', description: '设备标识符（可选，不填返回全量）' },
      },
      required: [],
    },
  },
  {
    name: 'freeark_get_plc_history',
    description: '[Tier-1 只读] 查询指定设备的 PLC 在线/离线状态变化历史，适合排查设备稳定性问题。无需用户确认。',
    parameters: {
      type: 'object',
      properties: {
        specific_part: { type: 'string', description: '设备标识符' },
      },
      required: ['specific_part'],
    },
  },
  {
    name: 'freeark_get_dashboard_summary',
    description: '[Tier-1 只读] 查询系统看板摘要（总能耗、PLC 在线率、屏幕在线率等汇总指标）。无需用户确认。',
    parameters: { type: 'object', properties: {}, required: [] },
  },
  {
    name: 'freeark_get_services_status',
    description: '[Tier-1 只读] 查询所有 FreeArk 后台服务的当前运行状态（看板视角）。无需用户确认。',
    parameters: { type: 'object', properties: {}, required: [] },
  },
  {
    name: 'freeark_get_power_status',
    description: '[Tier-1 只读] 查询系统供电状态。无需用户确认。',
    parameters: { type: 'object', properties: {}, required: [] },
  },
  {
    name: 'freeark_get_device_params',
    description: '[Tier-1 只读] 查询指定设备的可写参数列表及当前值，适合在执行写操作前先了解当前设定。无需用户确认。',
    parameters: {
      type: 'object',
      properties: {
        specific_part: { type: 'string', description: '设备标识符' },
      },
      required: ['specific_part'],
    },
  },
  {
    name: 'freeark_get_write_records',
    description: '[Tier-1 只读] 查询设备参数写操作历史记录，支持按 specific_part、operator、status、时间范围过滤。operator 含 "openclaw-agent" 前缀的记录为 Agent 操作。无需用户确认。',
    parameters: {
      type: 'object',
      properties: {
        specific_part: { type: 'string', description: '设备标识符（可选）' },
        operator: { type: 'string', description: '操作员（可选，如 "openclaw-agent"）' },
        status: { type: 'string', enum: ['pending', 'success', 'failed', 'timeout'], description: '状态过滤（可选）' },
        start_time: { type: 'string', description: '开始时间（可选）' },
        end_time: { type: 'string', description: '结束时间（可选）' },
      },
      required: [],
    },
  },
  {
    name: 'freeark_get_device_tree',
    description: '[Tier-1 只读] 查询指定业主 ID 的所有设备树（设备层级列表）。无需用户确认。',
    parameters: {
      type: 'object',
      properties: {
        owner_id: { type: ['integer', 'string'], description: '业主 ID（数字）' },
      },
      required: ['owner_id'],
    },
  },
  {
    name: 'freeark_get_service_detail',
    description: '[Tier-1 只读] 查询单个系统服务的详细状态，适合深入了解某个服务的运行情况。无需用户确认。',
    parameters: {
      type: 'object',
      properties: {
        service_name: { type: 'string', description: '服务名，如 "freeark-backend"、"freeark-mqtt-consumer"、"openclaw-gateway"' },
      },
      required: ['service_name'],
    },
  },
  {
    name: 'freeark_get_plc_latest',
    description: '[Tier-1 只读] 查询 PLC 最新数据（全量，所有采集到的最新参数值）。无需用户确认。',
    parameters: {
      type: 'object',
      properties: {
        specific_part: { type: 'string', description: '设备标识符（可选，不填返回全量）' },
      },
      required: [],
    },
  },

  // ─── Tier-2 写操作 Tools ──────────────────────────────────────
  {
    name: 'freeark_write_device_params',
    description: '[Tier-2 写操作 — 必须先获得用户确认] 修改三恒设备参数（如温控设定值）。调用此工具前，你必须先向用户展示操作摘要并等待用户输入「确认」。获得确认后，以 confirmed=true 重新调用。此操作将通过 MQTT 直接下发到硬件设备。',
    parameters: {
      type: 'object',
      properties: {
        specific_part: { type: 'string', description: '设备标识符，如 "3-1-7-702"' },
        items: {
          type: 'array',
          description: '参数变更列表',
          items: {
            type: 'object',
            properties: {
              param_name: { type: 'string', description: '参数名，如 "cooling_temp_setting"' },
              new_value: { description: '新值' },
            },
            required: ['param_name', 'new_value'],
          },
        },
        chat_user: { type: 'string', description: '当前对话用户名（从消息前缀 [__freeark_user__:<name>] 中提取）' },
        confirmed: { type: 'boolean', description: '必须为 true 才执行。用户未确认时不得传入 true。' },
      },
      required: ['specific_part', 'items'],
    },
  },
  {
    name: 'freeark_service_action',
    description: '[Tier-2 写操作 — 必须先获得用户确认] 对 FreeArk 后台服务执行 start/stop/restart 操作。调用前必须向用户展示操作摘要并等待确认。stop 操作将中断对应功能，请确保用户充分了解影响。',
    parameters: {
      type: 'object',
      properties: {
        service_name: { type: 'string', description: '服务名，如 "freeark-backend"、"freeark-mqtt-consumer"' },
        action: { type: 'string', enum: ['start', 'stop', 'restart'], description: '操作类型' },
        chat_user: { type: 'string', description: '当前对话用户名' },
        confirmed: { type: 'boolean', description: '必须为 true 才执行' },
      },
      required: ['service_name', 'action'],
    },
  },
  {
    name: 'freeark_trigger_refresh',
    description: '[Tier-2 写操作 — 必须先获得用户确认] 触发指定设备的按需数据采集（立即刷新一次数据）。需用户确认后执行。',
    parameters: {
      type: 'object',
      properties: {
        specific_part: { type: 'string', description: '设备标识符' },
        chat_user: { type: 'string', description: '当前对话用户名' },
        confirmed: { type: 'boolean', description: '必须为 true 才执行' },
      },
      required: ['specific_part'],
    },
  },
  {
    name: 'freeark_batch_sync_device_tree',
    description: '[Tier-2 写操作 — 必须先获得用户确认] 批量同步所有屏幕设备树，影响范围较大，需用户确认后执行。',
    parameters: {
      type: 'object',
      properties: {
        chat_user: { type: 'string', description: '当前对话用户名' },
        confirmed: { type: 'boolean', description: '必须为 true 才执行' },
      },
      required: [],
    },
  },
  {
    name: 'freeark_sync_device_tree',
    description: '[Tier-2 写操作 — 必须先获得用户确认] 同步单户屏幕设备树，需用户确认后执行。',
    parameters: {
      type: 'object',
      properties: {
        owner_id: { type: ['integer', 'string'], description: '业主 ID（可选）' },
        chat_user: { type: 'string', description: '当前对话用户名' },
        confirmed: { type: 'boolean', description: '必须为 true 才执行' },
      },
      required: [],
    },
  },
];

// ─────────────────────────────────────────────────────────────────
// Tool 实现映射
// ─────────────────────────────────────────────────────────────────

const TOOL_HANDLERS = {
  // Tier-1
  freeark_get_realtime_params: tier1.freeark_get_realtime_params,
  freeark_get_usage_daily: tier1.freeark_get_usage_daily,
  freeark_get_usage_period: tier1.freeark_get_usage_period,
  freeark_get_usage_monthly: tier1.freeark_get_usage_monthly,
  freeark_get_plc_status: tier1.freeark_get_plc_status,
  freeark_get_plc_history: tier1.freeark_get_plc_history,
  freeark_get_dashboard_summary: tier1.freeark_get_dashboard_summary,
  freeark_get_services_status: tier1.freeark_get_services_status,
  freeark_get_power_status: tier1.freeark_get_power_status,
  freeark_get_device_params: tier1.freeark_get_device_params,
  freeark_get_write_records: tier1.freeark_get_write_records,
  freeark_get_device_tree: tier1.freeark_get_device_tree,
  freeark_get_service_detail: tier1.freeark_get_service_detail,
  freeark_get_plc_latest: tier1.freeark_get_plc_latest,
  // Tier-2
  freeark_write_device_params: tier2.freeark_write_device_params,
  freeark_service_action: tier2.freeark_service_action,
  freeark_trigger_refresh: tier2.freeark_trigger_refresh,
  freeark_batch_sync_device_tree: tier2.freeark_batch_sync_device_tree,
  freeark_sync_device_tree: tier2.freeark_sync_device_tree,
};

// ─────────────────────────────────────────────────────────────────
// OpenClaw Skill 框架入口
// ─────────────────────────────────────────────────────────────────

/**
 * Skill 初始化：打印启动摘要，返回 Skill 描述
 */
function init() {
  logStartup();
  console.log(`[freeark-skill] 已注册 ${TOOL_SCHEMAS.length} 个 tool functions`);
  console.log(`[freeark-skill]   Tier-1 只读: ${Object.keys(tier1).length} 个`);
  console.log(`[freeark-skill]   Tier-2 写操作: ${Object.keys(tier2).length} 个（均需二次确认）`);
  return {
    name: 'freeark-skill',
    version: '1.0.0',
    description: 'FreeArk 系统 API 访问能力。Tier-1 只读工具可直接调用；Tier-2 写操作工具必须先获得用户明确确认。',
    tools: TOOL_SCHEMAS,
  };
}

/**
 * Tool 调用分发器
 * @param {string} toolName - tool function 名称
 * @param {object} args - tool 调用参数
 * @returns {Promise<object>}
 */
async function callTool(toolName, args) {
  const handler = TOOL_HANDLERS[toolName];
  if (!handler) {
    return {
      ok: false,
      error: `此操作超出 Agent 权限范围：工具 "${toolName}" 不在 FreeArk Skill 的注册列表中，拒绝执行。`,
      status: 0,
    };
  }

  try {
    return await handler(args || {});
  } catch (err) {
    console.error(`[freeark-skill] callTool "${toolName}" 异常: ${err.message}`);
    return {
      ok: false,
      error: `工具执行时发生内部错误（${err.message}），请稍后重试或联系管理员检查日志。`,
      status: 0,
    };
  }
}

module.exports = {
  init,
  callTool,
  TOOL_SCHEMAS,
  TOOL_HANDLERS,
};
