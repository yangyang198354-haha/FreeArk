/**
 * @module MOD-API
 * @author sub_agent_software_developer
 * @description Typed API call catalogue. All calls go through http.js (no bare uni.request).
 *
 * Dashboard APIs (NQ-01 confirmed):
 *   - /api/dashboard/plc-online-rate/   → {success, data: {online_count, offline_count, total_count, rate}}
 *   - /api/dashboard/fault-summary/     → {success, data: {active_fault_count, affected_unit_count}}
 *   - /api/dashboard/summary/           → {success, data: {today_kwh, month_kwh, date, month}}
 *   - Condensation count: GET /api/devices/condensation-warning-events/?page=1&page_size=1
 *     reads top-level `count` from DRF paginated response (NOT a custom dashboard endpoint)
 */

import http from './http'

export const api = {
  // Auth
  login: (data) => http.post('/api/auth/login/', data),
  logout: () => http.post('/api/auth/logout/', {}),

  // Miniapp 业主端账号体系（v1.8.0）—— 走独立 /api/miniapp/ 命名空间
  //   注册 miniapp_register：POST /api/miniapp/auth/register/ {username,password,password2,email?}
  //     → 201 {token, user:{id,username,email,role}}（role 后端强制 user）
  miniappRegister: (data) => http.post('/api/miniapp/auth/register/', data),
  //   微信一键登录 miniapp_wechat_login：POST /api/miniapp/auth/wechat/ {code}
  //     → 200/201 {token, user:{...}, is_new}
  miniappWechatLogin: (data) => http.post('/api/miniapp/auth/wechat/', data),
  //   绑定专有部分 miniapp_bind：POST /api/miniapp/bind/ {unique_id}
  //     → 200 {specific_part, location_name, bound_at}；404 未找到；409 已绑定
  bindOwner: (data) => http.post('/api/miniapp/bind/', data),
  //   自助解绑 miniapp_unbind：POST /api/miniapp/unbind/ {unique_id|specific_part}
  //     → 200 {detail, specific_part}
  unbindOwner: (data) => http.post('/api/miniapp/unbind/', data),
  //   绑定状态 miniapp_bind_status：GET /api/miniapp/bind/status/
  //     → 200 {bound, bindings:[{specific_part, location_name, bound_at}]}
  getBindStatus: () => http.get('/api/miniapp/bind/status/'),

  // Dashboard — 4 separate calls as per NQ-01
  getDashboardPlcOnlineRate: () => http.get('/api/dashboard/plc-online-rate/'),
  getDashboardFaultSummary: () => http.get('/api/dashboard/fault-summary/'),
  getDashboardSummary: () => http.get('/api/dashboard/summary/'),
  // Condensation: use paginated list endpoint; read `count` from DRF response root
  getCondensationWarningCount: () => http.get('/api/devices/condensation-warning-events/', { page: 1, page_size: 1 }),

  // Monitoring — 分包A（接口对齐现有 Web 视图）
  // PlcStatusView：GET /api/plc/connection-status/ {page,page_size,building,unit,connection_status}
  //   → {success, data:[{specific_part,connection_status,last_online_time,building,unit,room_number}], total, statistics}
  getPlcConnectionStatus: (params) => http.get('/api/plc/connection-status/', params),
  // DeviceManagementDeviceListView：GET /api/device-management/device-list/ {page,page_size,room_no,...}
  //   → DRF 分页 {results:[{specific_part,building,unit,room_number,...}], count}
  getDeviceList: (params) => http.get('/api/device-management/device-list/', params),
  // DeviceCardsView：GET /api/devices/realtime-params/?specific_part=X
  //   → {success, data:{group:{sub_types:{sub:{display,params:[{param_name,display_name,value}]}}}}}
  getDeviceRealtimeParams: (specificPart) => http.get('/api/devices/realtime-params/', { specific_part: specificPart }),
  // 按需采集：POST /api/devices/ondemand-refresh/ {specific_part}（移动端简化：触发后延时重取，不订阅 MQTT done）
  ondemandRefresh: (specificPart) => http.post('/api/devices/ondemand-refresh/', { specific_part: specificPart }),
  // 参数/房间历史：GET /api/devices/param-history/ {specific_part,param_names,start_time,end_time,chart:'true'}
  //   → {success, results:[{param_name, collected_at, value}]}
  getParamHistory: (params) => http.get('/api/devices/param-history/', params),

  // Energy 能耗 — 批次②（接口对齐 Web 报表视图）
  //   公共响应：{success, data:[{specific_part,building,unit,room_number,energy_mode,initial_energy,final_energy,usage_quantity,time_period}], total}
  //   日报 DailyUsageReportView：GET /api/usage/quantity/ {page,page_size,specific_part,energy_mode,start_time,end_time}
  getUsageDaily: (params) => http.get('/api/usage/quantity/', params),
  //   用量查询 UsageQueryView：GET /api/usage/quantity/specifictimeperiod 同参（注意无尾斜杠）
  getUsagePeriod: (params) => http.get('/api/usage/quantity/specifictimeperiod', params),
  //   月报 MonthlyUsageReportView：GET /api/usage/quantity/monthly/ {…,start_month,end_month}
  getUsageMonthly: (params) => http.get('/api/usage/quantity/monthly/', params),

  // Ops 运维 — 批次③（接口对齐 Web；分页 BA-07 后端已支持，零后端改动）
  // 故障事件（只读）FaultManagementView：GET /api/devices/fault-events/ {page,page_size,is_active,first_seen_after,...} → DRF {results,count}
  getFaultEvents: (params) => http.get('/api/devices/fault-events/', params),
  // 结露预警（只读）CondensationWarningView：GET /api/devices/condensation-warning-events/ → DRF {results,count}
  getCondensationEvents: (params) => http.get('/api/devices/condensation-warning-events/', params),
  // 巡检工单 WorkOrderListView：列表 GET /api/workorders/ {page,page_size,status,...} → {success,data,total}
  getWorkOrders: (params) => http.get('/api/workorders/', params),
  getWorkOrderDetail: (id) => http.get(`/api/workorders/${id}/`),
  approveWorkOrderWrite: (id) => http.post(`/api/workorders/${id}/approve-write/`, {}),
  resolveWorkOrder: (id) => http.post(`/api/workorders/${id}/resolve/`, {}),
  // 巡检工作日志（只读）InspectionWorkLogView：GET /api/inspection/logs/ {page,page_size,...} → {success,data,total}
  getInspectionLogs: (params) => http.get('/api/inspection/logs/', params),
  // 改密 ChangePasswordView：POST /api/change-password/ {current_password,new_password} → {success}
  changePassword: (data) => http.post('/api/change-password/', data),

  // 屏端 MQTT 参数配置（v1.10.0，业主端）
  //   config：GET /api/miniapp/device-settings/config/
  //     → {broker, topics, rooms:[{specific_part,location_name,screen_mac}], config:{writable_attrs,...}}
  getDeviceSettingsConfig: () => http.get('/api/miniapp/device-settings/config/'),
  //   audit（尽力上报）：POST /api/miniapp/device-settings/audit/
  //     {request_id, specific_part, screen_mac, device_sn, result, items:[{attr_tag,attr_value,old_value}]}
  reportDeviceSettingsAudit: (data) => http.post('/api/miniapp/device-settings/audit/', data),

  // Chat sessions
  getSessionList: (params) => http.get('/api/memory/me/', params),
  getSessionHistory: (sessionKey) => http.get(`/api/memory/session/${sessionKey}/history/`),
  deleteSession: (sessionKey) => http.del(`/api/memory/session/${sessionKey}/`),
}

export default api
