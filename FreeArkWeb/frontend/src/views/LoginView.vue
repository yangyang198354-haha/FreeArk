<template>
  <!-- AC-UI-001-02: 全屏登录页（改版 v2.0 — 深色科技风双栏布局）-->
  <div class="lp-stage">
    <!-- 网格背景装饰 -->
    <div class="lp-grid-bg"></div>

    <!-- 角落装饰线 -->
    <div class="lp-corner lp-corner--tl"></div>
    <div class="lp-corner lp-corner--tr"></div>
    <div class="lp-corner lp-corner--bl"></div>
    <div class="lp-corner lp-corner--br"></div>

    <!-- 侧边刻度 -->
    <div class="lp-side-ticks" ref="sideTicks"></div>

    <!-- 顶部 chrome -->
    <div class="lp-chrome-top">
      <div class="lp-brand">
        <div class="lp-logo">
          <svg viewBox="0 0 48 48" fill="none">
            <defs>
              <linearGradient id="lp-lg1" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stop-color="#3b82f6"/>
                <stop offset="1" stop-color="#22d3ee"/>
              </linearGradient>
            </defs>
            <path d="M24 3 L42 13.5 V34.5 L24 45 L6 34.5 V13.5 Z"
                  stroke="url(#lp-lg1)" stroke-width="1.2" fill="rgba(59,130,246,0.05)"/>
            <path d="M14 30 L24 18 L34 30"
                  stroke="url(#lp-lg1)" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
            <circle cx="24" cy="24" r="2" fill="#3b82f6"/>
            <path d="M14 33 H34" stroke="#3b82f6" stroke-width="1" opacity="0.55"/>
          </svg>
        </div>
        <div class="lp-brand-name">
          <div class="lp-brand-cn">自由方舟 · FREEARK</div>
          <div class="lp-brand-en">Energy Collection Platform · v4.2</div>
        </div>
      </div>
      <div class="lp-meta-row">
        <div class="lp-meta-item">
          <span class="lp-status-dot"></span>SYSTEM ONLINE
        </div>
        <div class="lp-meta-item">总设备数 / DEVICES <span class="lp-accent-val">634</span></div>
        <div class="lp-meta-item" ref="clockDate">{{ displayDate }}</div>
        <div class="lp-meta-item lp-meta-time">{{ displayTime }}</div>
      </div>
    </div>

    <!-- 主体：左右分栏 -->
    <div class="lp-split">
      <!-- 左栏：装饰营销区（<1100px 自动隐藏）-->
      <div class="lp-pane-left">
        <!-- 品牌主文案 -->
        <div class="lp-hero">
          <div class="lp-eyebrow">
            <span class="lp-eyebrow-dot"></span>实时能耗采集 · 设备在线监控
          </div>
          <h1 class="lp-h1">
            制冷 · 制热 · 能效<br/>
            <span class="lp-accent-text">让每一度电都被看见</span>
          </h1>
          <p class="lp-sub">
            自由方舟能耗采集平台接入 634 台终端设备，覆盖 PLC、温控面板、空气品质传感器、新风与水力模块，
            通过分钟级能耗采集与故障预警，为住宅与园区提供精细化能效管理与碳核算能力。
          </p>
        </div>

        <!-- 能耗环形图（纯视觉装饰，静态模拟值，不对接真实接口）-->
        <div class="lp-viz">
          <div class="lp-rings">
            <svg viewBox="0 0 400 400">
              <defs>
                <radialGradient id="lp-bgGlow" cx="0.5" cy="0.5" r="0.5">
                  <stop offset="0%" stop-color="#3b82f6" stop-opacity="0.12"/>
                  <stop offset="55%" stop-color="#22d3ee" stop-opacity="0.03"/>
                  <stop offset="100%" stop-color="#0a1424" stop-opacity="0"/>
                </radialGradient>
              </defs>
              <circle cx="200" cy="200" r="188" fill="url(#lp-bgGlow)"/>
              <g ref="tickRingSvg"></g>
              <text x="200" y="20" class="lp-svg-label-faint" text-anchor="middle">能耗结构 · ENERGY MIX</text>
              <text x="200" y="392" class="lp-svg-label-faint" text-anchor="middle">PLC 在线率 · {{ plcRateDisplay }}%</text>
              <!-- 外圈：制冷/制热占比 donut -->
              <circle cx="200" cy="200" r="150" class="lp-ring-track" stroke-width="14"/>
              <circle ref="coolArcEl" cx="200" cy="200" r="150" fill="none" stroke-linecap="round" stroke-width="14"
                      stroke="#3b82f6" transform="rotate(-90 200 200)"
                      style="filter:drop-shadow(0 0 8px rgba(59,130,246,0.55))"/>
              <circle ref="heatArcEl" cx="200" cy="200" r="150" fill="none" stroke-linecap="round" stroke-width="14"
                      stroke="#f0506e" transform="rotate(-90 200 200)"
                      style="filter:drop-shadow(0 0 8px rgba(240,80,110,0.5))"/>
              <!-- 内圈：设备在线率 -->
              <circle cx="200" cy="200" r="110" class="lp-ring-track"/>
              <circle ref="devArcEl" cx="200" cy="200" r="110" fill="none" stroke-linecap="round" stroke-width="2"
                      stroke="#3b82f6" transform="rotate(-90 200 200)"
                      style="filter:drop-shadow(0 0 6px #3b82f6)"/>
              <circle ref="devDotEl" r="3.5" fill="#3b82f6" style="filter:drop-shadow(0 0 6px #3b82f6)"/>
              <text x="104" y="108" class="lp-svg-label-mono" fill="#3b82f6" font-size="12" text-anchor="middle">制冷</text>
              <text x="296" y="300" class="lp-svg-label-mono" fill="#f0506e" font-size="12" text-anchor="middle">制热</text>
              <line x1="200" y1="122" x2="200" y2="278" stroke="rgba(120,160,220,0.10)" stroke-width="1" stroke-dasharray="2 4"/>
              <line x1="122" y1="200" x2="278" y2="200" stroke="rgba(120,160,220,0.10)" stroke-width="1" stroke-dasharray="2 4"/>
            </svg>
            <div class="lp-center-stat">
              <div class="lp-kw">118.6<span class="lp-kw-unit">万</span></div>
              <div class="lp-kw-sub">KWH · 累计总电量</div>
              <div class="lp-kw-lbl">TOTAL ENERGY</div>
            </div>
          </div>

          <!-- 浮动标签（静态装饰）-->
          <div class="lp-floater" style="top:6%;right:7%">
            <span class="lp-floater-lab">温控面板</span><span class="lp-floater-val">2954</span>
          </div>
          <div class="lp-floater" style="bottom:16%;left:4%">
            <span class="lp-floater-lab">新风模块</span><span class="lp-floater-val">634</span>
          </div>
          <div class="lp-floater" style="bottom:3%;right:12%">
            <span class="lp-floater-lab">开机率</span><span class="lp-floater-val">{{ runRateDisplay }}%</span>
          </div>
        </div>

        <!-- 底部三格 metric 卡 -->
        <div class="lp-metric-grid">
          <div class="lp-metric" style="--lp-mc:#3b82f6">
            <div class="lp-metric-name">今日用电量 · TODAY</div>
            <div class="lp-metric-val">{{ todayKwhDisplay }}<span class="lp-metric-unit">kWh</span></div>
            <div class="lp-metric-delta lp-delta-up">本月累计 206,487 kWh</div>
            <svg class="lp-sparkline" data-color="#3b82f6" data-seed="1.1" viewBox="0 0 100 22" preserveAspectRatio="none" ref="spark0"></svg>
          </div>
          <div class="lp-metric" style="--lp-mc:#34d399">
            <div class="lp-metric-name">PLC 在线 · ONLINE</div>
            <div class="lp-metric-val">565<span class="lp-metric-unit">/ 634</span></div>
            <div class="lp-metric-delta lp-delta-up">▲ 在线率 {{ plcRateDisplay }}%</div>
            <svg class="lp-sparkline" data-color="#34d399" data-seed="2.7" viewBox="0 0 100 22" preserveAspectRatio="none" ref="spark1"></svg>
          </div>
          <div class="lp-metric" style="--lp-mc:#f0506e">
            <div class="lp-metric-name">当前故障 · FAULTS</div>
            <div class="lp-metric-val">{{ faultsDisplay }}<span class="lp-metric-unit">起</span></div>
            <div class="lp-metric-delta lp-delta-dn">▼ 影响 75 户 · 待处理</div>
            <svg class="lp-sparkline" data-color="#f0506e" data-seed="3.9" viewBox="0 0 100 22" preserveAspectRatio="none" ref="spark2"></svg>
          </div>
        </div>
      </div>

      <!-- 右栏：登录卡 -->
      <div class="lp-pane-right">
        <!-- AC-UI-001-03: 入场动画 500ms ease-out translateY 20px→0 -->
        <div class="lp-card">
          <div class="lp-card-head">
            <div class="lp-card-title">欢迎回来</div>
            <div class="lp-card-sub">SIGN IN · FREEARK CONSOLE</div>
          </div>

          <!-- 保留 el-form 以维持校验与无障碍（AC-UI-001-02/03）-->
          <el-form :model="loginForm" :rules="loginRules" ref="loginFormRef" label-position="top">
            <el-form-item prop="username">
              <!-- 字段标签 -->
              <template #label>
                <span class="lp-field-label">工号 / 邮箱</span>
              </template>
              <div class="lp-input-wrap" :class="{ 'lp-input-wrap--focus': focusField === 'username' }">
                <span class="lp-input-icon">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                       stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="8" r="4"/><path d="M4 21v-1a7 7 0 0 1 14 0v1"/>
                  </svg>
                </span>
                <el-input
                  v-model="loginForm.username"
                  placeholder="请输入账户"
                  autocomplete="username"
                  @focus="focusField = 'username'"
                  @blur="focusField = ''"
                />
              </div>
            </el-form-item>

            <el-form-item prop="password">
              <template #label>
                <span class="lp-field-label">登录密码</span>
              </template>
              <div class="lp-input-wrap" :class="{ 'lp-input-wrap--focus': focusField === 'password' }">
                <span class="lp-input-icon">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                       stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="4" y="11" width="16" height="10" rx="2"/>
                    <path d="M8 11V8a4 4 0 0 1 8 0v3"/>
                  </svg>
                </span>
                <el-input
                  v-model="loginForm.password"
                  :type="showPassword ? 'text' : 'password'"
                  placeholder="请输入密码"
                  autocomplete="current-password"
                  @keyup.enter="handleLogin"
                  @focus="focusField = 'password'"
                  @blur="focusField = ''"
                />
                <button type="button" class="lp-pw-toggle" @click="showPassword = !showPassword"
                        :aria-label="showPassword ? '隐藏密码' : '显示密码'">
                  <!-- eye icon -->
                  <svg v-if="!showPassword" width="16" height="16" viewBox="0 0 24 24" fill="none"
                       stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/>
                    <circle cx="12" cy="12" r="3"/>
                  </svg>
                  <!-- eye-off icon -->
                  <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none"
                       stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M3 3l18 18"/>
                    <path d="M10.6 6.1A10 10 0 0 1 12 6c6 0 10 6 10 6a18 18 0 0 1-3.3 3.9"/>
                    <path d="M6 8.5A18 18 0 0 0 2 12s4 6 10 6a10 10 0 0 0 4.2-.9"/>
                    <path d="M9.5 10.6A3 3 0 0 0 12 15a3 3 0 0 0 2.4-1.1"/>
                  </svg>
                </button>
              </div>
            </el-form-item>

            <!-- 错误提示（AC-UI-001-02）-->
            <div v-if="error" class="lp-error-msg">
              <el-icon><Warning /></el-icon>
              {{ error }}
            </div>

            <!-- 记住登录 + 忘记密码 -->
            <div class="lp-row-between">
              <label class="lp-check">
                <input type="checkbox" v-model="rememberMe" />
                7 天内保持登录
              </label>
              <a class="lp-link" href="#">忘记密码？</a>
            </div>

            <!-- 登录按钮（loading 态保留）-->
            <el-form-item style="margin-bottom:0">
              <button type="button" class="lp-btn-primary"
                      :class="{ 'lp-btn-loading': loading }"
                      :disabled="loading"
                      @click="handleLogin">
                <span v-if="!loading">
                  登 录 控 制 台
                  <span class="lp-btn-arrow">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                         stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M5 12h14M13 5l7 7-7 7"/>
                    </svg>
                  </span>
                </span>
                <span v-else class="lp-btn-spinner"></span>
              </button>
            </el-form-item>
          </el-form>

          <!-- 卡片底部合规标识 -->
          <div class="lp-card-foot">
            <span>© 2026 FREEARK</span>
            <span class="lp-mono">SOC2 · ISO 27001 · 等保三级</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 底部 chrome -->
    <div class="lp-chrome-bottom">
      <div class="lp-meta-row">
        <div class="lp-meta-item"><span class="lp-status-dot"></span>freeark-backend · 运行中</div>
        <div class="lp-meta-item">采集频率 <span class="lp-accent-val">60s</span></div>
        <div class="lp-meta-item" style="white-space:nowrap">
          制冷 <span style="color:#3b82f6">210,611</span> · 制热 <span style="color:#f0506e">975,456</span> kWh
        </div>
      </div>
      <div class="lp-meta-row">
        <div class="lp-meta-item">服务条款</div>
        <div class="lp-meta-item">隐私政策</div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, markRaw, onMounted, onUnmounted } from 'vue'
