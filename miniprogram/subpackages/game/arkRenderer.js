/**
 * @module MOD-GAME-ARKRENDER
 * @description 方舟座舱·Canvas 2D 渲染器（美术升级版，无 Pixi/Spine 依赖）。
 *   把扁平多边形升级为"准插画"飞船透视图：
 *     金属渐变船体 + 舱段面板线 + 驾驶舱辉光 + 双引擎尾焰 + 星空视差背景
 *     + 每区状态辉光/故障火花 + 子系统 HUD 节点 + 角标 + 扫描线。
 *
 *   设计要点：
 *   - 船体分段 = 三个子系统分区多边形（与命中/状态严格对齐，单一真源）。
 *   - 可选真插画：loadShipImage(src) 后改用 drawImage 作底图，
 *     多边形退化为"热区 + 状态辉光蒙版"（用真插画时只需把 poly 对齐插画的子系统区域）。
 *   - 状态辉光用 additive（globalCompositeOperation='lighter'）叠加，按状态脉冲。
 *   - 不用 ctx.filter（mp 不稳）；辉光靠 radialGradient + shadowBlur。
 *   - 纯 Canvas 2D API 子集，mp-weixin / 真机可直接运行。
 *
 *   用法（页面侧）：
 *     const r = new ArkRenderer(canvasNode, ctx, cssW, cssH, zones)
 *     r.setStatuses(reactiveZoneStatus)   // 传引用，render 时实时读取
 *     loop: r.render(Date.now())
 *     tap:  r.hitTest(x, y) -> zoneId | null
 */

// 状态视觉配置：rgb 数组（additive 辉光用）+ 文案
const STATUS_VIS = {
  normal: { rgb: [0, 255, 163], text: '正常' },
  warning: { rgb: [255, 212, 0], text: '警告' },
  fault: { rgb: [255, 46, 99], text: '故障' },
  idle: { rgb: [90, 120, 150], text: '无数据' },
}

function rgba(c, a) {
  return `rgba(${c[0]}, ${c[1]}, ${c[2]}, ${a})`
}

export class ArkRenderer {
  /**
   * @param {object} canvas  canvas node（含 createImage / requestAnimationFrame）
   * @param {CanvasRenderingContext2D} ctx  已 scale(dpr) 的 2d 上下文（绘制坐标=CSS px）
   * @param {number} cssW
   * @param {number} cssH
   * @param {Array<{id,name,poly:number[][]}>} zones  poly 为归一化 [0..1] 坐标
   */
  constructor(canvas, ctx, cssW, cssH, zones) {
    this.canvas = canvas
    this.ctx = ctx
    this.w = cssW
    this.h = cssH
    this.zones = zones
    this.statuses = {}            // zoneId -> 状态（外部传引用）
    this.shipImg = null           // 可选真插画
    this._lastT = 0
    this.particles = []           // 故障火花
    this._spawnAcc = {}           // zoneId -> 上次喷发时刻
    this._rebuild()
    this.stars = this._genStars(64)
  }

  // 归一化多边形 → 像素，并预算质心/包围盒
  _rebuild() {
    this.pxZones = this.zones.map((z) => {
      const pts = z.poly.map(([nx, ny]) => ({ x: nx * this.w, y: ny * this.h }))
      return { id: z.id, name: z.name, pts, ctr: centroid(pts), bbox: bbox(pts) }
    })
  }

  resize(cssW, cssH) {
    this.w = cssW
    this.h = cssH
    this._rebuild()
    this.stars = this._genStars(64)
  }

  setStatuses(statusRef) { this.statuses = statusRef }

  /** 可选：载入真飞船插画（网络 URL 或已打包的 /static 路径）。 */
  loadShipImage(src) {
    if (!this.canvas || !this.canvas.createImage) return
    const img = this.canvas.createImage()
    img.onload = () => { this.shipImg = img }
    img.onerror = () => { this.shipImg = null }
    img.src = src
  }

  _genStars(n) {
    const arr = []
    for (let i = 0; i < n; i++) {
      arr.push({
        x: Math.random(),
        y: Math.random(),
        r: Math.random() * 1.2 + 0.3,
        a: Math.random() * 0.5 + 0.2,
        ph: Math.random() * Math.PI * 2,
        sp: Math.random() * 0.002 + 0.0008,
      })
    }
    return arr
  }

