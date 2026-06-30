/**
 * @module MOD-GAME-ARKROBOT
 * @description 方舟智能体·机器人角色渲染器（Canvas 2D，无 Pixi/Spine 依赖）。
 *   程序化绘制一只悬浮机器人，含 5 个状态动画，由聊天 WS 生命周期驱动：
 *     booting   连接中（弱光闪烁启动）
 *     idle      空闲（轻微浮动 + 眨眼 + 反应堆呼吸）
 *     listening 聆听（录音中：天线亮 + 头部声波环 + 绿光）
 *     thinking  思考（状态/推理中：头顶三点环绕 + 眼睛上移 + 琥珀光）
 *     speaking  说话（流式输出：面罩声波条随 token 跳动 + 青亮光）
 *
 *   用法：
 *     const r = new ArkRobotRenderer(canvasNode, ctx, cssW, cssH)
 *     r.setState('idle'); loop: r.render(Date.now())
 *     收到一个 stream_token 时 r.pulseSpeak() 让嘴部跳一下。
 *
 *   纯 Canvas 2D API 子集，mp-weixin / 真机可直接运行。
 */

const STATE_COLOR = {
  booting: [80, 130, 170],
  idle: [0, 210, 255],
  listening: [0, 255, 163],
  thinking: [255, 200, 60],
  speaking: [90, 230, 255],
}

function rgba(c, a) {
  return `rgba(${c[0]}, ${c[1]}, ${c[2]}, ${a})`
}

export class ArkRobotRenderer {
  constructor(canvas, ctx, cssW, cssH) {
    this.canvas = canvas
    this.ctx = ctx
    this.w = cssW
    this.h = cssH
    this.state = 'booting'
    this.speakEnergy = 0
    this._lastT = 0
    this.stars = this._genStars(40)
  }

  resize(cssW, cssH) {
    this.w = cssW
    this.h = cssH
    this.stars = this._genStars(40)
  }

  setState(s) {
    if (STATE_COLOR[s]) this.state = s
  }

  /** 每收到一个流式 token 调一次，驱动嘴部声波跳动。 */
  pulseSpeak() {
    this.speakEnergy = Math.min(1, this.speakEnergy + 0.5)
  }

  _genStars(n) {
    const arr = []
    for (let i = 0; i < n; i++) {
      arr.push({
        x: Math.random(), y: Math.random(),
        r: Math.random() * 1.1 + 0.3, a: Math.random() * 0.5 + 0.2,
        ph: Math.random() * Math.PI * 2, sp: Math.random() * 0.002 + 0.0008,
      })
    }
    return arr
  }

  render(t) {
    const dt = this._lastT ? Math.min(64, t - this._lastT) : 16
    this._lastT = t
    this.speakEnergy = Math.max(0, this.speakEnergy - dt / 600)

    const ctx = this.ctx
    ctx.clearRect(0, 0, this.w, this.h)
    this._drawBackground(t)

    const color = STATE_COLOR[this.state] || STATE_COLOR.idle
    const s = Math.min(this.w, this.h) * 0.26
    const bobAmp = this.state === 'speaking' ? 6 : this.state === 'listening' ? 5 : 4
    const bob = Math.sin(t / 620) * bobAmp
    const cx = this.w / 2
    const cy = this.h * 0.54 + bob

    this._drawHover(cx, cy + s * 1.15, s, color, t)
    // 状态环绕特效（在机器人后层）
    if (this.state === 'listening') this._drawSoundRings(cx, cy - s * 0.55, s, color, t)
    this._drawBody(cx, cy, s, color, t)
    this._drawHead(cx, cy - s * 0.78, s, color, t)
    if (this.state === 'thinking') this._drawThinkingDots(cx, cy - s * 1.7, s, color, t)
  }

  // ── 背景 ───────────────────────────────────────────────────────────────────
  _drawBackground(t) {
    const ctx = this.ctx
    const g = ctx.createLinearGradient(0, 0, 0, this.h)
    g.addColorStop(0, '#05080f')
    g.addColorStop(1, '#0a1426')
    ctx.fillStyle = g
    ctx.fillRect(0, 0, this.w, this.h)

    this._softBlob(this.w * 0.3, this.h * 0.35, this.w * 0.5, [40, 90, 160], 0.10)
    this._softBlob(this.w * 0.78, this.h * 0.7, this.w * 0.5, [110, 40, 130], 0.07)

    ctx.save()
    this.stars.forEach((st) => {
      ctx.globalAlpha = st.a * (0.6 + 0.4 * Math.sin(t * st.sp + st.ph))
      ctx.fillStyle = '#cfeaff'
      ctx.beginPath()
      ctx.arc(st.x * this.w, st.y * this.h, st.r, 0, Math.PI * 2)
      ctx.fill()
    })
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

  // ── 悬浮光垫 ───────────────────────────────────────────────────────────────
  _drawHover(cx, cy, s, color, t) {
    const ctx = this.ctx
    const pulse = 0.6 + 0.4 * Math.sin(t / 500)
    ctx.save()
    ctx.globalCompositeOperation = 'lighter'
    const r = s * 1.1
    const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, r)
    g.addColorStop(0, rgba(color, 0.35 * pulse))
    g.addColorStop(1, rgba(color, 0))
    ctx.fillStyle = g
    ctx.beginPath()
    ctx.ellipse ? ctx.ellipse(cx, cy, r, r * 0.32, 0, 0, Math.PI * 2)
      : ctx.arc(cx, cy, r * 0.5, 0, Math.PI * 2)
    ctx.fill()
    ctx.restore()
  }

