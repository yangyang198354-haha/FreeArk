/**
 * FreeArk Skill — Tier-2 写操作 Tool 实现（5 个 function）
 *
 * Tier-2 特性（来自 CONFIRM-2, CONFIRM-3）：
 *   - 所有写操作端点均纳入，均需二次确认
 *   - 代码级门控：confirmed !== true 时立即返回 CONFIRMATION_REQUIRED，不发出任何 HTTP 请求
 *   - 此门控独立于 Agent system prompt 规则，提供硬性拦截
 *   - 接收 chat_user 参数，用于 operator 字段追溯（CONFIRM-7）
 *   - 超时 8000ms（client.js 控制，含 MQTT 等待时间）
 *
 * 安全模型（来自 ARCH-LOBSTER-001 §5 纵深防御）：
 *   层 1 — Agent system prompt 规则（软性）
 *   层 2 — 本文件 confirmed 参数检查（硬性，代码级）
 *   层 3 — DRF IsAuthenticated（网络级）
 *   层 4 — FreeArk 现有写操作防护（业务级）
 *   层 5 — PLCWriteRecord 审计日志
 *
 * 文档引用: DECISIONS-LOBSTER-001 CONFIRM-2/CONFIRM-3/CONFIRM-7, MOD-SK-01
 */

'use strict';

const client = require('../client');

/**
 * 确认门控检查
 * 若 confirmed !== true，返回 CONFIRMATION_REQUIRED 响应（不发 HTTP）
 *
 * @param {boolean} confirmed - 来自 tool 调用参数
 * @param {object} preview - 操作摘要对象
 * @returns {object|null} 若需要确认则返回拒绝响应，否则返回 null（继续执行）
 */
function requireConfirmation(confirmed, preview) {
  if (confirmed !== true) {
    return {
      ok: false,
      status: 'CONFIRMATION_REQUIRED',
      message: '此操作属于 Tier-2 写操作，必须先向用户展示操作摘要并获得明确确认。'
        + '请在对话中输出以下摘要，等待用户输入「确认」后，再以 confirmed=true 重新调用此工具。'
        + '在用户确认之前，绝不发出实际的 API 请求。',
      preview,
      instruction_for_agent: '向用户展示 preview 中的操作摘要，格式：'
        + '"准备执行：[操作]。目标：[设备/服务]。参数：[变更详情]。'
        + '输入「确认」继续，输入「取消」放弃。"'
        + '只有收到用户明确的「确认」后，才以 confirmed=true 重新调用。',
    };
  }
  return null; // confirmed=true，允许继续
}

/**
 * 构建 operator 字符串（CONFIRM-7）
 * @param {string} chat_user - 当前对话用户名
 * @returns {string} 格式 "openclaw-agent::<chat_user>"
 */
function buildOperator(chat_user) {
  const safeUser = (chat_user || 'unknown').replace(/[^a-zA-Z0-9_@.-]/g, '_').substring(0, 50);
  return `openclaw-agent::${safeUser}`;
}

// ─────────────────────────────────────────────────────────────────
// Tool 1: freeark_write_device_params
// POST /api/device-settings/write/
// 风险：CRITICAL — 直接下发 PLC 写命令（经 MQTT 路由到三恒设备）
// ─────────────────────────────────────────────────────────────────
/**
 * 修改设备参数（三恒系统温控参数下发）
 *
 * @param {object} args
 * @param {string} args.specific_part - 设备标识符，如 "3-1-7-702"
 * @param {Array<{param_name: string, new_value: string|number}>} args.items - 参数变更列表
 * @param {string} [args.chat_user] - 当前对话用户名（用于 operator 追溯）
 * @param {boolean} [args.confirmed] - 必须为 true 才执行写操作
 * @returns {Promise<object>}
 */
async function freeark_write_device_params({ specific_part, items, chat_user, confirmed }) {
  if (!specific_part) return { ok: false, error: '缺少 specific_part 参数', status: 400 };
  if (!items || !Array.isArray(items) || items.length === 0) {
    return { ok: false, error: '缺少 items 参数（要修改的参数列表）', status: 400 };
  }

  // 构建操作预览
  const preview = {
    operation: '修改三恒设备参数',
    target_device: specific_part,
    changes: items.map(i => ({ param_name: i.param_name, new_value: i.new_value })),
    warning: '此操作将通过 MQTT 直接下发到硬件设备，请确认参数正确后再执行',
  };

  // 二次确认门控（硬性拦截）
  const blocked = requireConfirmation(confirmed, preview);
  if (blocked) return blocked;

  const operator = buildOperator(chat_user);

  // 发起 HTTP 请求（已确认）
  const body = {
    specific_part,
    items: items.map(i => ({ param_name: i.param_name, new_value: String(i.new_value) })),
    operator_override: operator, // CONFIRM-7: 追溯 chatuser（views 层需支持此字段）
  };

  const result = await client.post('/api/device-settings/write/', body);
  if (!result.ok) return { ok: false, error: result.error, status: result.status };

  return {
    ok: true,
    data: result.data,
    summary: `设备 ${specific_part} 参数写操作已下发，batch_request_id=${result.data.batch_request_id}，`
      + `共 ${result.data.item_count} 项，operator=${operator}，状态=pending（设备响应需 10-30 秒）`,
  };
}

// ─────────────────────────────────────────────────────────────────
// Tool 2: freeark_service_action
// POST /api/services/<name>/action/
// 风险：CRITICAL — 可停止/重启生产服务
// ─────────────────────────────────────────────────────────────────
/**
 * 执行系统服务操作（start/stop/restart）
 *
 * @param {object} args
 * @param {string} args.service_name - 服务名，如 "freeark-backend"、"freeark-mqtt-consumer"
 * @param {string} args.action - "start" | "stop" | "restart"
 * @param {string} [args.chat_user] - 当前对话用户名
 * @param {boolean} [args.confirmed] - 必须为 true 才执行
 * @returns {Promise<object>}
 */
