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
    path: '/login',
    name: 'Login',
    component: () => import('../views/LoginView.vue')
  }]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
})

// 路由守卫，检查登录状态
router.beforeEach((to, from, next) => {
  const requiresAuth = to.matched.some(record => record.meta.requiresAuth)
  const isLoggedIn = localStorage.getItem('userToken') !== null
  
  if (requiresAuth && !isLoggedIn) {
    next({ name: 'Login' })
  } else {
    next()
  }
})

export default router