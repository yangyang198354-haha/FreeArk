<!--
  @module MOD-1120-FE-02
  @author Claude (v1.14.0 参数设置页·赛博朋克 HOLO-HUD 视觉改版)
  @depends MOD-1110-FE-01 (useMqttClient.js), MOD-1120-FE-01 (paramPanels.js),
           MOD-API (api.js: getDeviceSettingsConfig / getOwnerStructure / reportDeviceSettingsAudit)
  @description 业主端·参数设置。v1.14.0 在 v1.13 卡片流之上落地「HOLO-HUD」赛博朋克视觉：
      · 全屏 HUD 背景层（网格漂移 + 扫描线扫过 + 细扫描线纹理），固定不随滚动。
      · 设备卡 = 暗玻璃 + 霓虹描边 + 四角 HUD 括号 + 呼吸辉光；青/紫按序交替（节奏感）。
      · 指标 = 双列大字霓虹读数（温度等只读读数）。
      · 顶部连接条带「均衡器」动效条 + LINK 状态药丸。
      · 控件（模式药丸 / 风速分段 / 加湿开关 / 温度步进）沿用点选即生效写链路，零语义变更。

    数据/写链路（结构骨架 owner/structure → MQTT 实时值 → buildCard → 点选即生效去抖下发 →
    写确认 → 审计）完全继承 v1.13.0，本次仅视觉与两个纯展示辅助函数（cardCode/cardEnLabel）。
    字体：不依赖远程 Web 字体（小程序域名白名单不稳），用系统等宽栈 + 字距营造科技感。