  // ── 命中检测 ───────────────────────────────────────────────────────────────
  hitTest(x, y) {
    const hit = this.pxZones.find((pz) => pointInPoly(x, y, pz.pts))
    return hit ? hit.id : null
  }

  zoneName(id) {
    const z = this.zones.find((z) => z.id === id)
    return z ? z.name : id
  }

  statusText(id) {
    const s = this.statuses[id] || 'idle'
    return (STATUS_VIS[s] || STATUS_VIS.idle).text
  }

  // ── 主渲染 ─────────────────────────────────────────────────────────────────
  render(t) {
    const dt = this._lastT ? Math.min(64, t - this._lastT) : 16
    this._lastT = t
    const ctx = this.ctx
    ctx.clearRect(0, 0, this.w, this.h)

    this._drawBackground(t)
    this._drawHullShadow()

    if (this.shipImg) {
      this._drawShipImage()
    } else {
      this.pxZones.forEach((pz) => this._drawShipSegment(pz))
      this._drawCockpit(t)
      this._drawEngines(t)
    }

    // 状态辉光 + 边缘 + 节点
    this.pxZones.forEach((pz) => {
      const st = this.statuses[pz.id] || 'idle'
      this._drawZoneGlow(pz, st, t)
    })
    this.pxZones.forEach((pz) => {
      const st = this.statuses[pz.id] || 'idle'
      this._spawnFaultSparks(pz, st, t)
      this._drawNode(pz, st, t)
    })

    this._updateAndDrawParticles(dt)
    this._drawForeground(t)
  }

  // ── 背景：星空 + 星云 + 极淡网格 ──────────────────────────────────────────
  _drawBackground(t) {
    const ctx = this.ctx
    const g = ctx.createLinearGradient(0, 0, 0, this.h)
    g.addColorStop(0, '#05080f')
    g.addColorStop(0.6, '#080f1e')
    g.addColorStop(1, '#0a1426')
    ctx.fillStyle = g
    ctx.fillRect(0, 0, this.w, this.h)

    // 星云（两团大柔光）
    this._softBlob(this.w * 0.22, this.h * 0.28, this.w * 0.5, [40, 90, 160], 0.10)
    this._softBlob(this.w * 0.8, this.h * 0.72, this.w * 0.55, [120, 40, 120], 0.08)

    // 星点（轻微闪烁）
    ctx.save()
    this.stars.forEach((s) => {
      const a = s.a * (0.6 + 0.4 * Math.sin(t * s.sp + s.ph))
      ctx.globalAlpha = a
      ctx.fillStyle = '#cfeaff'
      ctx.beginPath()
      ctx.arc(s.x * this.w, s.y * this.h, s.r, 0, Math.PI * 2)
      ctx.fill()
    })
    ctx.restore()

    // 极淡网格
    ctx.save()
    ctx.strokeStyle = 'rgba(0, 229, 255, 0.05)'
    ctx.lineWidth = 1
    const step = Math.max(28, this.w / 12)
    ctx.beginPath()
    for (let x = 0; x <= this.w; x += step) { ctx.moveTo(x, 0); ctx.lineTo(x, this.h) }
    for (let y = 0; y <= this.h; y += step) { ctx.moveTo(0, y); ctx.lineTo(this.w, y) }
    ctx.stroke()
    ctx.restore()
  }

