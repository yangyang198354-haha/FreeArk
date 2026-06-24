import { describe, it, expect, vi } from 'vitest'

// mock http，断言 api 的"接口路径 + 参数"契约（对齐 Web 真实接口）
vi.mock('@/utils/http', () => {
  const m = {
    get: vi.fn(() => Promise.resolve({})),
    post: vi.fn(() => Promise.resolve({})),
    put: vi.fn(() => Promise.resolve({})),
    del: vi.fn(() => Promise.resolve({})),
  }
  return { default: m, http: m, WS_BASE_URL: 'ws://test' }
})

import http from '@/utils/http'
import { api } from '@/utils/api'

describe('utils/api 接口契约', () => {
  it('登录/会话', () => {
    api.login({ username: 'a' })
    expect(http.post).toHaveBeenCalledWith('/api/auth/login/', { username: 'a' })
    api.getSessionList({ page: 1, page_size: 20 })
    expect(http.get).toHaveBeenCalledWith('/api/memory/me/', { page: 1, page_size: 20 })
  })

  it('看板', () => {
    api.getDashboardPlcOnlineRate()
    expect(http.get).toHaveBeenCalledWith('/api/dashboard/plc-online-rate/')
    api.getCondensationWarningCount()
    expect(http.get).toHaveBeenCalledWith('/api/devices/condensation-warning-events/', { page: 1, page_size: 1 })
  })

  it('监控', () => {
    api.getPlcConnectionStatus({ page: 1 })
    expect(http.get).toHaveBeenCalledWith('/api/plc/connection-status/', { page: 1 })
    api.getDeviceList({ page: 1 })
    expect(http.get).toHaveBeenCalledWith('/api/device-management/device-list/', { page: 1 })
    api.getDeviceRealtimeParams('9-1-31-3104')
    expect(http.get).toHaveBeenCalledWith('/api/devices/realtime-params/', { specific_part: '9-1-31-3104' })
    api.ondemandRefresh('9-1')
    expect(http.post).toHaveBeenCalledWith('/api/devices/ondemand-refresh/', { specific_part: '9-1' })
    api.getParamHistory({ specific_part: 'x', param_names: 'a,b' })
    expect(http.get).toHaveBeenCalledWith('/api/devices/param-history/', { specific_part: 'x', param_names: 'a,b' })
  })

  it('能耗（三类端点正确，注意用量查询无尾斜杠）', () => {
    api.getUsageDaily({ page: 1 })
    expect(http.get).toHaveBeenCalledWith('/api/usage/quantity/', { page: 1 })
    api.getUsagePeriod({ page: 1 })
    expect(http.get).toHaveBeenCalledWith('/api/usage/quantity/specifictimeperiod', { page: 1 })
    api.getUsageMonthly({ start_month: '2026-01' })
    expect(http.get).toHaveBeenCalledWith('/api/usage/quantity/monthly/', { start_month: '2026-01' })
  })

  it('运维 + 改密', () => {
    api.getFaultEvents({ page: 1 })
    expect(http.get).toHaveBeenCalledWith('/api/devices/fault-events/', { page: 1 })
    api.getWorkOrders({ page: 1 })
    expect(http.get).toHaveBeenCalledWith('/api/workorders/', { page: 1 })
    api.getWorkOrderDetail(7)
    expect(http.get).toHaveBeenCalledWith('/api/workorders/7/')
    api.approveWorkOrderWrite(7)
    expect(http.post).toHaveBeenCalledWith('/api/workorders/7/approve-write/', {})
    api.resolveWorkOrder(7)
    expect(http.post).toHaveBeenCalledWith('/api/workorders/7/resolve/', {})
    api.getInspectionLogs({ page: 1 })
    expect(http.get).toHaveBeenCalledWith('/api/inspection/logs/', { page: 1 })
    api.changePassword({ current_password: 'a', new_password: 'b' })
    expect(http.post).toHaveBeenCalledWith('/api/change-password/', { current_password: 'a', new_password: 'b' })
  })
})