-->
<template>
  <view class="ps-page">

    <!-- ── 赛博朋克背景层（与 profile/chat 一致：bg-base 径向渐变 + bg-grid 网格）── -->
    <view class="bg-base" />
    <view class="bg-grid" />

    <!-- HUD 装饰层（保留扫描线动效，作为参数设置页特色）─────────────────── -->
    <view class="hud-scan"></view>

    <!-- 状态栏占位（custom 导航）-->
    <view :style="{ height: statusBarHeight + 'px' }" class="status-spacer" />

    <!-- 自绘头（与 profile/chat 一致，无系统返回箭头，靠底栏 ArkTabBar 切换）-->
    <view class="ps-header">
      <text class="ps-header-title">参数设置</text>
    </view>

    <scroll-view scroll-y class="ps-content">

      <view v-if="loading" class="tip"><text>加载中…</text></view>

      <view v-else-if="rooms.length === 0" class="tip">
        <text>您还没有绑定专有部分</text>
        <view class="link-btn" @tap="goBind"><text>去绑定</text></view>
      </view>

      <template v-else>
        <!-- 套户选择条（多套户=选择器；单套户=名称）+ 连接状态药丸 + 均衡器动效 -->
        <view class="unit-bar">
          <view class="unit-main">
            <text class="unit-label">PROPERTY</text>
            <picker v-if="rooms.length > 1" :range="roomLabels" :value="roomIndex" @change="onRoomChange">
              <view class="unit-pick">{{ currentRoom ? (currentRoom.location_name || currentRoom.specific_part) : '请选择' }} ›</view>
            </picker>
            <text v-else-if="currentRoom" class="unit-single">{{ currentRoom.location_name || currentRoom.specific_part }}</text>
          </view>
          <view class="conn-side">
            <view class="eq" :class="{ live: mqttConnected }">
              <view class="eq-bar" v-for="n in 6" :key="n" :style="'animation-delay:' + (n * 0.12) + 's'"></view>
            </view>
            <view class="conn-pill" :class="{ on: mqttConnected }">
              <view class="conn-led"></view>
              <text class="conn-txt">{{ mqttConnected ? 'LINK · OK' : 'LINK · …' }}</text>
            </view>
          </view>
        </view>

        <!-- 结构骨架加载中（无任何缓存可渲染）-->
        <view v-if="curStructureLoading && !curStructure" class="tip"><text>正在获取设备结构…</text></view>

        <!-- 设备树未同步（sync_status=pending）-->
        <view v-else-if="curSyncPending" class="tip">
          <text>您的房间结构尚未就绪，请等待设备初始化后再试</text>
          <view class="link-btn" @tap="reloadStructure"><text>重试</text></view>
        </view>

        <!-- 结构加载失败且无缓存可降级 -->
        <view v-else-if="curError && !curStructure" class="tip">
          <text>{{ curError }}</text>
          <view class="link-btn" @tap="reloadStructure"><text>重试</text></view>
        </view>

        <!-- 结构就绪但无设备 -->
        <view v-else-if="cards.length === 0" class="tip"><text>当前房产暂无设备信息</text></view>

        <!-- 设备卡片流（HOLO-HUD，纵向排列，青/紫交替）-->
        <template v-else>
          <view
            v-for="(card, ci) in cards"
            :key="card.id"
            class="dev-card"
            :class="{ alt: ci % 2 === 1 }"
          >
            <!-- 四角 HUD 括号 -->
            <view class="bk bk-tl"></view>
            <view class="bk bk-tr"></view>
            <view class="bk bk-bl"></view>
            <view class="bk bk-br"></view>

            <!-- 头部：图标 + 名称/编号 + 主开关 -->
            <view class="card-head">
              <view class="card-icon"><text>{{ cardIcon(card) }}</text></view>
              <view class="card-id">
                <text class="card-title">{{ card.title }}</text>
                <text class="card-code">{{ cardEnLabel(card) }} · {{ cardCode(card) }}</text>
              </view>
              <switch
                v-if="card.switchCtl"
                class="card-switch"
                color="#00e5ff"
                :checked="curVal(card.switchCtl.sn, card.switchCtl.w.tag) === 'on'"
                @change="onToggle(ctlDev(card.switchCtl), card.switchCtl.w.tag, $event)"
              />
            </view>

            <!-- 指标区：ring gauge / 进度条 / 大字 / 普通 chip（分栏在 buildCard 预计算）─── -->
            <view v-if="card.small.length">
              <!-- HUD 分栏：左列主视觉 + 右列其余；两列均按指标 displayType 自描述渲染 -->
              <view v-if="card.hudLayout" class="metric-hud">
                <view v-if="card.metricsLeft.length" class="mhud-left">
                  <view v-for="m in card.metricsLeft" :key="m.tag" class="mcell">
                    <!-- 环形 gauge（温度 / 滤网时长）：ucharts arcbar 270° 渐变描边 -->
                    <RingGauge
                      v-if="m.displayType === 'ring'"
                      :canvas-id="ringId(card, m)"
                      :progress="m.progressPct"
                      :num-text="m.numText"
                      :unit-text="m.unitText"
                      :top-label="m.label"
                      :sub="m.tag === 'temp' ? setptText(m) : ''"
                      :alt="ci % 2 === 1"
                    />
                    <!-- 大字展示（如新风送风温度）-->
                    <view v-else-if="m.displayType === 'big'" class="big-metric">
                      <text class="big-lbl">{{ m.label }}</text>
                      <view class="big-val-row">
                        <text class="big-num">{{ m.numText }}</text>
                        <text class="big-unt">{{ m.unitText }}</text>
                      </view>
                    </view>
                    <!-- 进度条 -->
                    <view v-else-if="m.displayType === 'bar'" class="bar-metric">
                      <view class="bar-head">
                        <text class="bar-lbl">{{ m.label }}</text>
                        <text class="bar-val" :class="{ pink: m.tag === 'dew_point_temp' }">{{ m.value }}</text>
                      </view>
                      <view class="bar-track"><view class="bar-fill" :class="{ pink: m.tag === 'dew_point_temp' }" :style="'width: ' + m.progressPct + '%'"></view></view>
                    </view>
                    <!-- 文字 chip -->
                    <view v-else class="metric-chip">
                      <text class="metric-lbl">{{ m.label }}</text>
                      <text class="metric-val">{{ m.value }}</text>
                    </view>
                  </view>
                </view>
                <view v-if="card.metricsRight.length" class="mhud-right">
                  <view v-for="m in card.metricsRight" :key="m.tag" class="mcell">
                    <RingGauge
                      v-if="m.displayType === 'ring'"
                      :canvas-id="ringId(card, m)"
                      :progress="m.progressPct"
                      :num-text="m.numText"
                      :unit-text="m.unitText"
                      :top-label="m.label"
                      :sub="m.tag === 'temp' ? setptText(m) : ''"
                      :alt="ci % 2 === 1"
                    />
                    <view v-else-if="m.displayType === 'big'" class="big-metric">
                      <text class="big-lbl">{{ m.label }}</text>
                      <view class="big-val-row">
                        <text class="big-num">{{ m.numText }}</text>
                        <text class="big-unt">{{ m.unitText }}</text>
                      </view>
                    </view>
                    <view v-else-if="m.displayType === 'bar'" class="bar-metric">
                      <view class="bar-head">
                        <text class="bar-lbl">{{ m.label }}</text>
                        <text class="bar-val" :class="{ pink: m.tag === 'dew_point_temp' }">{{ m.value }}</text>
                      </view>
                      <view class="bar-track"><view class="bar-fill" :class="{ pink: m.tag === 'dew_point_temp' }" :style="'width: ' + m.progressPct + '%'"></view></view>
                    </view>
                    <view v-else class="metric-chip">
                      <text class="metric-lbl">{{ m.label }}</text>
                      <text class="metric-val">{{ m.value }}</text>
                    </view>
                  </view>
                </view>
              </view>
              <!-- 纯文字 chip：无 ring/big/bar（主机等双列大字 chip 网格）-->
              <view v-else class="metric-row">
                <view v-for="m in card.small" :key="m.tag" class="metric-chip">
                  <text class="metric-lbl">{{ m.label }}</text>
                  <text class="metric-val">{{ m.value }}</text>
                </view>
              </view>
            </view>

            <!-- 主机运行波形示波器（ucharts line，横向滚动青色波形）-->
            <WaveScope v-if="card.title === '主机'" :canvas-id="waveId(card)" />

            <!-- 可写控件（点选即生效）-->
            <view v-if="card.controls.length" class="ctl-area">
              <view v-for="c in card.controls" :key="c.sn + '-' + c.w.tag">

                <!-- 运行模式：图标药丸（点选即生效，当前态高亮发光）-->
                <view v-if="c.w.control === 'pills'" class="mode-block">
                  <text class="ctl-label">{{ c.w.label }}</text>
                  <view class="mode-pills">
                    <view
                      v-for="opt in c.w.options"
                      :key="opt.value"
                      class="mode-pill"
                      :class="{ on: curVal(c.sn, c.w.tag) === opt.value }"
                      @tap="onPickDot(ctlDev(c), c.w, opt.value)"
                    >
                      <view class="mode-dot"></view>
                      <text class="mode-txt">{{ opt.label }}</text>
                    </view>
                  </view>
                </view>

                <!-- 分段控件（如风速 select）：标签在上，全宽矩形分段在下 -->
                <view v-else-if="c.w.control === 'select'" class="seg-block">
                  <text class="ctl-label">{{ c.w.label }}</text>
                  <view class="seg">
                    <view
                      v-for="opt in c.w.options"
                      :key="opt.value"
                      class="seg-item"
                      :class="{ on: curVal(c.sn, c.w.tag) === opt.value }"
                      @tap="onPickDot(ctlDev(c), c.w, opt.value)"
                    ><text>{{ opt.label }}</text></view>
                  </view>
                </view>

                <!-- 开关 -->
                <view v-else-if="c.w.control === 'toggle'" class="ctl-row">
                  <text class="ctl-label">{{ c.w.label }}</text>
                  <switch color="#00e5ff" :checked="curVal(c.sn, c.w.tag) === 'on'" @change="onToggle(ctlDev(c), c.w.tag, $event)" />
                </view>

                <!-- 数值步进 -->
                <view v-else-if="c.w.control === 'number'" class="ctl-block">
                  <text class="ctl-label">{{ c.w.label }}</text>
                  <view class="num-ctl">
                    <view class="num-btn" @tap="onStep(ctlDev(c), c.w, -1)">−</view>
                    <view class="num-val">
                      <text class="num-num">{{ curVal(c.sn, c.w.tag) ?? '—' }}</text>
                      <text v-if="c.w.unit" class="num-unit">{{ c.w.unit }}</text>
                    </view>
                    <view class="num-btn" @tap="onStep(ctlDev(c), c.w, 1)">＋</view>
                  </view>
                </view>

              </view>
            </view>

            <!-- 查看全部（其余只读读数，展开/收起，不跳页）-->
            <view v-if="card.rest.length" class="more-row" @tap="toggleExpand(card.id)">
              <text class="more-txt">{{ expanded[card.id] ? '收起' : '查看全部 ' + card.rest.length + ' 项' }}</text>
              <text class="more-arrow">{{ expanded[card.id] ? '▲' : '›' }}</text>
            </view>
            <view v-if="expanded[card.id]" class="rest-list">
              <view v-for="r in card.rest" :key="r.tag" class="rest-row">
                <text class="rest-name">{{ r.label }}</text>
                <text class="rest-val">{{ r.value }}</text>
              </view>
            </view>

            <!-- 空卡占位（无开关/控件/指标/读数，连接中先撑住）-->
            <view
              v-if="!card.switchCtl && !card.controls.length && !card.small.length && !card.rest.length"
              class="empty-tip"
            >
              <text>{{ mqttConnected ? '采集中…' : '设备未上报' }}</text>
            </view>

          </view>
        </template>
      </template>

    </scroll-view>

    <!-- 底栏（4-Tab）：与 profile/chat/home 一致，替代系统返回箭头 -->
    <ArkTabBar active="device" />
  </view>
