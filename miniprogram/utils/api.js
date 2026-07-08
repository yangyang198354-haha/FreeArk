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

import http, { BASE_URL } from './http'
import { getToken } from './auth'

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

  // v1.11.0 Bridge Dashboard — device fault summary by category (MOD-BD-011)
  // IFC-BD-011-01: GET /api/dashboard/device-fault-summary/
  //   → {success, data: {fresh_air_unit: {total, fault_count}, hydraulic_module: {total, fault_count},
  //      air_quality_sensor: {total, fault_count}, other_devices: {total, fault_count}}}
  getDashboardDeviceFaultSummary: () => http.get('/api/dashboard/device-fault-summary/'),

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

  // v1.11.0 业主端实时参数 + 按需采集（MOD-1110-FE-03）
  // IFC-1110-FE-03-1: getOwnerRealtimeParams
  //   GET /api/miniapp/owner/realtime-params/?specific_part={sp}
  //   → 200: { success, specific_part, screen_mac, device_sns, data }
  //   → 400: { success: false, error }
  //   → 403: { detail }
  getOwnerRealtimeParams: (specificPart) =>
    http.get('/api/miniapp/owner/realtime-params/', { specific_part: specificPart }),

  // IFC-1110-FE-03-2: ownerOndemandRefresh
  //   POST /api/miniapp/owner/ondemand-refresh/ {specific_part}
  //   → 202: { status: "accepted"|"duplicate", specific_part }
  //   → 400/403/503: 错误响应
  ownerOndemandRefresh: (specificPart) =>
    http.post('/api/miniapp/owner/ondemand-refresh/', { specific_part: specificPart }),

  // v1.11.3 座舱连通性（舰桥仪表盘 PLC + 大屏双指示器）
  //   GET /api/miniapp/owner/connectivity/?specific_part={sp}
  //   → 200: { success, specific_part, plc_status, screen_status,
  //            plc_last_online_time, screen_last_seen_at }
  //   → 400/403: 错误响应
  getOwnerConnectivity: (specificPart) =>
    http.get('/api/miniapp/owner/connectivity/', { specific_part: specificPart }),

  // v1.11.1 业主设备树结构骨架端点（MOD-1111-FE-02）
  // IFC-1111-FE-02-1: getOwnerStructure
  //   GET /api/miniapp/owner/structure/?specific_part={sp}
  //   → 200 (sync_status="ok"):
  //     { success, specific_part, sync_status, rooms, system_devices, device_sns }
  //     rooms: [{room_id, room_name, ori_room_name,
  //              devices:[{device_sn, device_name, sub_type, product_code,
  //                        params:[{param_name, display_name}]}]}]
  //     system_devices: [{device_sn, device_name, sub_type, product_code, params:[...]}]
  //   → 200 (sync_status="pending"):
  //     { success, specific_part, sync_status:"pending", sync_status_detail,
  //       rooms:[], system_devices:[], device_sns:[] }
  //   → 400: { success: false, error: "specific_part 参数为必填项" }
  //   → 403: { detail: "无权访问该专有部分" }
  getOwnerStructure: (specificPart) =>
    http.get('/api/miniapp/owner/structure/', { specific_part: specificPart }),

  // v1.12.0: 上传头像 + 保存昵称（MOD-V1120-FE-05, IFC-V1120-FE-05-01）
  //   有头像文件：使用 uni.uploadFile（multipart/form-data），filePath+name 语法
  //     （微信小程序不支持 files[] 数组 / uri 字段，那是 App 端专用）
  //   仅昵称：使用 uni.request（JSON body），无需 multipart
  //   @param {String|null} nickname - 用户昵称（可选）
  //   @param {String|null} filePath - 头像临时文件路径（可选，来自 chooseAvatar）
  //   @returns {Promise<{avatar_url: String|null, nickname: String|null}>}
  //   @throws {Error} 网络错误、文件过大、格式不支持、认证失败
  uploadProfile: (nickname, filePath) => {
    const token = getToken()
    const authHeader = { 'Authorization': 'Token ' + token }

    // 仅昵称更新（无文件）：用普通 POST JSON 请求
    if (!filePath) {
      return http.post('/api/miniapp/profile/update/', { nickname })
    }

    // 有头像文件：用 uni.uploadFile，微信小程序必须用 filePath+name 语法
    return new Promise((resolve, reject) => {
      const formData = {}
      if (nickname && nickname.trim()) {
        formData.nickname = nickname.trim()
      }
      uni.uploadFile({
        url: BASE_URL + '/api/miniapp/profile/update/',
        filePath: filePath,
        name: 'avatar',
        formData: formData,
        header: authHeader,
        success: (uploadRes) => {
          try {
            const data = JSON.parse(uploadRes.data)
            if (uploadRes.statusCode >= 200 && uploadRes.statusCode < 300) {
              resolve(data)
            } else {
              reject(new Error(data.detail || '资料更新失败'))
            }
          } catch (e) {
            reject(new Error('服务器响应异常'))
          }
        },
        fail: (err) => {
          reject(new Error(err.errMsg || '上传失败，请检查网络'))
        },
      })
    })
  },
}

export default api
