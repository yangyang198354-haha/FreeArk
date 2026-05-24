/**
 * FreeArk Skill — Tier-1 只读 Tool 实现（14 个 function）
 *
 * Tier-1 特性：
 *   - 只读 GET 操作，Agent 可自主调用，无需用户确认
 *   - 超时 5000ms（client.js 控制）
 *   - 返回格式化的 JSON 摘要，对 Agent 友好
 *
 * 文档引用: ARCH-LOBSTER-001 §附录 API 端点映射, MOD-SK-01, CONFIRM-2
 */

'use strict';

const client = require('../client');

/**
 * 统一结果封装：OK 路径
 */
function ok(data, summary = null) {
  return { ok: true, data, summary };
}

/**
 * 统一结果封装：错误路径
 */
function fail(error, status = 0) {
  return { ok: false, error, status };
}

// ─────────────────────────────────────────────────────────────────
// Tool 1: freeark_get_realtime_params
// GET /api/devices/realtime-params/
// ─────────────────────────────────────────────────────────────────
/**
 * 查询设备实时参数
 * @param {object} args
 * @param {string} args.specific_part - 设备标识符，格式 "楼-单元-房号-PLC"，如 "3-1-7-702"
 * @returns {Promise<object>}
 */
async function freeark_get_realtime_params({ specific_part }) {
  if (!specific_part) {
    return fail('缺少必要参数 specific_part，格式为 "<楼>-<单元>-<房号前缀>-<设备ID>"，如 "3-1-7-702"');
  }
  const result = await client.get('/api/devices/realtime-params/', { specific_part });
  if (!result.ok) return fail(result.error, result.status);
  return ok(result.data, `设备 ${specific_part} 实时参数查询成功，共 ${Array.isArray(result.data) ? result.data.length : '?'} 条参数`);
}

// ─────────────────────────────────────────────────────────────────
// Tool 2: freeark_get_usage_daily
// GET /api/usage/quantity/
// ─────────────────────────────────────────────────────────────────
/**
 * 查询日用量数据
 * @param {object} args
 * @param {string} [args.specific_part] - 设备标识符（可选，不填返回全量）
 * @param {string} [args.energy_mode] - "制冷" 或 "制热"（可选）
 * @param {string} [args.start_date] - 开始日期 YYYY-MM-DD（可选）
 * @param {string} [args.end_date] - 结束日期 YYYY-MM-DD（可选）
 * @param {number} [args.page] - 页码（可选，默认 1）
 * @returns {Promise<object>}
 */
async function freeark_get_usage_daily({ specific_part, energy_mode, start_date, end_date, page }) {
  const params = {};
  if (specific_part) params.specific_part = specific_part;
  if (energy_mode) params.energy_mode = energy_mode;
  if (start_date) params.start_date = start_date;
  if (end_date) params.end_date = end_date;
  if (page) params.page = page;

  const result = await client.get('/api/usage/quantity/', params);
  if (!result.ok) return fail(result.error, result.status);
  return ok(result.data, '日用量数据查询成功');
}

// ─────────────────────────────────────────────────────────────────
// Tool 3: freeark_get_usage_period
// GET /api/usage/quantity/specifictimeperiod/
// ─────────────────────────────────────────────────────────────────
/**
 * 查询指定时间段汇总用量
 * @param {object} args
 * @param {string} args.specific_part - 设备标识符
 * @param {string} [args.energy_mode] - "制冷" 或 "制热"
 * @param {string} [args.start_time] - 开始时间 ISO8601
 * @param {string} [args.end_time] - 结束时间 ISO8601
 * @returns {Promise<object>}
 */
async function freeark_get_usage_period({ specific_part, energy_mode, start_time, end_time }) {
  const params = {};
  if (specific_part) params.specific_part = specific_part;
  if (energy_mode) params.energy_mode = energy_mode;
  if (start_time) params.start_time = start_time;
  if (end_time) params.end_time = end_time;

  const result = await client.get('/api/usage/quantity/specifictimeperiod/', params);
  if (!result.ok) return fail(result.error, result.status);
  return ok(result.data, `时间段用量汇总查询成功`);
}