import { Warning } from '@element-plus/icons-vue'
import api from '../utils/api'

export default {
  name: 'LoginView',
  components: { Warning },
  setup() {
    // ---- 响应式数据 ----
    const loginFormRef = ref(null)
    const loginForm = ref({ username: '', password: '' })
    const loginRules = {
      username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
      password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
    }
    const loading = ref(false)
    const error = ref('')
    const showPassword = ref(false)
    const rememberMe = ref(true)
    const focusField = ref('')

    // ---- 装饰动画数值（纯前端模拟，pure visual simulation）----
    const displayDate = ref('')
    const displayTime = ref('')
    const plcRateDisplay = ref('89.12')
    const todayKwhDisplay = ref('15,375')
    const faultsDisplay = ref('481')
    const runRateDisplay = ref('62.6')

    // SVG 元素 refs
    const tickRingSvg = ref(null)
    const coolArcEl = ref(null)
    const heatArcEl = ref(null)
    const devArcEl = ref(null)
    const devDotEl = ref(null)
    const sideTicks = ref(null)
    const spark0 = ref(null)
    const spark1 = ref(null)
    const spark2 = ref(null)

    const WK = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
    function pad(n) { return String(n).padStart(2, '0') }

    // 时钟
    let clockTimer = null
    function tickClock() {
      const d = new Date()
      displayDate.value = `${d.getFullYear()}.${pad(d.getMonth()+1)}.${pad(d.getDate())} · ${WK[d.getDay()]}`
      displayTime.value = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
    }

    // 装饰数值刷新（pure visual simulation; replace with real values if needed）
    let vizTick = 0
    let vizTimer = null
    const R = 150, C = 2 * Math.PI * R, GAP = 0.012 * C
    const Rd = 110, Cd = 2 * Math.PI * Rd
    const coolKwh = 210611, heatKwh = 975456
    const coolFrac = coolKwh / (coolKwh + heatKwh)

    function initDonut() {
      const coolLen = Math.max(0, coolFrac * C - GAP)
      const heatLen = Math.max(0, (1 - coolFrac) * C - GAP)
      if (coolArcEl.value) {
        coolArcEl.value.setAttribute('stroke-dasharray', `${coolLen} ${C - coolLen}`)
      }
      if (heatArcEl.value) {
        heatArcEl.value.setAttribute('stroke-dasharray', `${heatLen} ${C - heatLen}`)
        heatArcEl.value.setAttribute('stroke-dashoffset', String(-(coolFrac * C)))
      }
    }

    function setDevice(pct) {
      pct = Math.max(0.04, Math.min(0.96, pct))
      const len = pct * Cd
      if (devArcEl.value) devArcEl.value.setAttribute('stroke-dasharray', `${len} ${Cd - len}`)
      const a = pct * Math.PI * 2 - Math.PI / 2
      if (devDotEl.value) {
        devDotEl.value.setAttribute('cx', String(200 + Math.cos(a) * Rd))
        devDotEl.value.setAttribute('cy', String(200 + Math.sin(a) * Rd))
      }
    }

    function refreshViz() {
      const t = vizTick
      const today = 15375 + 90 * Math.sin(t * 0.27 + 2.1)
      const plc = 0.8912 + 0.002 * Math.sin(t * 0.2)
      const faults = 481 + Math.round(2 * Math.sin(t * 0.3))
      const run = 62.6 + 0.6 * Math.sin(t * 0.22 + 1.1)
      todayKwhDisplay.value = Math.round(today).toLocaleString()
      plcRateDisplay.value = (plc * 100).toFixed(2)
      faultsDisplay.value = String(faults)
      runRateDisplay.value = run.toFixed(1)
      setDevice(plc)
      vizTick++
    }

    // 刻度环
    function initTickRing() {
      const SVGNS = 'http://www.w3.org/2000/svg'
      const container = tickRingSvg.value
      if (!container) return
      for (let k = 0; k < 60; k++) {
        const a = (k / 60) * Math.PI * 2 - Math.PI / 2
        const inner = k % 5 === 0 ? 182 : 186, outer = 192
        const ln = document.createElementNS(SVGNS, 'line')
        ln.setAttribute('x1', String(200 + Math.cos(a) * inner))
        ln.setAttribute('y1', String(200 + Math.sin(a) * inner))
        ln.setAttribute('x2', String(200 + Math.cos(a) * outer))
        ln.setAttribute('y2', String(200 + Math.sin(a) * outer))
        ln.setAttribute('class', 'lp-tick' + (k % 5 === 0 ? ' lp-tick--major' : ''))
        container.appendChild(ln)
      }
    }

    // 侧边刻度条
    function initSideTicks() {
      const st = sideTicks.value
      if (!st) return
      for (let i = 0; i < 18; i++) {
        const d = document.createElement('div')
        d.className = 'lp-side-tick' + (i % 4 === 0 ? ' lp-side-tick--long' : '')
        st.appendChild(d)
      }
    }

    // sparklines
    function buildSpark(svgEl) {
      if (!svgEl) return
      const SVGNS = 'http://www.w3.org/2000/svg'
      const color = svgEl.getAttribute('data-color')
      const seed = parseFloat(svgEl.getAttribute('data-seed'))
      const n = 32, w = 100, h = 22
      const pts = []
      for (let i = 0; i < n; i++) {
        const t = i / (n - 1)
        let v = 0.5 + 0.3 * Math.sin(t * 8 + seed) + 0.18 * Math.sin(t * 18 + seed * 1.4) + 0.05 * Math.cos(t * 30 + seed)
        v = Math.max(0.05, Math.min(0.95, v))
        pts.push([t * w, (1 - v) * h])
      }
      const d = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ')
      const path2 = document.createElementNS(SVGNS, 'path')
      path2.setAttribute('d', `${d} L100,${h} L0,${h} Z`)
      path2.setAttribute('fill', color)
      path2.setAttribute('opacity', '0.07')
      const path1 = document.createElementNS(SVGNS, 'path')
      path1.setAttribute('d', d)
      path1.setAttribute('stroke', color)
      path1.setAttribute('stroke-width', '1.2')
      path1.setAttribute('fill', 'none')
      path1.setAttribute('stroke-linecap', 'round')
      path1.setAttribute('stroke-linejoin', 'round')
      path1.setAttribute('opacity', '0.9')
      const dot = document.createElementNS(SVGNS, 'circle')
      dot.setAttribute('cx', String(pts[pts.length - 1][0]))
      dot.setAttribute('cy', String(pts[pts.length - 1][1]))
      dot.setAttribute('r', '1.6')
      dot.setAttribute('fill', color)
      svgEl.appendChild(path2)
      svgEl.appendChild(path1)
      svgEl.appendChild(dot)
    }

    onMounted(() => {
      tickClock()
      clockTimer = setInterval(tickClock, 1000)

      initSideTicks()
      initTickRing()
      buildSpark(spark0.value)
      buildSpark(spark1.value)
      buildSpark(spark2.value)
      initDonut()
      refreshViz()
      vizTimer = setInterval(refreshViz, 1600)
    })

    onUnmounted(() => {
      clearInterval(clockTimer)
      clearInterval(vizTimer)
    })

    return {
      loginFormRef, loginForm, loginRules,
      loading, error, showPassword, rememberMe, focusField,
      displayDate, displayTime,
      plcRateDisplay, todayKwhDisplay, faultsDisplay, runRateDisplay,
      tickRingSvg, coolArcEl, heatArcEl, devArcEl, devDotEl,
      sideTicks, spark0, spark1, spark2
    }
  },

  methods: {
    // ---- handleLogin: 1:1 保留原有鉴权逻辑 (BUG-CSRF-001 已通过 credentials:'include' 规避) ----
    async handleLogin() {
      this.$refs.loginFormRef.validate(async (valid) => {
        if (valid) {
          this.loading = true
          this.error = ''
          try {
            const baseUrl = import.meta.env.VITE_API_BASE_URL ||
              (typeof window !== 'undefined' ? window.location.origin : 'http://localhost:8000')
            const loginUrl = `${baseUrl}/api/auth/login/`

            const resp = await fetch(loginUrl, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              credentials: 'include',            // CSRF/cookie 行为零回退
              // remember_me 传给后端，决定滑动窗口超时阈值（7天 vs 30分钟）
              body: JSON.stringify({ ...this.loginForm, remember_me: this.rememberMe })
            })

            if (!resp.ok) {
              const errData = await resp.json().catch(() => ({}))
              throw { response: { data: errData } }
            }

            const data = await resp.json()

            if (data.token) {
              localStorage.setItem('userToken', data.token)
              localStorage.setItem('isAuthenticated', 'true')
              const secure = window.location.protocol === 'https:'
              // 勾选"7天内保持登录"时 cookie 存 7 天，否则 1 天；
              // 真正的会话有效期由后端滑动窗口超时控制（见 remember_me）
              const maxAge = this.rememberMe ? 604800 : 86400
              let cookieString = `auth_token=${encodeURIComponent(data.token)}; path=/; max-age=${maxAge}; SameSite=Lax`
              if (secure) cookieString += '; Secure'
              document.cookie = cookieString
              // 登录成功：复位会话过期提示去重标志，使下次过期能再次提示
              api.resetSessionExpiredFlag()
              this.$router.push('/')
            }
          } catch (error) {
            let errorMessage = '登录失败，请检查用户名和密码'
            if (error.response) {
              errorMessage = error.response.data?.non_field_errors?.[0] ||
                             error.response.data?.detail ||
                             errorMessage
            } else if (error.message && (
              error.message.includes('NetworkError') ||
              error.message.includes('Failed to fetch')
            )) {
              errorMessage = '网络连接异常，请检查您的网络'
            }
            this.error = errorMessage
          } finally {
            this.loading = false
          }
        }
      })
    }
  }
}
</script>