</template>

<script setup>
/**
 * @module MOD-1120-FE-02
 * @depends MOD-1110-FE-01 (useMqttClient), MOD-1120-FE-01 (paramPanels)
 */
import { ref, computed, reactive } from 'vue'
import { onLoad, onShow, onUnload } from '@dcloudio/uni-app'
import { useAuthStore } from '@/store/auth'
import { api } from '@/utils/api'
import { buildWriteItems } from '@/utils/screenMqtt'
import { useMqttClient } from '@/utils/useMqttClient'
import { buildPanels, buildCard } from '@/utils/paramPanels'
import RingGauge from '@/components/RingGauge.vue'
import WaveScope from '@/components/WaveScope.vue'
import ArkTabBar from '@/components/ArkTabBar.vue'

const authStore = useAuthStore()
const mqttClient = useMqttClient()

const sysInfo = uni.getSystemInfoSync()
const statusBarHeight = sysInfo.statusBarHeight || 20

// ── 配置 / 套户 / MQTT 实时值 state ──────────────────────────────────────────
const loading = ref(true)
const rooms = ref([])               // config.rooms：[{specific_part, location_name, screen_mac}]
const roomIndex = ref(0)
const broker = ref(null)
const topics = ref(null)
const config = ref({ writable_attrs: {}, readonly_attrs: {}, product_code_role: {}, mode_energy_link: {}, link_product_codes: [] })

const devices = reactive({})        // deviceSn → {productCode, attrs:{tag:val}}（MQTT 实时值）
const edits = reactive({})          // deviceSn → {tag: newVal}（待下发）
const applyingSn = ref('')
const mqttConnected = computed(() => mqttClient.connected.value)

let knownSns = new Set()
let _offDeviceUpdate = null

const currentRoom = computed(() => rooms.value[roomIndex.value] || null)
const roomLabels = computed(() => rooms.value.map((r) => r.location_name || r.specific_part))

// ── 结构骨架 state（按 specific_part）───────────────────────────────────────
const partState = reactive({})      // sp → {structure, structureLoading, errorMsg}

/** 结构缓存 TTL：30 天（OQ-03，硬件结构基本不变）；sync_status=pending 时 5 分钟。 */
const STRUCT_TTL_MS = 30 * 24 * 60 * 60 * 1000
const STRUCT_TTL_PENDING_MS = 5 * 60 * 1000

function _initPartState(sp) {
  if (!partState[sp]) {
    partState[sp] = { structure: null, structureLoading: false, errorMsg: null }
  }
}

// ── 当前套户视图（结构状态 + 卡片）────────────────────────────────────────────
const curPart = computed(() => {
  const sp = currentRoom.value?.specific_part
  return sp ? partState[sp] : null
})
const curStructure = computed(() => curPart.value?.structure || null)
const curStructureLoading = computed(() => !!curPart.value?.structureLoading)
const curSyncPending = computed(() => curStructure.value?.sync_status === 'pending')
const curError = computed(() => curPart.value?.errorMsg || '')

const panels = computed(() => buildPanels(curStructure.value, config.value))

// 屏端实时值（sn → attrs）快照，供 buildCard 读取突出指标 / 查看全部；devices 变更即重算。
const attrsBySn = computed(() => {
  const m = {}
  for (const sn of Object.keys(devices)) m[sn] = devices[sn].attrs
  return m
})
// 面板 → 卡片视图模型（结构 + 实时值合成）。
const cards = computed(() => panels.value.map((p) => buildCard(p, attrsBySn.value, config.value)))

// ── 「查看全部」展开态（cardId → bool）─────────────────────────────────────────
const expanded = reactive({})
function toggleExpand(id) { expanded[id] = !expanded[id] }

// 控件 slot（{sn,productCode,w}）→ 写链路所需的轻量 dev 对象（deviceSn/productCode）。
function ctlDev(c) { return { deviceSn: c.sn, productCode: c.productCode } }

// ── HOLO-HUD 纯展示辅助（不参与数据/写链路）──────────────────────────────────
// 卡片副标题编号：优先取真实 device_sn（房间面板 id=room-{room_id}，room_id 常 <100 位，
//   靠 card.id 正则抽数字会命不中→显示「—」，用户反馈儿童房/次卧/书房等只显示「—」即此坑）。
//   优先级：switchCtl.sn → 首个控件.sn → 首个指标.sn → 兜底从 card.id 抽数字。
function cardCode(card) {
  const sn = (card && card.switchCtl && card.switchCtl.sn)
    || (card && card.controls && card.controls[0] && card.controls[0].sn)
    || (card && card.small && card.small[0] && card.small[0].sn)
    || ''
  if (sn) return String(sn)
  const m = String((card && card.id) || '').match(/(\d{3,})/)
  return m ? m[1] : '—'
}
// 卡片铭牌（对齐设计稿）：英文副标题 + 头部 2 字母 monogram（取代 emoji）。
// monogram 为设计稿手选缩写（HOST→HC / FRESH-AIR→FA / MASTER-BEDROOM→MB …），
//   未命中的房间走通用 ROOM/RM 兜底（真机 HUD 一致，不臆造业务含义）。
const CARD_META = {
  '主机':   { en: 'HOST',           mono: 'HC' },
  '新风':   { en: 'FRESH-AIR',      mono: 'FA' },
  '客厅':   { en: 'LIVING-ROOM',    mono: 'LR' },
  '主卧':   { en: 'MASTER-BEDROOM', mono: 'MB' },
  '次卧':   { en: '2ND-BEDROOM',    mono: 'BR' },
  '书房':   { en: 'STUDY',          mono: 'ST' },
  '儿童房': { en: 'KIDS-ROOM',      mono: 'KR' },
  '能耗表': { en: 'ENERGY',         mono: 'EN' },
  '空气质量': { en: 'AIR-QUALITY',  mono: 'AQ' },
  '餐厅':   { en: 'DINING-ROOM',    mono: 'DR' },
  '厨房':   { en: 'KITCHEN',        mono: 'KT' },
  '卫生间': { en: 'BATHROOM',       mono: 'BA' },
  '主卫':   { en: 'MASTER-BATH',    mono: 'MW' },
  '次卫':   { en: '2ND-BATH',       mono: 'BW' },
  '阳台':   { en: 'BALCONY',        mono: 'BC' },
  '老人房': { en: 'ELDER-ROOM',     mono: 'ER' },
  '茶室':   { en: 'TEA-ROOM',       mono: 'TR' },
  '衣帽间': { en: 'CLOAKROOM',      mono: 'CR' },
  '玄关':   { en: 'FOYER',          mono: 'FY' },
  '过道':   { en: 'HALLWAY',        mono: 'HW' },
}
function cardMeta(card) { return (card && CARD_META[card.title]) || { en: 'ROOM', mono: 'RM' } }
function cardEnLabel(card) { return cardMeta(card).en }
function cardIcon(card) { return cardMeta(card).mono }