// ─────────────────────────────────────────────────────────────────
// Tool 4: freeark_get_usage_monthly
// GET /api/usage/quantity/monthly/
// ─────────────────────────────────────────────────────────────────
/**
 * 查询月度用量
 * @param {object} args
 * @param {string} [args.specific_part] - 设备标识符（可选）
 * @param {string} [args.energy_mode] - "制冷" 或 "制热"（可选）
 * @param {string} [args.year_month] - 年月 YYYY-MM（可选）
 * @returns {Promise<object>}
 */
async function freeark_get_usage_monthly({ specific_part, energy_mode, year_month }) {
  const params = {};
  if (specific_part) params.specific_part = specific_part;
  if (energy_mode) params.energy_mode = energy_mode;
  if (year_month) params.year_month = year_month;

  const result = await client.get('/api/usage/quantity/monthly/', params);
  if (!result.ok) return fail(result.error, result.status);
  return ok(result.data, '月度用量查询成功');
}

// ─────────────────────────────────────────────────────────────────
// Tool 5: freeark_get_plc_status
// GET /api/plc/connection-status/ 或 /api/plc/connection-status/<id>/
// ─────────────────────────────────────────────────────────────────
/**
 * 查询 PLC 连接状态
 * @param {object} args
 * @param {string} [args.specific_part] - 设备标识符（不填返回所有 PLC 状态）
 * @returns {Promise<object>}
 */
async function freeark_get_plc_status({ specific_part } = {}) {
  const path = specific_part
    ? `/api/plc/connection-status/${encodeURIComponent(specific_part)}/`
    : '/api/plc/connection-status/';

  const result = await client.get(path);
  if (!result.ok) return fail(result.error, result.status);

  const desc = specific_part
    ? `设备 ${specific_part} 的 PLC 连接状态查询成功`
    : 'PLC 连接状态全量查询成功';
  return ok(result.data, desc);
}

// ─────────────────────────────────────────────────────────────────
// Tool 6: freeark_get_plc_history
// GET /api/plc/status-change-history/<id>/
// ─────────────────────────────────────────────────────────────────
/**
 * 查询 PLC 状态变化历史
 * @param {object} args
 * @param {string} args.specific_part - 设备标识符
 * @returns {Promise<object>}
 */
async function freeark_get_plc_history({ specific_part }) {
  if (!specific_part) {
    return fail('缺少必要参数 specific_part');
  }
  const result = await client.get(`/api/plc/status-change-history/${encodeURIComponent(specific_part)}/`);
  if (!result.ok) return fail(result.error, result.status);
  return ok(result.data, `设备 ${specific_part} 的 PLC 状态变化历史查询成功`);
}

// ─────────────────────────────────────────────────────────────────
// Tool 7: freeark_get_dashboard_summary
// GET /api/dashboard/summary/
// ─────────────────────────────────────────────────────────────────
/**
 * 查询看板摘要（总能耗、PLC 在线率等）
 * @returns {Promise<object>}
 */
async function freeark_get_dashboard_summary() {
  const result = await client.get('/api/dashboard/summary/');
  if (!result.ok) return fail(result.error, result.status);
  return ok(result.data, '看板摘要查询成功');
}

// ─────────────────────────────────────────────────────────────────
// Tool 8: freeark_get_services_status
// GET /api/dashboard/services/
// ─────────────────────────────────────────────────────────────────
/**
 * 查询系统服务运行状态（看板视角）
 * @returns {Promise<object>}
 */
async function freeark_get_services_status() {
  const result = await client.get('/api/dashboard/services/');
  if (!result.ok) return fail(result.error, result.status);
  return ok(result.data, '系统服务状态查询成功');
}

// ─────────────────────────────────────────────────────────────────
// Tool 9: freeark_get_power_status
// GET /api/dashboard/power-status/
// ─────────────────────────────────────────────────────────────────
/**
 * 查询供电状态
 * @returns {Promise<object>}
 */
async function freeark_get_power_status() {
  const result = await client.get('/api/dashboard/power-status/');
  if (!result.ok) return fail(result.error, result.status);
  return ok(result.data, '供电状态查询成功');
}

// ─────────────────────────────────────────────────────────────────
// Tool 10: freeark_get_device_params
// GET /api/device-settings/params/<id>/
// ─────────────────────────────────────────────────────────────────
/**
 * 查询设备可写参数列表（含当前值）
 * @param {object} args
 * @param {string} args.specific_part - 设备标识符
 * @returns {Promise<object>}
 */