<style scoped>
/* =============================================================
   登录页局部设计令牌（--lp-* 前缀，不污染全局命名空间）
   色板来自 reference/Login-standalone.html，与全局令牌隔离。
   字体降级到系统字体，无外网 CDN 依赖。
   ============================================================= */
.lp-stage {
  /* 局部色板 */
  --lp-bg-0: #050a14;
  --lp-bg-1: #0a1424;
  --lp-bg-2: #0f1d35;
  --lp-ink-0: #f0f6ff;
  --lp-ink-1: #c7d4ea;
  --lp-ink-2: #7a8bab;
  --lp-ink-3: #4a5a78;
  --lp-line: rgba(120,160,220,0.12);
  --lp-line-2: rgba(120,160,220,0.22);
  --lp-acc: #3b82f6;
  --lp-acc-2: #22d3ee;
  --lp-cool: #3b82f6;
  --lp-heat: #f0506e;
  --lp-ok: #34d399;
  /* 字体栈：系统字体降级，无 Google Fonts CDN 依赖 */
  --lp-font-sans: 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei',
                  system-ui, -apple-system, sans-serif;
  --lp-font-mono: 'JetBrains Mono', 'Fira Code', ui-monospace,
                  'Courier New', monospace;

  /* AC-UI-001-02: 全屏 */
  position: fixed;
  inset: 0;
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  background:
    radial-gradient(1200px 800px at 18% 30%, rgba(56,189,248,0.10), transparent 60%),
    radial-gradient(900px 700px at 85% 80%, rgba(59,130,246,0.08), transparent 60%),
    radial-gradient(700px 500px at 60% 10%, rgba(34,211,238,0.05), transparent 60%),
    linear-gradient(180deg, #050a14 0%, #060d1c 60%, #050a14 100%);
  color: var(--lp-ink-0);
  font-family: var(--lp-font-sans);
  -webkit-font-smoothing: antialiased;
}

/* 网格背景 */
.lp-grid-bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background-image:
    linear-gradient(rgba(120,160,220,0.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(120,160,220,0.045) 1px, transparent 1px);
  background-size: 56px 56px;
  -webkit-mask-image: radial-gradient(1200px 800px at 30% 50%, #000 0%, transparent 75%);
  mask-image: radial-gradient(1200px 800px at 30% 50%, #000 0%, transparent 75%);
}

/* 角落装饰线 */
.lp-corner {
  position: absolute;
  width: 22px;
  height: 22px;
  border: 1px solid rgba(59,130,246,0.5);
  pointer-events: none;
  z-index: 5;
}
.lp-corner--tl { top: 80px; left: 36px; border-right: 0; border-bottom: 0; }
.lp-corner--tr { top: 80px; right: 36px; border-left: 0; border-bottom: 0; }
.lp-corner--bl { bottom: 72px; left: 36px; border-right: 0; border-top: 0; }
.lp-corner--br { bottom: 72px; right: 36px; border-left: 0; border-top: 0; }

/* 侧边刻度 */
.lp-side-ticks {
  position: absolute;
  left: 16px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  flex-direction: column;
  gap: 6px;
  pointer-events: none;
  z-index: 5;
}
.lp-side-tick {
  width: 8px;
  height: 1px;
  background: rgba(120,160,220,0.25);
}
.lp-side-tick--long {
  width: 14px;
  background: rgba(120,160,220,0.5);
}

/* 顶部/底部 chrome */
.lp-chrome-top,
.lp-chrome-bottom {
  position: absolute;
  left: 0;
  right: 0;
  display: flex;
  align-items: center;
  padding: 22px 40px;
  font-size: 12px;
  color: var(--lp-ink-2);
  z-index: 5;
  letter-spacing: 0.04em;
}
.lp-chrome-top {
  top: 0;
  justify-content: space-between;
}
.lp-chrome-bottom {
  bottom: 0;
  justify-content: space-between;
  border-top: 1px solid var(--lp-line);
}

/* 品牌 */
.lp-brand {
  display: flex;
  align-items: center;
  gap: 14px;
}
.lp-logo {
  width: 40px;
  height: 40px;
}
.lp-logo svg {
  width: 100%;
  height: 100%;
  display: block;
}
.lp-brand-name {
  display: flex;
  flex-direction: column;
  line-height: 1.1;
}
.lp-brand-cn {
  font-weight: 600;
  font-size: 16px;
  letter-spacing: 0.18em;
  color: var(--lp-ink-0);
}
.lp-brand-en {
  font-family: var(--lp-font-mono);
  font-weight: 500;
  font-size: 11px;
  letter-spacing: 0.32em;
  color: var(--lp-ink-2);
  margin-top: 4px;
  text-transform: uppercase;
}

/* meta 行 */
.lp-meta-row {
  display: flex;
  align-items: center;
  gap: 22px;
}
.lp-meta-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: var(--lp-ink-2);
  letter-spacing: 0.1em;
  font-family: var(--lp-font-mono);
}
.lp-meta-time {
  color: var(--lp-acc);
}
.lp-accent-val {
  color: var(--lp-ink-0);
}
.lp-status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--lp-acc);
  box-shadow: 0 0 8px var(--lp-acc);
  flex-shrink: 0;
}