// ── ucharts 画布辅助（环形 gauge / 运行波形）──────────────────────────────────
// canvas-id 须页面内唯一且合法（mp-weixin 仅允许 字母/数字/-/_）。card.id 唯一 → 稳定不撞。
function ringId(card, m) { return ('rg-' + String(card.id) + '-' + m.tag).replace(/[^A-Za-z0-9_-]/g, '-') }
function waveId(card) { return ('wave-' + String(card.id)).replace(/[^A-Za-z0-9_-]/g, '-') }
// 温度 ring 圆心第三行：当前设定温度（写链路读 temp_set）。
function setptText(m) {
  const v = curVal(m.sn, 'temp_set')
  return '设定 ' + (v !== undefined && v !== null && v !== '' ? v : '—') + '°C'
}

// ── 控件读写（写链路继承 v1.10.0，零语义变更）────────────────────────────────
function curVal(sn, tag) {
  if (edits[sn] && edits[sn][tag] !== undefined) return edits[sn][tag]
  return devices[sn] ? devices[sn].attrs[tag] : undefined
}
function hasPending(sn) {
  return edits[sn] && Object.keys(edits[sn]).length > 0
}
function setEdit(sn, tag, val) {
  if (!edits[sn]) edits[sn] = {}
  edits[sn][tag] = val
}
function onToggle(dev, tag, e) {
  setEdit(dev.deviceSn, tag, e.detail.value ? 'on' : 'off')
  scheduleFlush(dev)
}
function onPickDot(dev, w, value) {
  if (curVal(dev.deviceSn, w.tag) === value) return  // 点当前态不重复下发（圆点 / 分段 chips 共用）
  setEdit(dev.deviceSn, w.tag, value)
  scheduleFlush(dev)
}
function onStep(dev, w, dir) {
  const cur = parseFloat(curVal(dev.deviceSn, w.tag))
  let base = isNaN(cur) ? (w.min ?? 0) : cur
  let next = base + dir * (w.step || 1)
  if (w.min !== undefined) next = Math.max(w.min, next)
  if (w.max !== undefined) next = Math.min(w.max, next)
  next = Number.isInteger(w.step) ? String(next) : next.toFixed(1)
  setEdit(dev.deviceSn, w.tag, String(next))
  scheduleFlush(dev)   // 数值连点会被去抖合并（见 scheduleFlush）
}

// 点选即生效：控件变更后去抖 600ms 自动下发该设备的待发改动（替代「下发更改」按钮）。
// 去抖让数值步进连点合并为一次写，避免刷屏式下发。
const _flushTimers = {}
function scheduleFlush(dev) {
  const sn = dev.deviceSn
  if (_flushTimers[sn]) clearTimeout(_flushTimers[sn])
  _flushTimers[sn] = setTimeout(() => {
    delete _flushTimers[sn]
    applyDevice(dev)
  }, 600)
}

async function applyDevice(dev) {
  const sn = dev.deviceSn
  const room = currentRoom.value
  if (!mqttClient.connected.value || !room) {
    uni.showToast({ title: '通道未连接', icon: 'none' }); return
  }
  if (!hasPending(sn)) return
  if (applyingSn.value) { scheduleFlush(dev); return }  // 有写在途，稍后重排，勿丢改动
  applyingSn.value = sn
  const pending = { ...edits[sn] }
  const auditItems = []
  let okCount = 0, failCount = 0

  for (const tag of Object.keys(pending)) {
    const target = pending[tag]
    const oldVal = devices[sn] ? devices[sn].attrs[tag] : ''
    const items = buildWriteItems(dev.productCode, tag, target, config.value)
    try {
      mqttClient.publishWrite(room.screen_mac, sn, items)
      await mqttClient.waitConfirm(sn, tag, target, 8000)
      okCount++
      items.forEach((it) => auditItems.push({ attr_tag: it.attrTag, attr_value: it.attrValue, old_value: it.attrTag === tag ? String(oldVal ?? '') : '' }))
      if (edits[sn]) delete edits[sn][tag]
    } catch (e) {
      failCount++
      items.forEach((it) => auditItems.push({ attr_tag: it.attrTag, attr_value: it.attrValue, old_value: '' }))
    }
  }

  if (auditItems.length > 0) {
    try {
      await api.reportDeviceSettingsAudit({
        request_id: 'mp-' + Date.now(),
        specific_part: room.specific_part,
        screen_mac: room.screen_mac,
        device_sn: sn,
        result: failCount === 0 ? 'success' : (okCount === 0 ? 'timeout' : 'success'),
        items: auditItems,
      })
    } catch (e) { /* 静默 */ }
  }

  applyingSn.value = ''
  // 成功不再弹「已生效」系统提示（点选即生效，避免每次设置都打扰）；仅失败/部分成功时反馈。
  if (failCount > 0 && okCount === 0) uni.showToast({ title: '未确认，请重试', icon: 'none' })
  else if (failCount > 0) uni.showToast({ title: `部分成功（${okCount}/${okCount + failCount}）`, icon: 'none' })

  // 在途写期间若又产生新改动，排一次后续 flush 以排空（点选即生效语义）
  if (hasPending(sn)) scheduleFlush(dev)
}

// ── 套户切换 ─────────────────────────────────────────────────────────────────
function onRoomChange(e) {
  selectUnit(Number(e.detail.value))
}

async function selectUnit(idx) {
  roomIndex.value = idx
  const sp = currentRoom.value?.specific_part
  if (!sp) return
  _initPartState(sp)
  await loadStructure(sp)   // 缓存优先即时渲染；缓存未命中时 await 网络
  await connectRoom()       // 用结构 device_sns 主动拉取 MQTT 实时值
}

// ── 配置加载 + MQTT 连接 ─────────────────────────────────────────────────────
async function loadConfig() {
  loading.value = true
  try {
    const res = await api.getDeviceSettingsConfig()
    broker.value = res.broker
    topics.value = res.topics
    config.value = res.config || config.value
    rooms.value = res.rooms || []
    if (rooms.value.length > 0) await selectUnit(0)
  } catch (err) {
    uni.showToast({ title: '加载配置失败，请重试', icon: 'none' })
  } finally {
    loading.value = false
  }
}