async function freeark_service_action({ service_name, action, chat_user, confirmed }) {
  if (!service_name) return { ok: false, error: '缺少 service_name 参数', status: 400 };
  if (!['start', 'stop', 'restart'].includes(action)) {
    return { ok: false, error: 'action 必须为 start、stop 或 restart', status: 400 };
  }

  const preview = {
    operation: `系统服务操作：${action}`,
    target_service: service_name,
    action,
    warning: action === 'stop'
      ? `停止 ${service_name} 将中断相关功能，请确认业务影响`
      : `${action} ${service_name} 将导致服务短暂中断`,
  };

  const blocked = requireConfirmation(confirmed, preview);
  if (blocked) return blocked;

  const operator = buildOperator(chat_user);
  const body = { action, operator };

  const result = await client.post(`/api/services/${encodeURIComponent(service_name)}/action/`, body);
  if (!result.ok) return { ok: false, error: result.error, status: result.status };

  return {
    ok: true,
    data: result.data,
    summary: `服务 ${service_name} 执行 ${action} 成功，operator=${operator}`,
  };
}

// ─────────────────────────────────────────────────────────────────
// Tool 3: freeark_trigger_refresh
// POST /api/devices/ondemand-refresh/
// 风险：MEDIUM — 触发边缘任务，无硬件风险
// ─────────────────────────────────────────────────────────────────
/**
 * 触发设备按需数据采集
 *
 * @param {object} args
 * @param {string} args.specific_part - 设备标识符
 * @param {string} [args.chat_user] - 当前对话用户名
 * @param {boolean} [args.confirmed] - 必须为 true 才执行
 * @returns {Promise<object>}
 */
async function freeark_trigger_refresh({ specific_part, chat_user, confirmed }) {
  if (!specific_part) return { ok: false, error: '缺少 specific_part 参数', status: 400 };

  const preview = {
    operation: '触发设备按需数据采集',
    target_device: specific_part,
    warning: '将触发一次立即数据采集，通常在 5-10 秒内完成',
  };

  const blocked = requireConfirmation(confirmed, preview);
  if (blocked) return blocked;

  const operator = buildOperator(chat_user);
  const result = await client.post('/api/devices/ondemand-refresh/', { specific_part, operator });
  if (!result.ok) return { ok: false, error: result.error, status: result.status };

  return {
    ok: true,
    data: result.data,
    summary: `设备 ${specific_part} 按需采集任务已触发，operator=${operator}`,
  };
}

// ─────────────────────────────────────────────────────────────────
// Tool 4: freeark_batch_sync_device_tree
// POST /api/device-management/screen-device-tree/batch-sync/
// 风险：MEDIUM — 批量同步，影响范围较大
// ─────────────────────────────────────────────────────────────────
/**
 * 批量同步屏幕设备树
 *
 * @param {object} args
 * @param {string} [args.chat_user] - 当前对话用户名
 * @param {boolean} [args.confirmed] - 必须为 true 才执行
 * @param {object} [args.extra_params] - 传递给 API 的额外参数（可选）
 * @returns {Promise<object>}
 */
async function freeark_batch_sync_device_tree({ chat_user, confirmed, extra_params } = {}) {
  const preview = {
    operation: '批量同步屏幕设备树',
    scope: '全量批量同步',
    warning: '此操作影响范围较大，将同步所有屏幕设备树数据，请确认时机合适',
  };

  const blocked = requireConfirmation(confirmed, preview);
  if (blocked) return blocked;

  const operator = buildOperator(chat_user);
  const body = { operator, ...(extra_params || {}) };

  const result = await client.post('/api/device-management/screen-device-tree/batch-sync/', body);
  if (!result.ok) return { ok: false, error: result.error, status: result.status };

  return {
    ok: true,
    data: result.data,
    summary: `批量设备树同步任务已提交，operator=${operator}`,
  };
}

// ─────────────────────────────────────────────────────────────────
// Tool 5: freeark_sync_device_tree
// POST /api/device-management/screen-device-tree/sync/
// 风险：MEDIUM — 单户同步（保守纳入 Tier-2）
// ─────────────────────────────────────────────────────────────────
/**
 * 同步单户屏幕设备树
 *
 * @param {object} args
 * @param {string} [args.owner_id] - 业主 ID（可选，不填则全量）
 * @param {string} [args.chat_user] - 当前对话用户名
 * @param {boolean} [args.confirmed] - 必须为 true 才执行
 * @returns {Promise<object>}
 */
async function freeark_sync_device_tree({ owner_id, chat_user, confirmed } = {}) {
  const preview = {
    operation: '同步屏幕设备树',
    target: owner_id ? `业主 ID=${owner_id}` : '全量同步',
    warning: '将触发设备树同步操作',
  };

  const blocked = requireConfirmation(confirmed, preview);
  if (blocked) return blocked;

  const operator = buildOperator(chat_user);
  const body = { operator };
  if (owner_id) body.owner_id = owner_id;

  const result = await client.post('/api/device-management/screen-device-tree/sync/', body);
  if (!result.ok) return { ok: false, error: result.error, status: result.status };

  return {
    ok: true,
    data: result.data,
    summary: `设备树同步任务已提交，operator=${operator}`,
  };
}

// ─────────────────────────────────────────────────────────────────
// 导出
// ─────────────────────────────────────────────────────────────────
module.exports = {
  freeark_write_device_params,
  freeark_service_action,
  freeark_trigger_refresh,
  freeark_batch_sync_device_tree,
  freeark_sync_device_tree,
};