/* 主体分栏 */
.lp-split {
  position: relative;
  display: grid;
  grid-template-columns: 1.05fr 1fr;
  width: 100%;
  height: 100%;
  padding-top: 60px;
  padding-bottom: 52px;
}

/* 左栏 */
.lp-pane-left {
  position: relative;
  padding: 28px 56px 24px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: 0;
  overflow: hidden;
}

/* 右栏 */
.lp-pane-right {
  position: relative;
  padding: 28px 56px 24px 0;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  min-height: 0;
}

/* 主文案区 */
.lp-hero {
  max-width: 560px;
}
.lp-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-size: 11px;
  letter-spacing: 0.3em;
  color: var(--lp-acc);
  text-transform: uppercase;
  padding: 6px 10px;
  border: 1px solid rgba(59,130,246,0.3);
  border-radius: 999px;
  background: rgba(59,130,246,0.06);
}
.lp-eyebrow-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--lp-acc);
  box-shadow: 0 0 12px var(--lp-acc);
  animation: lp-pulse 2.2s ease-in-out infinite;
  flex-shrink: 0;
}
@keyframes lp-pulse {
  0%,100% { opacity: 1 }
  50% { opacity: 0.35 }
}
.lp-h1 {
  font-weight: 600;
  font-size: clamp(30px, 3vw, 42px);
  line-height: 1.1;
  letter-spacing: -0.01em;
  margin: 16px 0 12px;
}
.lp-accent-text {
  background: linear-gradient(90deg, var(--lp-acc) 0%, var(--lp-acc-2) 70%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.lp-sub {
  color: var(--lp-ink-2);
  font-size: 13px;
  line-height: 1.7;
  max-width: 460px;
  margin: 0;
}

/* 环形图区域 */
.lp-viz {
  position: relative;
  flex: 1;
  margin: 6px 0;
  display: grid;
  place-items: center;
  min-height: 0;
}
.lp-rings {
  position: relative;
  width: min(320px, 26vw);
  aspect-ratio: 1 / 1;
}
.lp-rings svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

/* SVG 内部样式（非 scoped，通过全局写入 .lp-* 类）*/
:deep(.lp-ring-track) {
  fill: none;
  stroke: rgba(120,160,220,0.10);
  stroke-width: 1;
}
:deep(.lp-tick) {
  stroke: rgba(120,160,220,0.18);
  stroke-width: 1;
}
:deep(.lp-tick--major) {
  stroke: rgba(120,160,220,0.35);
}
:deep(.lp-svg-label-faint) {
  fill: var(--lp-ink-3);
  font-family: var(--lp-font-mono);
  font-size: 9px;
  letter-spacing: 0.06em;
}
:deep(.lp-svg-label-mono) {
  font-family: var(--lp-font-mono);
}

/* SVG 样式（scoped 无法作用到 SVG 内部 DOM，需通过属性直接写） */
.lp-stage :deep(.lp-ring-track) {
  fill: none;
  stroke: rgba(120,160,220,0.10);
  stroke-width: 1;
}

/* 中心数值 */
.lp-center-stat {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}
.lp-kw {
  font-family: var(--lp-font-mono);
  font-weight: 500;
  font-size: 44px;
  letter-spacing: -0.02em;
  color: var(--lp-ink-0);
  line-height: 1;
}
.lp-kw-unit {
  font-size: 18px;
  color: var(--lp-ink-2);
  margin-left: 4px;
  font-family: var(--lp-font-sans);
}
.lp-kw-sub {
  font-family: var(--lp-font-mono);
  font-size: 10px;
  color: var(--lp-ink-2);
  letter-spacing: 0.2em;
  margin-top: 6px;
}
.lp-kw-lbl {
  font-size: 10px;
  color: var(--lp-ink-3);
  letter-spacing: 0.3em;
  margin-top: 10px;
}

/* 浮动标签 */
.lp-floater {
  position: absolute;
  padding: 8px 12px;
  border: 1px solid var(--lp-line-2);
  border-radius: 8px;
  background: rgba(10,20,36,0.6);
  backdrop-filter: blur(8px);
  font-family: var(--lp-font-mono);
  font-size: 10px;
  color: var(--lp-ink-1);
  letter-spacing: 0.06em;
  display: flex;
  align-items: center;
  gap: 8px;
}
.lp-floater-lab { color: var(--lp-ink-3); }
.lp-floater-val { color: var(--lp-acc); }

/* metric 卡 */
.lp-metric-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-top: 10px;
}
.lp-metric {
  border: 1px solid var(--lp-line);
  background: linear-gradient(180deg, rgba(15,29,53,0.45), rgba(10,20,36,0.3));
  border-radius: 10px;
  padding: 12px 14px;
  position: relative;
  overflow: hidden;
}
.lp-metric::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 2px;
  background: var(--lp-mc, var(--lp-acc));
  box-shadow: 0 0 12px var(--lp-mc, var(--lp-acc));
}
.lp-metric-name {
  font-size: 11px;
  color: var(--lp-ink-2);
  letter-spacing: 0.18em;
}
.lp-metric-val {
  font-family: var(--lp-font-mono);
  font-weight: 500;
  font-size: 20px;
  color: var(--lp-ink-0);
  margin-top: 4px;
  letter-spacing: -0.01em;
}
.lp-metric-unit {
  font-size: 11px;
  color: var(--lp-ink-2);
  margin-left: 4px;
  font-family: var(--lp-font-mono);
}
.lp-metric-delta {
  font-family: var(--lp-font-mono);
  font-size: 10px;
  color: var(--lp-ink-2);
  margin-top: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.lp-delta-up { color: var(--lp-ok); }
.lp-delta-dn { color: var(--lp-heat); }
.lp-sparkline {
  width: 100%;
  height: 22px;
  margin-top: 6px;
}

/* ---- 登录卡 ---- */
/* AC-UI-001-03: 入场动画 500ms ease-out, translateY 20px → 0 */
.lp-card {
  width: 420px;
  max-width: 100%;
  background: linear-gradient(180deg, rgba(20,34,58,0.78), rgba(10,20,36,0.72));
  border: 1px solid var(--lp-line-2);
  border-radius: 16px;
  padding: 36px 36px 30px;
  backdrop-filter: blur(18px) saturate(140%);
  -webkit-backdrop-filter: blur(18px) saturate(140%);
  box-shadow:
    0 30px 80px -30px rgba(0,0,0,0.6),
    0 0 0 1px rgba(120,160,220,0.04) inset,
    0 1px 0 rgba(255,255,255,0.04) inset;
  position: relative;
  animation: lp-card-enter 500ms ease-out both;
}
@keyframes lp-card-enter {
  from { opacity: 0; transform: translateY(20px); }
  to   { opacity: 1; transform: translateY(0); }
}
/* 渐变边框装饰 */
.lp-card::before {
  content: "";
  position: absolute;
  inset: -1px;
  border-radius: 16px;
  padding: 1px;
  background: linear-gradient(140deg, rgba(59,130,246,0.45) 0%, rgba(34,211,238,0) 35%, rgba(96,165,250,0.25) 100%);
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  pointer-events: none;
}

.lp-card-head {
  margin-bottom: 28px;
}
.lp-card-title {
  font-size: 20px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--lp-ink-0);
}
.lp-card-sub {
  font-size: 12px;
  color: var(--lp-ink-3);
  margin-top: 4px;
  letter-spacing: 0.16em;
  font-family: var(--lp-font-mono);
}