async function connectRoom() {
  const room = currentRoom.value
  if (!room || !room.screen_mac) return

  // 切换套户：清空旧设备/编辑状态
  Object.keys(devices).forEach((k) => delete devices[k])
  Object.keys(edits).forEach((k) => delete edits[k])
  knownSns = new Set()
  if (_offDeviceUpdate) { _offDeviceUpdate(); _offDeviceUpdate = null }

  const mac = room.screen_mac
  const sp = room.specific_part

  _offDeviceUpdate = mqttClient.onDeviceUpdate((p) => {
    const prev = devices[p.deviceSn] || { productCode: p.productCode, attrs: {} }
    devices[p.deviceSn] = {
      productCode: p.productCode != null ? p.productCode : prev.productCode,
      attrs: { ...prev.attrs, ...p.attrs },
    }
    const sn = String(p.deviceSn)
    if (!knownSns.has(sn)) { knownSns.add(sn); persistSns(mac) }
  })

  try {
    await mqttClient.acquire(broker.value, topics.value)
    mqttClient.subscribe(mac)
    const allSns = _discoverSns(sp, mac)
    if (allSns.length > 0) {
      allSns.forEach((s) => knownSns.add(s))
      mqttClient.publishRead(mac, allSns)
    }
  } catch (e) {
    uni.showToast({ title: '设备通道连接失败：' + (e && e.message || ''), icon: 'none' })
  }
}

/** 设备 SN 发现：结构骨架 device_sns 优先，回退结构缓存，再回退遗留 SN 缓存。 */
function _discoverSns(sp, mac) {
  const struct = partState[sp]?.structure
  if (struct && Array.isArray(struct.device_sns) && struct.device_sns.length > 0) {
    return struct.device_sns.map(String)
  }
  const { data: cached } = readStructureCache(sp)
  if (cached && Array.isArray(cached.device_sns) && cached.device_sns.length > 0) {
    return cached.device_sns.map(String)
  }
  return loadSns(mac)
}

// 遗留 SN 缓存（按 screenMac，v1.11.0 兼容降级）
const snCacheKey = (mac) => `ds_sns_${mac}`
function loadSns(mac) {
  try { const a = uni.getStorageSync(snCacheKey(mac)); return Array.isArray(a) ? a.map(String) : [] } catch (e) { return [] }
}
function persistSns(mac) {
  try { uni.setStorageSync(snCacheKey(mac), Array.from(knownSns)) } catch (e) { /* ignore */ }
}

// ── 结构骨架缓存（owner_structure_{sp}，TTL 30 天）────────────────────────────
function writeStructureCache(sp, data) {
  try {
    const ttlMs = data && data.sync_status === 'pending' ? STRUCT_TTL_PENDING_MS : STRUCT_TTL_MS
    uni.setStorageSync(`owner_structure_${sp}`, JSON.stringify(data))
    uni.setStorageSync(`owner_structure_${sp}_ts`, new Date().toISOString())
    uni.setStorageSync(`owner_structure_${sp}_ttl`, ttlMs)
  } catch (e) {
    console.warn('[param-settings] writeStructureCache 失败:', e)
  }
}

function readStructureCache(sp) {
  try {
    const raw = uni.getStorageSync(`owner_structure_${sp}`)
    const tsRaw = uni.getStorageSync(`owner_structure_${sp}_ts`)
    const ttlMs = uni.getStorageSync(`owner_structure_${sp}_ttl`) || STRUCT_TTL_MS
    const data = raw ? JSON.parse(raw) : null
    const ts = tsRaw ? new Date(tsRaw) : null
    const expired = ts ? (Date.now() - ts.getTime() > ttlMs) : true
    return { data: expired ? null : data, rawData: data }
  } catch (e) {
    return { data: null, rawData: null }
  }
}

/**
 * 加载结构骨架：
 *   - 缓存有效 → 立即渲染（秒开），并后台静默重拉一次（兑现「重新进入即更新」，OQ-02/OQ-03）。
 *   - 缓存过期但有旧数据 → 先用旧数据渲染，再 await 网络。
 *   - 无任何缓存 → 显示加载态，await 网络（首次进入预取，OQ-02）。
 */
async function loadStructure(sp, forceRefresh = false) {
  const ps = partState[sp]
  if (!ps) return
  const { data: cached, rawData } = readStructureCache(sp)

  if (!forceRefresh && cached) {
    ps.structure = cached
    ps.structureLoading = false
    ps.errorMsg = null
    _refreshStructureNetwork(sp)   // 后台静默刷新，不阻塞渲染
    return
  }
  if (rawData) {
    ps.structure = rawData          // 过期旧数据先撑住骨架
    ps.structureLoading = false
  } else {
    ps.structure = null
    ps.structureLoading = true
  }
  await _refreshStructureNetwork(sp)
}

/** 网络重拉结构（指数退避重试 3 次）；成功后更新缓存，并补拉新发现设备的 MQTT 值。 */
async function _refreshStructureNetwork(sp) {
  const ps = partState[sp]
  if (!ps) return
  const BACKOFF_MS = [0, 500, 1500]
  for (let attempt = 0; attempt < BACKOFF_MS.length; attempt++) {
    if (BACKOFF_MS[attempt] > 0) await new Promise((r) => setTimeout(r, BACKOFF_MS[attempt]))
    try {
      const res = await api.getOwnerStructure(sp)
      if (res && res.success !== false) {
        ps.structure = res
        ps.errorMsg = null
        writeStructureCache(sp, res)
        _readNewlyDiscovered(sp, res)
      } else {
        ps.errorMsg = (res && res.error) || '获取设备结构失败，请点击重试'
        // 保留已有 structure（若有），不清空
      }
      ps.structureLoading = false
      return
    } catch (e) {
      if (attempt < BACKOFF_MS.length - 1) continue
      // 重试耗尽：降级用过期缓存
      const { rawData } = readStructureCache(sp)
      if (rawData && !ps.structure) ps.structure = rawData
      if (!ps.structure) ps.errorMsg = '获取设备结构失败，请点击重试'
      ps.structureLoading = false
    }
  }
}

/** 后台刷新发现新 device_sn 且 MQTT 已连接当前套户时，补发 DeviceStatusRead。 */
function _readNewlyDiscovered(sp, structure) {
  const room = currentRoom.value
  if (!room || room.specific_part !== sp) return
  if (!mqttClient.connected.value || !Array.isArray(structure.device_sns)) return
  const fresh = structure.device_sns.map(String).filter((s) => !knownSns.has(s))
  if (fresh.length > 0) {
    fresh.forEach((s) => knownSns.add(s))
    mqttClient.publishRead(room.screen_mac, fresh)
  }
}

/** 错误/pending 态的重试入口（强制网络重拉，非「手动刷新有效数据」入口）。 */
function reloadStructure() {
  const sp = currentRoom.value?.specific_part
  if (sp) loadStructure(sp, true)
}

// ── 通用 ─────────────────────────────────────────────────────────────────────
function goBind() {
  uni.navigateTo({ url: '/pages/bind/index' })
}

