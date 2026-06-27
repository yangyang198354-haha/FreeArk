import { createRouter, createWebHistory } from 'vue-router'

// 聊天页会话列表预取缓存（路由 beforeEnter 写入，SessionSidebar onMounted 读取）
export let chatSessionsCache = null
export let chatSessionsCacheTime = 0
const CHAT_SESSIONS_CACHE_TTL_MS = 30000  // 30秒内复用缓存

// 聊天页最新会话历史预取缓存（路由 beforeEnter 串接写入，ChatView onMounted 读取）
// chatHistoryCacheKey: 对应的 session_key_full，防止会话切换后错误复用
export let chatHistoryCache = null
export let chatHistoryCacheTime = 0
export let chatHistoryCacheKey = null

const routes = [
  {
    path: '/',
    redirect: '/home'
  },
  {
    path: '/home',
    name: 'Home',
    component: () => import('../views/HomeView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/usage-query',
    name: 'UsageQuery',
    component: () => import('../views/UsageQueryView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/monthly-usage-report',
    name: 'MonthlyUsageReport',
    component: () => import('../views/MonthlyUsageReportView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/daily-usage-report',
    name: 'DailyUsageReport',
    component: () => import('../views/DailyUsageReportView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/services',
    name: 'Services',
    component: () => import('../views/ServicesView.vue'),
    meta: { requiresAuth: true, requiresAdmin: true }  // v1.6.0: 服务管理仅 admin
  },
  {
    path: '/create-user',
    name: 'CreateUser',
    component: () => import('../views/CreateUserView.vue'),
    meta: { requiresAuth: true, requiresAdmin: true }  // v1.6.0: 用户管理仅 admin
  },
  {
    path: '/user-list',
    name: 'UserList',
    component: () => import('../views/UserListView.vue'),
    meta: { requiresAuth: true, requiresAdmin: true }  // v1.6.0: 用户管理仅 admin
  },
  {
    path: '/edit-user/:id',
    name: 'EditUser',
    component: () => import('../views/EditUserView.vue'),
    meta: { requiresAuth: true, requiresAdmin: true }  // v1.6.0: 用户管理仅 admin
  },
  {
    path: '/change-password',
    name: 'ChangePassword',
    component: () => import('../views/ChangePasswordView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/plc-status',
    name: 'PlcStatus',
    component: () => import('../views/PlcStatusView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/specific-part-detail/:specificPart',
    name: 'SpecificPartDetail',
    component: () => import('../views/SpecificPartDetailView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/owner-management',
    name: 'OwnerManagement',
    component: () => import('../views/OwnerManagementView.vue'),
    meta: { requiresAuth: true }
  },
  {
    // specific_part 通过 query param 传入，如 /device-cards?specific_part=9-1-31-3104
    path: '/device-cards',
    name: 'DeviceCards',
    component: () => import('../views/DeviceCardsView.vue'),
    meta: { requiresAuth: true }
  },
  {
    // specific_part 和 sub_type 通过 query param 传入
    // 如 /device-history?specific_part=9-1-31-3104&sub_type=main_thermostat
    path: '/device-history',
    name: 'DeviceParamHistory',
    component: () => import('../views/DeviceParamHistoryView.vue'),
    meta: { requiresAuth: true }
  },
  {
    // specific_part 通过 query param 传入
    path: '/room-history',
    name: 'RoomHistory',
    component: () => import('../views/RoomHistoryView.vue'),
    meta: { requiresAuth: true }
  },
  {
    // 设备管理 — 设备列表（MOD-FE-01, US-001）
    path: '/device-management/device-list',
    name: 'DeviceManagementDeviceList',
    component: () => import('../views/DeviceManagementDeviceListView.vue'),
    meta: { requiresAuth: true }
  },
  {
    // 设置记录（审计日志只读页面，FR6，US-9）
    path: '/plc-write-records',
    name: 'PlcWriteRecords',
    component: () => import('../views/PlcWriteRecordView.vue'),
    meta: { requiresAuth: true }
  },
  {
    // REQ-FUNC-034: 设备参数设置独立路由页面（specific_part 通过 query param 传入）
    path: '/device-management/device-settings',
    name: 'DeviceSettings',
    component: () => import('../views/DeviceManagementSettingsView.vue'),
    meta: { requiresAuth: true }
  },
  {
    // 方舟智能体聊天页面（REQ-FUNC-001, REQ-FUNC-002；所有登录用户可见，无角色限制）
    path: '/chat',
    name: 'Chat',
    component: () => import('../views/ChatView.vue'),
    meta: { requiresAuth: true },
    beforeEnter: async (to, from, next) => {
      // 认证检查（与全局 beforeEach 保持一致）
      const isLoggedIn = localStorage.getItem('userToken') !== null
      if (!isLoggedIn) {
        next({ name: 'Login' })
        return
      }
      // 预取会话列表（fire-and-don't-await：不阻塞路由跳转，但尽早发起请求）
      // 使用动态 import 避免与 api.js 的循环依赖（api.js 已静态 import router/index.js）
      const now = Date.now()
      if (!chatSessionsCache || (now - chatSessionsCacheTime) > CHAT_SESSIONS_CACHE_TTL_MS) {
        import('../utils/api.js').then(m => {
          const api = m.default
          api.get('/api/memory/me/', { page: 1, page_size: 20 })
            .then(data => {
              chatSessionsCache = data
              chatSessionsCacheTime = Date.now()
              // 串接：会话列表预取成功后，立即 fire 最新会话的历史消息预取
              // 条件：列表非空 + 历史缓存未命中或已过期
              const sessions = data.sessions || []
              if (sessions.length > 0) {
                const latestKey = sessions[0].session_key_full
                const historyNow = Date.now()
                const historyStale = !chatHistoryCache
                  || chatHistoryCacheKey !== latestKey
                  || (historyNow - chatHistoryCacheTime) > CHAT_SESSIONS_CACHE_TTL_MS
                if (historyStale) {
                  api.get(`/api/memory/session/${latestKey}/history/`)
                    .then(histData => {
                      chatHistoryCache = histData
                      chatHistoryCacheTime = Date.now()
                      chatHistoryCacheKey = latestKey
                    })
                    .catch(() => {
                      // 静默失败，ChatView 会自行重试
                    })
                }
              }
            })
            .catch(() => {
              // 静默失败，SessionSidebar 会自行重试
            })
        })
      }
      next()
    },
  },
  {
    // 巡检智能体工作日志（v1.3.0-AOW，REQ-FUNC-NAV-003）
    path: '/agent/inspection-worklog',
    name: 'InspectionWorkLog',
    component: () => import('../views/InspectionWorkLogView.vue'),
    meta: { requiresAuth: true }
  },
  {
    // 巡检工单（v1.3.1-WO）— 查看工单 + 管理员审批执行被拦截的写提案
    path: '/agent/work-orders',
    name: 'WorkOrders',
    component: () => import('../views/WorkOrderListView.vue'),
    meta: { requiresAuth: true }
  },
  {
    // 故障管理页面（v0.6.0-FM，FR-FM-04）
    path: '/device-management/faults',
    name: 'FaultManagement',
    component: () => import('../views/FaultManagementView.vue'),
    meta: { requiresAuth: true }
  },
  {
    // 结露预警页面（v0.7.0-CW，MOD-FE-CW-02）
    path: '/device-management/condensation-warnings',
    name: 'CondensationWarnings',
    component: () => import('../views/CondensationWarningView.vue'),
    meta: { requiresAuth: true }
  },
  {
    // 三恒知识库管理（v1.4.0_sanheng_rag，管理员专属）
    path: '/admin/knowledge-base',
    name: 'KnowledgeBase',
    component: () => import('../views/KnowledgeBaseView.vue'),
    meta: { requiresAuth: true, requiresAdmin: true }
  },
  {
    // v1.6.0 RBAC：user（普通业主/住户）登录后的占位落地页。
    // 业务功能以后单独开发；user 角色访问任何其他业务页都会被守卫重定向到此。
    path: '/user-landing',
    name: 'UserLanding',
    component: () => import('../views/UserLandingView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/LoginView.vue')
  }]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
})

// 路由守卫：检查登录状态 + 管理员权限（v1.4.0: 新增 requiresAdmin 检查）
router.beforeEach((to, from, next) => {
  const requiresAuth = to.matched.some(record => record.meta.requiresAuth)
  const requiresAdmin = to.matched.some(record => record.meta.requiresAdmin)
  const isLoggedIn = localStorage.getItem('userToken') !== null

  if (requiresAuth && !isLoggedIn) {
    next({ name: 'Login' })
    return
  }

  // v1.6.0 RBAC：基于角色的访问控制（仅对已登录用户生效）
  if (isLoggedIn) {
    let role = null
    try {
      role = (JSON.parse(localStorage.getItem('userInfo') || '{}')).role || null
    } catch (e) {
      role = null
    }
    if (role === 'user') {
      // user（普通业主）：除占位页外，任何页面都重定向到占位页
      if (to.path !== '/user-landing') {
        next({ path: '/user-landing' })
        return
      }
      next()
      return
    }
    // admin/operator 误入占位页 → 回首页
    if (to.path === '/user-landing') {
      next({ path: '/home' })
      return
    }
  }

  if (requiresAdmin) {
    try {
      // 本项目 admin 概念是 userInfo.role==='admin'（与菜单 v-if 及后端 role 鉴权一致）；
      // /api/auth/me/ 不返回 is_staff，旧的 is_staff 判断恒为 undefined 会把管理员也弹回首页。
      const userInfo = JSON.parse(localStorage.getItem('userInfo') || '{}')
      if (userInfo.role !== 'admin') {
        next({ path: '/home' })
        return
      }
    } catch (e) {
      next({ path: '/home' })
      return
    }
  }
  next()
})

export default router