/* 字段标签 */
.lp-field-label {
  font-size: 11px;
  color: var(--lp-ink-2);
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

/* 输入框外壳（包裹 el-input + icon）*/
.lp-input-wrap {
  position: relative;
  display: flex;
  align-items: center;
  background: rgba(5,10,20,0.5);
  border: 1px solid var(--lp-line);
  border-radius: 10px;
  padding: 0 14px;
  height: 48px;
  transition: border-color 0.2s, box-shadow 0.2s;
  width: 100%;
}
.lp-input-wrap--focus {
  border-color: rgba(59,130,246,0.6);
  box-shadow: 0 0 0 4px rgba(59,130,246,0.1);
}
.lp-input-icon {
  color: var(--lp-ink-3);
  margin-right: 10px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}

/* el-input 内部深度覆盖 —— 深色主题适配 */
.lp-input-wrap :deep(.el-input) {
  flex: 1;
  --el-input-bg-color: transparent;
  --el-input-border-color: transparent;
  --el-input-hover-border-color: transparent;
  --el-input-focus-border-color: transparent;
  --el-input-text-color: var(--lp-ink-0);
  --el-input-placeholder-color: var(--lp-ink-3);
}
.lp-input-wrap :deep(.el-input__wrapper) {
  background: transparent !important;
  box-shadow: none !important;
  padding: 0;
}
.lp-input-wrap :deep(.el-input__wrapper.is-focus) {
  box-shadow: none !important;
}
.lp-input-wrap :deep(.el-input__inner) {
  color: var(--lp-ink-0);
  font-size: 14px;
  letter-spacing: 0.02em;
  font-family: var(--lp-font-sans);
  background: transparent;
  height: 100%;
  line-height: normal;
}
.lp-input-wrap :deep(.el-input__inner::placeholder) {
  color: var(--lp-ink-3);
}
/* 隐藏 el-input 自带的前缀/后缀 icon 区域（我们用外部图标）*/
.lp-input-wrap :deep(.el-input__prefix),
.lp-input-wrap :deep(.el-input__suffix) {
  display: none;
}

/* el-form-item label 区域 */
.lp-card :deep(.el-form-item__label) {
  color: var(--lp-ink-2);
  font-size: 11px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  line-height: 1;
  margin-bottom: 10px;
}
.lp-card :deep(.el-form-item) {
  margin-bottom: 18px;
}
.lp-card :deep(.el-form-item__error) {
  color: var(--lp-heat);
  font-size: 11px;
  padding-top: 4px;
}

/* 密码切换按钮 */
.lp-pw-toggle {
  background: transparent;
  border: 0;
  color: var(--lp-ink-3);
  cursor: pointer;
  padding: 4px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  transition: color 0.15s;
}
.lp-pw-toggle:hover { color: var(--lp-ink-1); }

/* 错误提示 */
.lp-error-msg {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--lp-heat);
  font-size: 12px;
  margin-bottom: 14px;
  padding: 8px 12px;
  background: rgba(240,80,110,0.08);
  border-radius: 8px;
  border: 1px solid rgba(240,80,110,0.2);
}