// ── 生命周期 ─────────────────────────────────────────────────────────────────
onLoad(() => {
  // custom 导航：标题自绘在页面内（.ps-header），无系统返回箭头，由底栏 ArkTabBar 切换。
  //   仍设置胶囊按钮 frontColor=白（微信右上「⋯/○」两颗胶囊图标色），底色由 backgroundColor 透出的
  //   页面 bg-base 渐变承接（与 profile/chat 一致的赛博朋克 HUD 观感）。
  try { uni.setNavigationBarColor({ frontColor: '#ffffff', backgroundColor: '#05070f' }) } catch (e) { /* ignore */ }
  // 注：HOLO-HUD 数字/铭牌字体直接走 CSS 字体栈里的系统等宽（Menlo/Monaco/monospace）。
  //   原 uni.loadFontFace 远程拉 jsdelivr Orbitron 不稳（CDN 返回非法 TTF → OTS 解析报错），
  //   已移除；真机若要 Orbitron，改为打包本地 .ttf（static/）并在后台配 downloadFile 合法域名。
})

onShow(() => {
  if (!authStore.isLoggedIn) { uni.reLaunch({ url: '/pages/login/index' }); return }
  if (rooms.value.length === 0 && loading.value) loadConfig()
})

onUnload(() => {
  Object.values(_flushTimers).forEach((t) => clearTimeout(t))
  if (_offDeviceUpdate) { _offDeviceUpdate(); _offDeviceUpdate = null }
  mqttClient.release()
})
</script>

<style scoped>
/* ── 页面骨架：与 profile/chat 一致的 flex 列 + 赛博朋克底 ────────────────── */
.ps-page {
  position: relative;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #05070f;
  overflow: hidden;
}

