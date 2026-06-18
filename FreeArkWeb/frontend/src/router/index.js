import { createRouter, createWebHistory } from 'vue-router'

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
    meta: { requiresAuth: true }
  },
  {
    path: '/create-user',
    name: 'CreateUser',
    component: () => import('../views/CreateUserView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/user-list',
    name: 'UserList',
    component: () => import('../views/UserListView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/edit-user/:id',
    name: 'EditUser',
    component: () => import('../views/EditUserView.vue'),
    meta: { requiresAuth: true }
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
    // 方舟龙虾聊天页面（REQ-FUNC-001, REQ-FUNC-002；所有登录用户可见，无角色限制）
    path: '/chat',
    name: 'Chat',
    component: () => import('../views/ChatView.vue'),
    meta: { requiresAuth: true }
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