/* remember / 忘记密码行 */
.lp-row-between {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 4px 0 22px;
}
.lp-check {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--lp-ink-2);
  font-size: 12px;
  cursor: pointer;
  user-select: none;
}
.lp-check input[type="checkbox"] {
  appearance: none;
  -webkit-appearance: none;
  width: 14px;
  height: 14px;
  border-radius: 3px;
  border: 1px solid var(--lp-line-2);
  background: rgba(5,10,20,0.5);
  display: grid;
  place-items: center;
  cursor: pointer;
  flex-shrink: 0;
  transition: background 0.15s, border-color 0.15s;
}
.lp-check input[type="checkbox"]:checked {
  background: var(--lp-acc);
  border-color: var(--lp-acc);
}
.lp-check input[type="checkbox"]:checked::after {
  content: "";
  width: 8px;
  height: 4px;
  border-left: 2px solid #06121f;
  border-bottom: 2px solid #06121f;
  transform: rotate(-45deg) translate(0px, -1px);
}
.lp-link {
  color: var(--lp-acc);
  font-size: 12px;
  text-decoration: none;
  letter-spacing: 0.04em;
  transition: text-decoration 0.15s;
}
.lp-link:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}

/* 登录按钮 */
.lp-btn-primary {
  width: 100%;
  height: 48px;
  border-radius: 10px;
  border: 0;
  cursor: pointer;
  background: linear-gradient(90deg, var(--lp-acc) 0%, var(--lp-acc-2) 100%);
  color: #06182a;
  font-weight: 600;
  font-size: 14px;
  letter-spacing: 0.2em;
  font-family: var(--lp-font-sans);
  position: relative;
  overflow: hidden;
  transition: transform 0.15s, box-shadow 0.2s, opacity 0.15s;
  box-shadow: 0 10px 30px -10px rgba(59,130,246,0.55), 0 0 0 1px rgba(59,130,246,0.4) inset;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.lp-btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 16px 36px -12px rgba(59,130,246,0.7), 0 0 0 1px rgba(59,130,246,0.5) inset;
}
.lp-btn-primary:active:not(:disabled) {
  transform: scale(0.98);
}
.lp-btn-primary:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}
.lp-btn-arrow {
  margin-left: 10px;
  display: inline-flex;
  transition: transform 0.2s;
}
.lp-btn-primary:hover:not(:disabled) .lp-btn-arrow {
  transform: translateX(4px);
}
/* loading 旋转器 */
.lp-btn-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(6,24,42,0.3);
  border-top-color: #06182a;
  border-radius: 50%;
  animation: lp-spin 0.7s linear infinite;
  display: inline-block;
}
@keyframes lp-spin {
  to { transform: rotate(360deg); }
}

/* 卡片底部 */
.lp-card-foot {
  margin-top: 22px;
  padding-top: 18px;
  border-top: 1px solid var(--lp-line);
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 10px;
  color: var(--lp-ink-3);
  letter-spacing: 0.08em;
  white-space: nowrap;
}
.lp-mono {
  font-family: var(--lp-font-mono);
}

/* ---- 响应式：<1100px 单栏，隐藏装饰区 ---- */
@media (max-width: 1100px) {
  .lp-split {
    grid-template-columns: 1fr;
  }
  .lp-pane-left {
    padding: 40px 32px 12px;
    /* 移动端隐藏整个左栏（仅有品牌文案，无环形图）*/
    display: none;
  }
  .lp-pane-right {
    padding: 0 32px 40px;
    justify-content: center;
    grid-column: 1;
  }
  .lp-viz {
    display: none;
  }
  /* 移动端 chrome 简化 */
  .lp-chrome-top .lp-meta-row {
    display: none;
  }
  .lp-corner--tr,
  .lp-corner--br {
    display: none;
  }
}
</style>