  // ── 身体（反应堆核心呼吸）──────────────────────────────────────────────────
  _drawBody(cx, cy, s, color, t) {
    const ctx = this.ctx
    const bw = s * 1.5
    const bh = s * 1.25
    const x = cx - bw / 2
    const y = cy - bh * 0.18

    ctx.save()
    // 金属外壳
    roundRect(ctx, x, y, bw, bh, s * 0.28)
    const g = ctx.createLinearGradient(0, y, 0, y + bh)
    g.addColorStop(0, '#243a52')
    g.addColorStop(0.5, '#2f5572')
    g.addColorStop(1, '#13202f')
    ctx.fillStyle = g
    ctx.fill()
    ctx.lineWidth = 1.5
    ctx.strokeStyle = rgba(color, 0.5)
    ctx.stroke()
    ctx.restore()

    // 反应堆核心
    const corePulse = 0.55 + 0.45 * Math.abs(Math.sin(t / (this.state === 'thinking' ? 280 : 700)))
    const coreR = s * 0.3
    ctx.save()
    ctx.globalCompositeOperation = 'lighter'
    const cg = ctx.createRadialGradient(cx, cy + bh * 0.28, 0, cx, cy + bh * 0.28, coreR * 1.6)
    cg.addColorStop(0, rgba(color, 0.95 * corePulse))
    cg.addColorStop(0.5, rgba(color, 0.4 * corePulse))
    cg.addColorStop(1, rgba(color, 0))
    ctx.fillStyle = cg
    ctx.beginPath()
    ctx.arc(cx, cy + bh * 0.28, coreR * 1.6, 0, Math.PI * 2)
    ctx.fill()
    ctx.restore()

    ctx.save()
    ctx.fillStyle = '#eaffff'
    ctx.beginPath()
    ctx.arc(cx, cy + bh * 0.28, coreR * 0.32, 0, Math.PI * 2)
    ctx.fill()
    ctx.restore()
  }