  _softBlob(cx, cy, r, c, a) {
    const ctx = this.ctx
    const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, r)
    g.addColorStop(0, rgba(c, a))
    g.addColorStop(1, rgba(c, 0))
    ctx.fillStyle = g
    ctx.fillRect(cx - r, cy - r, r * 2, r * 2)
  }

  // 船体下方一团冷光，托起整艘船
  _drawHullShadow() {
    const ctx = this.ctx
    ctx.save()
    ctx.globalCompositeOperation = 'lighter'
    this._softBlob(this.w * 0.5, this.h * 0.5, this.w * 0.42, [20, 120, 160], 0.10)
    ctx.restore()
  }

  // ── 程序化船体分段（金属渐变 + 面板线 + 冷边光）──────────────────────────
  _drawShipSegment(pz) {
    const ctx = this.ctx
    ctx.save()
    tracePath(ctx, pz.pts)
    // 金属竖向渐变
    const { y0, y1 } = pz.bbox
    const g = ctx.createLinearGradient(0, y0, 0, y1)
    g.addColorStop(0, '#16293c')
    g.addColorStop(0.45, '#274d6b')
    g.addColorStop(0.55, '#2d5878')
    g.addColorStop(1, '#0e1c2b')
    ctx.fillStyle = g
    ctx.fill()
    // 高光侧（左上）
    ctx.clip()
    const hl = ctx.createLinearGradient(pz.bbox.x0, 0, pz.bbox.x1, 0)
    hl.addColorStop(0, 'rgba(160, 220, 255, 0.10)')
    hl.addColorStop(0.4, 'rgba(160, 220, 255, 0)')
    ctx.fillStyle = hl
    ctx.fillRect(pz.bbox.x0, pz.bbox.y0, pz.bbox.w, pz.bbox.h)
    // 面板线
    ctx.strokeStyle = 'rgba(10, 20, 30, 0.55)'
    ctx.lineWidth = 1
    const rows = 3
    for (let i = 1; i <= rows; i++) {
      const yy = pz.bbox.y0 + (pz.bbox.h * i) / (rows + 1)
      ctx.beginPath()
      ctx.moveTo(pz.bbox.x0, yy)
      ctx.lineTo(pz.bbox.x1, yy)
      ctx.stroke()
    }
    ctx.restore()

    // 冷边光描边
    ctx.save()
    tracePath(ctx, pz.pts)
    ctx.lineWidth = 1.5
    ctx.strokeStyle = 'rgba(120, 200, 255, 0.35)'
    ctx.stroke()
    ctx.restore()
  }

  _drawCockpit(t) {
    // 驾驶舱：新风区上部一颗青色光学舱
    const fresh = this.pxZones.find((z) => z.id === 'fresh_air')
    if (!fresh) return
    const cx = fresh.ctr.x
    const cy = fresh.bbox.y0 + fresh.bbox.h * 0.42
    const r = Math.max(8, this.w * 0.035)
    const ctx = this.ctx
    ctx.save()
    ctx.globalCompositeOperation = 'lighter'
    const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, r * 1.8)
    const pulse = 0.7 + 0.3 * Math.sin(t / 700)
    g.addColorStop(0, rgba([120, 240, 255], 0.9 * pulse))
    g.addColorStop(0.5, rgba([60, 180, 255], 0.4 * pulse))
    g.addColorStop(1, rgba([60, 180, 255], 0))
    ctx.fillStyle = g
    ctx.beginPath()
    ctx.arc(cx, cy, r * 1.8, 0, Math.PI * 2)
    ctx.fill()
    ctx.restore()
  }

  _drawEngines(t) {
    // 双引擎尾焰：除湿·能源区底部两口喷管
    const tail = this.pxZones.find((z) => z.id === 'dehumid')
    if (!tail) return
    const ctx = this.ctx
    const baseY = tail.bbox.y1 - tail.bbox.h * 0.06
    const dx = tail.bbox.w * 0.16
    const cxs = [tail.ctr.x - dx, tail.ctr.x + dx]
    const flick = 0.75 + 0.25 * Math.sin(t / 90) + 0.1 * Math.sin(t / 37)
    const len = tail.bbox.h * 0.32 * flick
    const wid = Math.max(5, this.w * 0.022)
    ctx.save()
    ctx.globalCompositeOperation = 'lighter'
    cxs.forEach((cx) => {
      const g = ctx.createLinearGradient(0, baseY, 0, baseY + len)
      g.addColorStop(0, 'rgba(180, 240, 255, 0.95)')
      g.addColorStop(0.35, 'rgba(60, 170, 255, 0.6)')
      g.addColorStop(1, 'rgba(60, 170, 255, 0)')
      ctx.fillStyle = g
      ctx.beginPath()
      ctx.moveTo(cx - wid, baseY)
      ctx.lineTo(cx + wid, baseY)
      ctx.lineTo(cx, baseY + len)
      ctx.closePath()
      ctx.fill()
    })
    ctx.restore()
  }

  _drawShipImage() {
    // 真插画：等比缩放铺到画布中部（留边）。热区/状态仍由 poly 控制。
    const ctx = this.ctx
    const img = this.shipImg
    const iw = img.width || this.w
    const ih = img.height || this.h
    const scale = Math.min((this.w * 0.92) / iw, (this.h * 0.96) / ih)
    const dw = iw * scale
    const dh = ih * scale
    ctx.drawImage(img, (this.w - dw) / 2, (this.h - dh) / 2, dw, dh)
  }

  // ── 状态辉光（additive，按区域裁剪）──────────────────────────────────────
  _drawZoneGlow(pz, status, t) {
    const vis = STATUS_VIS[status] || STATUS_VIS.idle
    let pulse = 0.85
    if (status === 'fault') pulse = 0.5 + 0.5 * Math.abs(Math.sin(t / 260))
    else if (status === 'warning') pulse = 0.6 + 0.4 * Math.abs(Math.sin(t / 560))
    else if (status === 'idle') pulse = 0.32

    const ctx = this.ctx
    ctx.save()
    tracePath(ctx, pz.pts)
    ctx.clip()
    ctx.globalCompositeOperation = 'lighter'
    const r = Math.max(pz.bbox.w, pz.bbox.h) * 0.75
    const g = ctx.createRadialGradient(pz.ctr.x, pz.ctr.y, 0, pz.ctr.x, pz.ctr.y, r)
    g.addColorStop(0, rgba(vis.rgb, 0.42 * pulse))
    g.addColorStop(0.6, rgba(vis.rgb, 0.14 * pulse))
    g.addColorStop(1, rgba(vis.rgb, 0))
    ctx.fillStyle = g
    ctx.fillRect(pz.bbox.x0, pz.bbox.y0, pz.bbox.w, pz.bbox.h)
    ctx.restore()

    // 区域边缘点亮
    ctx.save()
    tracePath(ctx, pz.pts)
    ctx.lineWidth = 2
    ctx.strokeStyle = rgba(vis.rgb, Math.min(1, pulse))
    ctx.shadowColor = rgba(vis.rgb, 0.9)
    ctx.shadowBlur = (status === 'idle' ? 3 : 12) * pulse
    ctx.stroke()
    ctx.restore()
  }

  // ── 子系统 HUD 节点（光点 + 名称 + 状态）─────────────────────────────────
  _drawNode(pz, status, t) {
    const vis = STATUS_VIS[status] || STATUS_VIS.idle
    const ctx = this.ctx
    const x = pz.ctr.x
    const y = pz.ctr.y
    const pulse = 0.6 + 0.4 * Math.sin(t / 400)
    ctx.save()
    // 光点
    ctx.globalCompositeOperation = 'lighter'
    const g = ctx.createRadialGradient(x, y, 0, x, y, 10)
    g.addColorStop(0, rgba(vis.rgb, 0.95))
    g.addColorStop(1, rgba(vis.rgb, 0))
    ctx.fillStyle = g
    ctx.beginPath()
    ctx.arc(x, y, 10, 0, Math.PI * 2)
    ctx.fill()
    ctx.restore()

    ctx.save()
    ctx.fillStyle = '#ffffff'
    ctx.beginPath()
    ctx.arc(x, y, 2.2 + 0.6 * pulse, 0, Math.PI * 2)
    ctx.fill()
    ctx.restore()

    // 标签底衬 + 文字
    ctx.save()
    ctx.font = '12px sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    const tw = Math.max(ctx.measureText(pz.name).width, 48) + 18
    ctx.fillStyle = 'rgba(4, 10, 18, 0.55)'
    roundRect(ctx, x - tw / 2, y + 18, tw, 34, 6)
    ctx.fill()
    ctx.fillStyle = '#dff6ff'
    ctx.fillText(pz.name, x, y + 28)
    ctx.fillStyle = rgba(vis.rgb, 1)
    ctx.font = '10px sans-serif'
    ctx.fillText('● ' + vis.text, x, y + 44)
    ctx.restore()
  }

  // ── 故障火花粒子 ──────────────────────────────────────────────────────────
  _spawnFaultSparks(pz, status, t) {
    if (status !== 'fault') return
    const last = this._spawnAcc[pz.id] || 0
    if (t - last < 90) return
    this._spawnAcc[pz.id] = t
    if (this.particles.length > 60) return
    const n = 2
    for (let i = 0; i < n; i++) {
      this.particles.push({
        x: pz.ctr.x + (Math.random() - 0.5) * pz.bbox.w * 0.5,
        y: pz.ctr.y + (Math.random() - 0.5) * pz.bbox.h * 0.3,
        vx: (Math.random() - 0.5) * 0.04,
        vy: -0.05 - Math.random() * 0.05,
        life: 1,
        rgb: STATUS_VIS.fault.rgb,
      })
    }
  }

  _updateAndDrawParticles(dt) {
    const ctx = this.ctx
    ctx.save()
    ctx.globalCompositeOperation = 'lighter'
    for (let i = this.particles.length - 1; i >= 0; i--) {
      const p = this.particles[i]
      p.x += p.vx * dt
      p.y += p.vy * dt
      p.life -= dt / 700
      if (p.life <= 0) { this.particles.splice(i, 1); continue }
      ctx.globalAlpha = Math.max(0, p.life)
      ctx.fillStyle = rgba(p.rgb, 1)
      ctx.beginPath()
      ctx.arc(p.x, p.y, 1.6, 0, Math.PI * 2)
      ctx.fill()
    }
    ctx.restore()
  }

  // ── 前景 FX：扫描线 + 暗角 + 角标 ────────────────────────────────────────
  _drawForeground(t) {
    const ctx = this.ctx
    // 扫描线
    const y = (t / 16) % this.h
    ctx.save()
    const g = ctx.createLinearGradient(0, y - 30, 0, y + 30)
    g.addColorStop(0, 'rgba(0,229,255,0)')
    g.addColorStop(0.5, 'rgba(0,229,255,0.08)')
    g.addColorStop(1, 'rgba(0,229,255,0)')
    ctx.fillStyle = g
    ctx.fillRect(0, y - 30, this.w, 60)
    ctx.restore()

    // 暗角
    ctx.save()
    const vg = ctx.createRadialGradient(
      this.w / 2, this.h / 2, this.h * 0.3,
      this.w / 2, this.h / 2, this.h * 0.75,
    )
    vg.addColorStop(0, 'rgba(0,0,0,0)')
    vg.addColorStop(1, 'rgba(0,0,0,0.45)')
    ctx.fillStyle = vg
    ctx.fillRect(0, 0, this.w, this.h)
    ctx.restore()

    // 四角 HUD 角标
    ctx.save()
    ctx.strokeStyle = 'rgba(0, 229, 255, 0.5)'
    ctx.lineWidth = 2
    const m = 14
    const L = 20
    const corners = [
      [m, m, 1, 1], [this.w - m, m, -1, 1],
      [m, this.h - m, 1, -1], [this.w - m, this.h - m, -1, -1],
    ]
    corners.forEach(([cx, cy, sx, sy]) => {
      ctx.beginPath()
      ctx.moveTo(cx + L * sx, cy)
      ctx.lineTo(cx, cy)
      ctx.lineTo(cx, cy + L * sy)
      ctx.stroke()
    })
    ctx.restore()
  }
}