async function freeark_get_device_params({ specific_part }) {
  if (!specific_part) {
    return fail('缺少必要参数 specific_part');
  }
  const result = await client.get(`/api/device-settings/params/${encodeURIComponent(specific_part)}/`);
  if (!result.ok) return fail(result.error, result.status);
  return ok(result.data, `设备 ${specific_part} 可写参数查询成功`);
}

// ─────────────────────────────────────────────────────────────────
// Tool 11: freeark_get_write_records
// GET /api/device-settings/records/
// ─────────────────────────────────────────────────────────────────
/**
 * 查询设备参数写操作记录
 * @param {object} args
 * @param {string} [args.specific_part] - 设备标识符（可选过滤）
 * @param {string} [args.operator] - 操作员（可选过滤，如 "openclaw-agent"）
 * @param {string} [args.status] - 状态过滤（pending/success/failed/timeout）
 * @param {string} [args.start_time] - 开始时间（可选）
 * @param {string} [args.end_time] - 结束时间（可选）
 * @returns {Promise<object>}
 */
async function freeark_get_write_records({ specific_part, operator, status, start_time, end_time } = {}) {
  const params = {};
  if (specific_part) params.specific_part = specific_part;
  if (operator) params.operator = operator;
  if (status) params.status = status;
  if (start_time) params.start_time = start_time;
  if (end_time) params.end_time = end_time;

  const result = await client.get('/api/device-settings/records/', params);
  if (!result.ok) return fail(result.error, result.status);
  return ok(result.data, '写操作记录查询成功');
}

// ─────────────────────────────────────────────────────────────────
// Tool 12: freeark_get_device_tree
// GET /api/owners/<pk>/device-tree/
// ─────────────────────────────────────────────────────────────────
/**
 * 查询业主设备树
 * @param {object} args
 * @param {number|string} args.owner_id - 业主 ID
 * @returns {Promise<object>}
 */
async function freeark_get_device_tree({ owner_id }) {
  if (!owner_id) {
    return fail('缺少必要参数 owner_id（业主 ID）');
  }
  const result = await client.get(`/api/owners/${encodeURIComponent(owner_id)}/device-tree/`);
  if (!result.ok) return fail(result.error, result.status);
  return ok(result.data, `业主 ID=${owner_id} 的设备树查询成功`);
}

// ─────────────────────────────────────────────────────────────────
// Tool 13: freeark_get_service_detail
// GET /api/services/<name>/detail/
// ─────────────────────────────────────────────────────────────────
/**
 * 查询单个系统服务详情
 * @param {object} args
 * @param {string} args.service_name - 服务名称，如 "freeark-backend"、"freeark-mqtt-consumer"
 * @returns {Promise<object>}
 */
async function freeark_get_service_detail({ service_name }) {
  if (!service_name) {
    return fail('缺少必要参数 service_name（服务名称）');
  }
  const result = await client.get(`/api/services/${encodeURIComponent(service_name)}/detail/`);
  if (!result.ok) return fail(result.error, result.status);
  return ok(result.data, `服务 ${service_name} 详情查询成功`);
}

// ─────────────────────────────────────────────────────────────────
// Tool 14: freeark_get_plc_latest
// GET /api/plc-latest/
// ─────────────────────────────────────────────────────────────────
/**
 * 查询 PLC 最新参数（全量）
 * @param {object} args
 * @param {string} [args.specific_part] - 设备标识符（可选过滤）
 * @returns {Promise<object>}
 */
async function freeark_get_plc_latest({ specific_part } = {}) {
  const params = {};
  if (specific_part) params.specific_part = specific_part;

  const result = await client.get('/api/plc-latest/', params);
  if (!result.ok) return fail(result.error, result.status);
  return ok(result.data, 'PLC 最新参数查询成功');
}

// ─────────────────────────────────────────────────────────────────
// 导出：Tool 名称 → 实现函数映射
// ─────────────────────────────────────────────────────────────────
module.exports = {
  freeark_get_realtime_params,
  freeark_get_usage_daily,
  freeark_get_usage_period,
  freeark_get_usage_monthly,
  freeark_get_plc_status,
  freeark_get_plc_history,
  freeark_get_dashboard_summary,
  freeark_get_services_status,
  freeark_get_power_status,
  freeark_get_device_params,
  freeark_get_write_records,
  freeark_get_device_tree,
  freeark_get_service_detail,
  freeark_get_plc_latest,
};