  // ── 头部（面罩 + 眼睛 + 天线 + 嘴部）──────────────────────────────────────
  _drawHead(cx, cy, s, color, t) {
    const ctx = this.ctx
    const hw = s * 1.32
    const hh = s * 1.04
    const x = cx - hw / 2
    const y = cy - hh / 2

    // 天线
    const tipY = y - s * 0.42
    const tipPulse = this.state === 'listening' ? 0.5 + 0.5 * Math.abs(Math.sin(t / 160)) : 0.5 + 0.3 * Math.sin(t / 600)
    ctx.save()
    ctx.strokeStyle = rgba(color, 0.7)
    ctx.lineWidth = 2
    ctx.beginPath()
    ctx.moveTo(cx, y + s * 0.04)
    ctx.lineTo(cx, tipY)
    ctx.stroke()
    ctx.globalCompositeOperation = 'lighter'
    const tg = ctx.createRadialGradient(cx, tipY, 0, cx, tipY, s * 0.2)
    tg.addColorStop(0, rgba(color, tipPulse))
    tg.addColorStop(1, rgba(color, 0))
    ctx.fillStyle = tg
    ctx.beginPath()
    ctx.arc(cx, tipY, s * 0.2, 0, Math.PI * 2)
    ctx.fill()
    ctx.restore()

    // 头壳
    ctx.save()
    roundRect(ctx, x, y, hw, hh, s * 0.34)
    const g = ctx.createLinearGradient(0, y, 0, y + hh)
    g.addColorStop(0, '#2c4d6b')
    g.addColorStop(1, '#16273a')
    ctx.fillStyle = g
    ctx.fill()
    ctx.lineWidth = 1.5
    ctx.strokeStyle = rgba(color, 0.55)
    ctx.stroke()
    ctx.restore()

    // 面罩（深色屏）
    const vw = hw * 0.78
    const vh = hh * 0.6
    const vx = cx - vw / 2
    const vy = cy - vh * 0.55
    ctx.save()
    roundRect(ctx, vx, vy, vw, vh, s * 0.22)
    ctx.fillStyle = '#0a141f'
    ctx.fill()
    ctx.clip()

    // 眼睛
    const lookUp = this.state === 'thinking' ? -vh * 0.16 : 0
    const eyeY = cy - vh * 0.04 + lookUp
    const eyeDx = vw * 0.22
    const blink = this._blink(t)
    const eyeR = s * 0.16
    ;[-1, 1].forEach((sgn) => {
      const ex = cx + sgn * eyeDx
      ctx.save()
      ctx.globalCompositeOperation = 'lighter'
      const eg = ctx.createRadialGradient(ex, eyeY, 0, ex, eyeY, eyeR * 2)
      eg.addColorStop(0, rgba(color, 0.95))
      eg.addColorStop(1, rgba(color, 0))
      ctx.fillStyle = eg
      ctx.beginPath()
      ctx.ellipse ? ctx.ellipse(ex, eyeY, eyeR, eyeR * blink, 0, 0, Math.PI * 2)
        : ctx.arc(ex, eyeY, eyeR * blink, 0, Math.PI * 2)
      ctx.fill()
      ctx.restore()
      ctx.save()
      ctx.fillStyle = '#ffffff'
      ctx.beginPath()
      ctx.ellipse ? ctx.ellipse(ex, eyeY, eyeR * 0.4, eyeR * 0.4 * blink, 0, 0, Math.PI * 2)
        : ctx.arc(ex, eyeY, eyeR * 0.4 * blink, 0, Math.PI * 2)
      ctx.fill()
      ctx.restore()
    })

    // 嘴部声波（说话时）
    if (this.state === 'speaking') {
      const my = vy + vh * 0.78
      const bars = 7
      const span = vw * 0.6
      const x0 = cx - span / 2
      ctx.save()
      ctx.fillStyle = rgba(color, 0.9)
      for (let i = 0; i < bars; i++) {
        const bx = x0 + (span * i) / (bars - 1)
        const e = 0.4 + this.speakEnergy
        const bh2 = (vh * 0.10) + vh * 0.22 * e * Math.abs(Math.sin(t * 0.02 + i * 0.9))
        roundRect(ctx, bx - 2, my - bh2 / 2, 4, bh2, 2)
        ctx.fill()
      }
      ctx.restore()
    }
    ctx.restore()
  }

  _blink(t) {
    // 每 ~3.2s 眨一次，闭眼约 130ms
    const m = t % 3200
    if (m > 3070) return Math.max(0.08, 1 - (m - 3070) / 65)
    if (m > 3005 && m <= 3070) return Math.max(0.08, 1 - (3070 - m) / 65)
    return 1
  }

  // ── 思考三点 ───────────────────────────────────────────────────────────────
  _drawThinkingDots(cx, cy, s, color, t) {
    const ctx = this.ctx
    const r = s * 0.5
    ctx.save()
    ctx.globalCompositeOperation = 'lighter'
    for (let i = 0; i < 3; i++) {
      const ang = t / 320 + (i * Math.PI * 2) / 3
      const dx = cx + Math.cos(ang) * r
      const dy = cy + Math.sin(ang) * r * 0.5
      const a = 0.4 + 0.6 * (0.5 + 0.5 * Math.sin(t / 200 + i))
      ctx.fillStyle = rgba(color, a)
      ctx.beginPath()
      ctx.arc(dx, dy, s * 0.08, 0, Math.PI * 2)
      ctx.fill()
    }
    ctx.restore()
  }

  // ── 聆听声波环 ─────────────────────────────────────────────────────────────
  _drawSoundRings(cx, cy, s, color, t) {
    const ctx = this.ctx
    ctx.save()
    ctx.globalCompositeOperation = 'lighter'
    for (let k = 0; k < 3; k++) {
      const ph = ((t / 900) + k / 3) % 1
      const rr = s * (0.7 + ph * 1.4)
      ctx.globalAlpha = (1 - ph) * 0.4
      ctx.strokeStyle = rgba(color, 1)
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.arc(cx, cy, rr, 0, Math.PI * 2)
      ctx.stroke()
    }
    ctx.restore()
  }
}

function roundRect(ctx, x, y, w, h, r) {
  const rr = Math.min(r, w / 2, h / 2)
  ctx.beginPath()
  ctx.moveTo(x + rr, y)
  ctx.arcTo(x + w, y, x + w, y + h, rr)
  ctx.arcTo(x + w, y + h, x, y + h, rr)
  ctx.arcTo(x, y + h, x, y, rr)
  ctx.arcTo(x, y, x + w, y, rr)
  ctx.closePath()
}

export default ArkRobotRenderer