// ── 几何工具 ─────────────────────────────────────────────────────────────────
function tracePath(ctx, pts) {
  ctx.beginPath()
  ctx.moveTo(pts[0].x, pts[0].y)
  for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y)
  ctx.closePath()
}

function centroid(pts) {
  let x = 0
  let y = 0
  pts.forEach((p) => { x += p.x; y += p.y })
  return { x: x / pts.length, y: y / pts.length }
}

function bbox(pts) {
  let x0 = Infinity
  let y0 = Infinity
  let x1 = -Infinity
  let y1 = -Infinity
  pts.forEach((p) => {
    if (p.x < x0) x0 = p.x
    if (p.y < y0) y0 = p.y
    if (p.x > x1) x1 = p.x
    if (p.y > y1) y1 = p.y
  })
  return { x0, y0, x1, y1, w: x1 - x0, h: y1 - y0 }
}

function pointInPoly(px, py, pts) {
  let inside = false
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const xi = pts[i].x
    const yi = pts[i].y
    const xj = pts[j].x
    const yj = pts[j].y
    const intersect = yi > py !== yj > py && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi
    if (intersect) inside = !inside
  }
  return inside
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y, x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r)
  ctx.arcTo(x, y, x + w, y, r)
  ctx.closePath()
}

export default ArkRenderer