/* 赛博朋克背景（与 profile/chat 一致：紫/青径向渐变 + 深空底）*/
.bg-base, .bg-grid { position: absolute; pointer-events: none; }
.bg-base {
  inset: 0;
  background:
    radial-gradient(90% 45% at 18% 0%, rgba(101,55,180,0.32), transparent 55%),
    radial-gradient(80% 40% at 100% 4%, rgba(20,180,170,0.22), transparent 55%),
    linear-gradient(180deg, #0b0a1a, #07101c 60%, #050811);
}
.bg-grid {
  inset: 0;
  background-image:
    linear-gradient(rgba(56,230,224,0.06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(56,230,224,0.06) 1px, transparent 1px);
  background-size: 80rpx 80rpx;
  -webkit-mask-image: linear-gradient(180deg, #000, transparent 55%);
  mask-image: linear-gradient(180deg, #000, transparent 55%);
}

/* HUD 扫描线（参数页特色装饰，其它页无）*/
.hud-scan {
  position: absolute; left: 0; right: 0; top: 0; height: 300rpx; z-index: 1; pointer-events: none;
  background: linear-gradient(180deg, transparent, rgba(0, 229, 255, 0.10), transparent);
  animation: hudScan 5.5s linear infinite;
}
@keyframes hudScan { 0% { transform: translateY(-300rpx); } 100% { transform: translateY(1900rpx); } }
@keyframes pulseDot { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }
@keyframes hueFloat {
  0%, 100% { box-shadow: 0 0 28rpx rgba(0, 160, 255, 0.14), inset 0 1rpx 0 rgba(255, 255, 255, 0.05); }
  50% { box-shadow: 0 0 36rpx rgba(124, 58, 237, 0.22), inset 0 1rpx 0 rgba(255, 255, 255, 0.05); }
}
@keyframes eqBar { 0%, 100% { transform: scaleY(0.28); } 50% { transform: scaleY(1); } }

/* 状态栏占位 + 头 */
.status-spacer { position: relative; z-index: 5; flex: 0 0 auto; }
.ps-header {
  position: relative; z-index: 5; flex: 0 0 auto;
  height: 92rpx; display: flex; align-items: center; justify-content: center;
}
.ps-header-title {
  font-size: 34rpx; font-weight: 700; letter-spacing: 8rpx; color: #f4fbff;
  text-shadow: 0 0 12px rgba(56,230,224,0.5);
}

/* 内容滚动区（flex 列内滚动，让 ArkTabBar 固定底部）*/
.ps-content { position: relative; z-index: 4; flex: 1 1 0; min-height: 0; padding-bottom: 24rpx; }

/* 套户选择条 */
.unit-bar { display: flex; align-items: center; justify-content: space-between; padding: 28rpx 32rpx 14rpx; }
.unit-main { display: flex; flex-direction: column; flex: 1; min-width: 0; }
.unit-label { font-family: 'Orbitron', 'Menlo', 'Monaco', monospace; font-size: 20rpx; color: #5f7da6; letter-spacing: 4rpx; }
.unit-pick, .unit-single { font-size: 34rpx; color: #eaf6ff; font-weight: 700; letter-spacing: 1rpx; margin-top: 4rpx; text-shadow: 0 0 12rpx rgba(0, 229, 255, 0.45); }

.conn-side { display: flex; align-items: center; flex: none; }
/* 均衡器动效（连接时跳动，断开时静止矮态）*/
.eq { display: flex; align-items: flex-end; height: 32rpx; }
.eq-bar {
  width: 5rpx; height: 32rpx; margin-right: 4rpx; border-radius: 3rpx; transform: scaleY(0.28); transform-origin: bottom;
  background: linear-gradient(180deg, #00e5ff, #7c3aed);
}
.eq.live .eq-bar { animation: eqBar 1.1s ease-in-out infinite; }

.conn-pill { display: flex; align-items: center; margin-left: 14rpx; padding: 8rpx 16rpx; border-radius: 999rpx; border: 1rpx solid rgba(245, 158, 11, 0.4); background: rgba(245, 158, 11, 0.08); }
.conn-pill.on { border-color: rgba(39, 245, 181, 0.45); background: rgba(39, 245, 181, 0.08); }
.conn-led { width: 12rpx; height: 12rpx; margin-right: 8rpx; border-radius: 50%; background: #f59e0b; }
.conn-pill.on .conn-led { background: #27f5b5; box-shadow: 0 0 12rpx #27f5b5; animation: pulseDot 1.8s ease-in-out infinite; }
.conn-txt { font-family: 'Orbitron', 'Menlo', 'Monaco', monospace; font-size: 20rpx; letter-spacing: 1rpx; color: #f59e0b; }
.conn-pill.on .conn-txt { color: #27f5b5; }

/* 提示 / 空态 */
.tip { text-align: center; padding: 90rpx 24rpx; color: #6b7796; font-size: 28rpx; }
.link-btn {
  margin-top: 24rpx; display: inline-block; padding: 16rpx 42rpx; border-radius: 999rpx;
  background: linear-gradient(90deg, #00e5ff, #7c3aed); box-shadow: 0 0 24rpx rgba(0, 229, 255, 0.5);
}
.link-btn text { color: #04121f; font-size: 26rpx; font-weight: 700; }

/* 设备卡：暗玻璃 + 霓虹描边 + 呼吸辉光（青）*/
.dev-card {
  position: relative; margin: 16rpx 24rpx; border-radius: 24rpx; padding: 30rpx 30rpx 16rpx;
  background: linear-gradient(160deg, rgba(20, 30, 56, 0.74), rgba(10, 16, 33, 0.84));
  border: 1rpx solid rgba(0, 229, 255, 0.22);
  animation: hueFloat 7s ease-in-out infinite;
  overflow: hidden;
}
/* 交替紫色卡（节奏感）*/
.dev-card.alt {
  background: linear-gradient(160deg, rgba(28, 20, 52, 0.74), rgba(14, 9, 30, 0.84));
  border-color: rgba(124, 58, 237, 0.30);
}

/* 四角 HUD 括号 */
.bk { position: absolute; width: 22rpx; height: 22rpx; z-index: 1; }
.bk-tl { top: 12rpx; left: 12rpx; border-top: 3rpx solid rgba(0, 229, 255, 0.7); border-left: 3rpx solid rgba(0, 229, 255, 0.7); }
.bk-tr { top: 12rpx; right: 12rpx; border-top: 3rpx solid rgba(0, 229, 255, 0.7); border-right: 3rpx solid rgba(0, 229, 255, 0.7); }
.bk-bl { bottom: 12rpx; left: 12rpx; border-bottom: 3rpx solid rgba(0, 229, 255, 0.4); border-left: 3rpx solid rgba(0, 229, 255, 0.4); }
.bk-br { bottom: 12rpx; right: 12rpx; border-bottom: 3rpx solid rgba(0, 229, 255, 0.4); border-right: 3rpx solid rgba(0, 229, 255, 0.4); }
.dev-card.alt .bk-tl, .dev-card.alt .bk-tr { border-color: rgba(124, 58, 237, 0.75); }
.dev-card.alt .bk-bl, .dev-card.alt .bk-br { border-color: rgba(124, 58, 237, 0.45); }

/* 头部 */
.card-head { display: flex; align-items: center; position: relative; z-index: 2; }
.card-icon {
  width: 72rpx; height: 72rpx; display: flex; align-items: center; justify-content: center;
  font-family: 'Orbitron', 'Menlo', 'Monaco', monospace; font-size: 28rpx; font-weight: 800; letter-spacing: 1rpx; color: #7df9ff;
  border-radius: 18rpx; margin-right: 18rpx;
  background: rgba(0, 229, 255, 0.10); border: 1rpx solid rgba(0, 229, 255, 0.32);
  box-shadow: 0 0 16rpx rgba(0, 229, 255, 0.25);
}
.dev-card.alt .card-icon { background: rgba(124, 58, 237, 0.14); border-color: rgba(124, 58, 237, 0.4); box-shadow: 0 0 16rpx rgba(124, 58, 237, 0.3); color: #c4a6ff; }
.card-id { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.card-title { font-size: 34rpx; font-weight: 700; color: #eaf6ff; letter-spacing: 1rpx; line-height: 1.1; }
.card-code { font-family: 'Orbitron', 'Menlo', 'Monaco', monospace; font-size: 20rpx; letter-spacing: 3rpx; color: #5f7da6; margin-top: 6rpx; }
.dev-card.alt .card-code { color: #7a6aa6; }
.card-switch { transform: scale(0.92); }

/* ── HUD 指标分栏（ring + big + bar 混排）─────────────────────────────────── */
.metric-hud { display: flex; align-items: stretch; margin: 20rpx 0 8rpx; position: relative; z-index: 2; gap: 16rpx; }

/* 左列：主视觉（ring gauge / big text）；固定宽，居中 */
.mhud-left { display: flex; flex-direction: column; align-items: center; justify-content: center; flex: 0 0 200rpx; }

/* 右列：其余指标（bars / ring / chips）；自动撑满 */
.mhud-right { flex: 1; display: flex; flex-direction: column; justify-content: center; min-width: 0; gap: 12rpx; }

/* 单元格包裹（左右列共用，按 displayType 自描述渲染）*/
.mcell { width: 100%; display: flex; flex-direction: column; }
.mhud-left .mcell { align-items: center; }
.mhud-left .mcell + .mcell { margin-top: 18rpx; }
.mhud-right .mcell { align-items: stretch; }

/* 环形 gauge 已迁移到 <RingGauge>（ucharts arcbar，组件内 scoped 样式）*/

/* 大字展示（新风送风温度等）*/
.big-metric { display: flex; flex-direction: column; align-items: center; padding: 8rpx 0; }
.big-lbl { font-size: 20rpx; color: #5f7da6; letter-spacing: 1rpx; margin-bottom: 6rpx; }
.big-val-row { display: flex; align-items: flex-end; gap: 2rpx; }
.big-num {
  font-family: 'Orbitron', 'Menlo', monospace; font-size: 80rpx; font-weight: 800;
  color: #7df9ff; line-height: 1; text-shadow: 0 0 18rpx rgba(0, 229, 255, 0.45);
}
.dev-card.alt .big-num { color: #c4a6ff; text-shadow: 0 0 18rpx rgba(124, 58, 237, 0.45); }
.big-unt { font-size: 28rpx; color: #7df9ff; margin-bottom: 8rpx; }
.dev-card.alt .big-unt { color: #c4a6ff; }

/* 进度条（湿度 / 露点）*/
.bar-metric { display: flex; flex-direction: column; }
.bar-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8rpx; }
.bar-lbl { font-size: 22rpx; color: #7f8db0; }
.bar-val { font-size: 26rpx; font-weight: 700; color: #7df9ff; }
.bar-val.pink { color: #ff79c6; }
.bar-track { height: 8rpx; border-radius: 999rpx; background: rgba(0, 229, 255, 0.12); overflow: hidden; }
.bar-fill { height: 100%; border-radius: 999rpx; background: linear-gradient(90deg, #00e5ff, #3b82f6); }
.bar-fill.pink { background: linear-gradient(90deg, #ff79c6, #bd93f9); }

/* 指标：双列大字霓虹读数（纯文字 chip 回退）*/
.metric-row { display: flex; flex-wrap: wrap; margin: 24rpx -7rpx 6rpx; position: relative; z-index: 2; }
.metric-chip {
  box-sizing: border-box; width: calc(50% - 14rpx); margin: 7rpx; display: flex; flex-direction: column;
  padding: 16rpx 20rpx; border-radius: 16rpx;
  background: rgba(0, 229, 255, 0.05); border: 1rpx solid rgba(0, 229, 255, 0.14);
}
.dev-card.alt .metric-chip { background: rgba(124, 58, 237, 0.06); border-color: rgba(124, 58, 237, 0.16); }
.metric-lbl { font-size: 22rpx; color: #7f8db0; letter-spacing: 1rpx; margin-bottom: 6rpx; }
.metric-val { font-family: 'Orbitron', -apple-system, sans-serif; font-size: 40rpx; font-weight: 700; color: #7df9ff; line-height: 1.05; text-shadow: 0 0 14rpx rgba(0, 229, 255, 0.45); }
.dev-card.alt .metric-val { color: #c4a6ff; text-shadow: 0 0 14rpx rgba(124, 58, 237, 0.5); }
/* mhud-right 内的 metric-chip 不设宽（flex 列内自然撑满）*/
.mhud-right .metric-chip { width: auto; margin: 0; }

/* 控件区 */
.ctl-area { margin-top: 12rpx; position: relative; z-index: 2; }
.ctl-row { display: flex; align-items: center; justify-content: space-between; padding: 22rpx 0; border-top: 1rpx solid rgba(120, 160, 255, 0.10); }
.ctl-block { padding: 22rpx 0 6rpx; border-top: 1rpx solid rgba(120, 160, 255, 0.10); }
.ctl-label { font-size: 26rpx; color: #aab6d6; letter-spacing: 1rpx; }

/* 分段控件（风速等少选项 select）：标签在上 + 全宽矩形分段（对齐设计稿，非胶囊）*/
.seg-block { padding: 22rpx 0 6rpx; border-top: 1rpx solid rgba(120, 160, 255, 0.10); }
.seg { display: flex; gap: 16rpx; margin-top: 16rpx; }
.seg-item {
  flex: 1; text-align: center; padding: 22rpx 0; border-radius: 22rpx;
  background: rgba(10, 18, 38, 0.7); border: 1rpx solid rgba(120, 160, 255, 0.16);
}
.seg-item text { font-size: 26rpx; color: #9fb0d6; font-weight: 600; }
.seg-item.on {
  background: linear-gradient(135deg, rgba(0, 229, 255, 0.22), rgba(124, 58, 237, 0.30));
  border-color: rgba(0, 229, 255, 0.7); box-shadow: 0 0 18rpx rgba(0, 229, 255, 0.4);
}
.seg-item.on text { color: #eaf6ff; font-weight: 700; }
.dev-card.alt .seg-item.on {
  background: linear-gradient(135deg, rgba(124, 58, 237, 0.30), rgba(192, 38, 211, 0.28));
  border-color: rgba(192, 38, 211, 0.7); box-shadow: 0 0 16rpx rgba(124, 58, 237, 0.4);
}
.dev-card.alt .seg-item.on text { color: #f3eaff; }

/* 数值步进：大字霓虹中央值 */
.num-ctl { display: flex; align-items: center; margin-top: 16rpx; }
.num-btn {
  width: 100rpx; height: 92rpx; display: flex; align-items: center; justify-content: center; border-radius: 24rpx;
  border: 1rpx solid rgba(0, 229, 255, 0.32); color: #7df9ff;
  font-family: 'Orbitron', 'Menlo', monospace; font-size: 48rpx; font-weight: 700; background: rgba(10, 18, 38, 0.8);
}
.num-val {
  flex: 1; height: 92rpx; margin: 0 16rpx; display: flex; align-items: flex-end; justify-content: center; border-radius: 24rpx;
  background: linear-gradient(135deg, rgba(0, 229, 255, 0.16), rgba(124, 58, 237, 0.2));
  border: 1rpx solid rgba(0, 229, 255, 0.4); box-shadow: inset 0 0 24rpx rgba(0, 229, 255, 0.18);
}
.num-num { font-family: 'Orbitron', -apple-system, sans-serif; font-size: 56rpx; line-height: 1; color: #eaf6ff; font-weight: 800; text-shadow: 0 0 16rpx rgba(0, 229, 255, 0.5); padding-bottom: 14rpx; }
.num-unit { font-size: 28rpx; color: #9fb0d6; margin-left: 4rpx; padding-bottom: 18rpx; }
.dev-card.alt .num-btn { border-color: rgba(124, 58, 237, 0.4); color: #c4a6ff; }
.dev-card.alt .num-val { border-color: rgba(124, 58, 237, 0.45); box-shadow: inset 0 0 24rpx rgba(124, 58, 237, 0.18); }
.dev-card.alt .num-unit { color: #bcaee0; }

/* 运行模式：图标药丸 */
.mode-block { padding: 22rpx 0 6rpx; border-top: 1rpx solid rgba(120, 160, 255, 0.10); }
.mode-pills { display: flex; flex-wrap: wrap; margin: 18rpx -7rpx 0; }
.mode-pill {
  flex: 1; min-width: 150rpx; box-sizing: border-box; margin: 7rpx; display: flex; align-items: center; justify-content: center;
  padding: 18rpx 10rpx; border-radius: 16rpx;
  background: rgba(10, 18, 38, 0.75); border: 1rpx solid rgba(120, 160, 255, 0.16);
}
.mode-pill.on {
  background: linear-gradient(135deg, rgba(0, 229, 255, 0.22), rgba(124, 58, 237, 0.32));
  border-color: rgba(0, 229, 255, 0.7); box-shadow: 0 0 22rpx rgba(0, 229, 255, 0.45);
}
/* 模式标记：菱形小方块（选中态青色发光，未选中灰色），取代 emoji */
.mode-dot { width: 12rpx; height: 12rpx; margin-right: 12rpx; background: #5f7da6; transform: rotate(45deg); }
.mode-pill.on .mode-dot { background: #7df9ff; box-shadow: 0 0 12rpx #7df9ff; }
.dev-card.alt .mode-pill.on .mode-dot { background: #c4a6ff; box-shadow: 0 0 12rpx #c4a6ff; }
.mode-txt { font-size: 26rpx; color: #9fb0d6; }
.mode-pill.on .mode-txt { color: #eaf6ff; font-weight: 700; }

/* 查看全部 + 展开列表 */
.more-row { display: flex; align-items: center; justify-content: center; padding: 22rpx 0 12rpx; margin-top: 8rpx; border-top: 1rpx solid rgba(120, 160, 255, 0.08); position: relative; z-index: 2; }
.more-txt, .more-arrow { font-family: 'Orbitron', 'Menlo', 'Monaco', monospace; font-size: 22rpx; color: #5f6b86; letter-spacing: 1rpx; }
.more-arrow { margin-left: 8rpx; }
.rest-list { padding: 2rpx 0 10rpx; position: relative; z-index: 2; }
.rest-row { display: flex; align-items: center; justify-content: space-between; padding: 16rpx 0; border-top: 1rpx solid rgba(120, 160, 255, 0.08); }
.rest-name { font-size: 24rpx; color: #7f8db0; }
.rest-val { font-size: 24rpx; color: #bcd3e8; }

/* 空卡占位 */
.empty-tip { text-align: center; padding: 30rpx 0; position: relative; z-index: 2; }
.empty-tip text { font-size: 24rpx; color: #4d5878; }
</style>
