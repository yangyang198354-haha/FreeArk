/**
 * @module MOD-1120-FE-01
 * @author Claude (v1.12.0 参数设置页重设计)
 * @description 参数设置页「按设备/房间分组面板」纯逻辑（与 Vue 运行时解耦，便于 vitest 单测）。
 *
 *   v1.12.0 重设计（docs/requirements/v1.12.0_miniprogram_param_settings_redesign）：
 *   - 取消「只读/可写分面板」与「我的房产 / 参数设置」两区域，改为按预设类型纵向面板：
 *       主机（集中供暖 270001）→ 新风（130004）→ 主温控（260001）→ 各房间（120003）→ 其余系统设备
 *   - 每个面板两个 tab：tab1「设置」（OQ-01 精选可写属性）/ tab2「详细」（全部属性含只读）
 *   - 骨架来自 owner/structure（device_sn / product_code / sub_type / params 定义）
 *   - 值来自 MQTT DeviceStatusUpdate，按 device_sn + param_name(=attrTag) 对齐（不再用 sub_type 叠加）
 *
 *   写链路（DeviceWrite/写确认/审计）保持 v1.10.0 语义零变更，不在本模块内。
 */

// OQ-01（用户确认）：各面板 tab1「设置」展示的可写属性白名单（按 product_code）。
// system_switch 只在主机（270001）出现；主温控（260001/客厅）不重复展示 system_switch。
// 主机不显示 energy_supply_mode（能源供应）——写 mode 时由 buildWriteItems 按 MODE_ENERGY_LINK
//   自动联动下发 energy_supply_mode（制冷/制热→同；通风→无；除湿→制冷），无需用户单独设置。
export const TAB1_FIELDS = {
  '270001': ['system_switch', 'mode', 'energy_saving_sign'],  // 主机·集中供暖（能源供应随运行模式自动联动）
  '260001': ['switch', 'temp_set'],                           // 主温控（显示为「客厅」）
  '130004': [],                                               // 新风传感器（130004）本身不开放设置（#2：去掉出风温度设定）
  '10016':  ['wind_speed', 'humidification_enable'],          // 新风·风速/加湿在「面板控制器」10016 上（#2 抓包确认）
  '120003': ['switch', 'temp_set'],                           // 各房间·末端温控
}

// 预设系统面板顺序（主机 → 新风 → 客厅）。每个面板可匹配多个 product_code。
// 无论设备落在 system_devices 还是某房间，均按 product_code 抽出为独立面板
//（OQ-06：主温控独立面板，对 structure 归属鲁棒）。
//   新风面板合并 130004（新风传感器，详细读数）+ 10016（面板控制器，承载风速/加湿设置，#2）。
//   260001 为全屋主温控器，业务上展示为「客厅」（用户 2026-06-29 指定）。
const SYS_PANEL_ORDER = [
  { codes: ['270001'], title: '主机' },
  { codes: ['130004', '10016'], title: '新风' },
  { codes: ['260001'], title: '客厅' },
]

// 其余系统级设备（非预设）兜底标题，避免丢失既有可见信息（能量计 / 空气质量等）。
const EXTRA_SYS_TITLE = { '250001': '能量计', '100007': '空气质量' }

/**
 * 房间名 fallback 链：room_name → ori_room_name → '未知房间'（继承 v1.11.1 语义）。
 */
export function resolveRoomName(room) {
  return (room && (room.room_name || room.ori_room_name)) || '未知房间'
}

/**
 * 构建某设备 tab1「设置」的可写控件定义列表。
 * @param device {device_sn, product_code, params:[{param_name,display_name}]}
 * @param writableAttrs 后端 config.writable_attrs（attrTag → {control,label,options,unit,step,min,max}）
 * @returns Array<{tag,label,control,unit,step,min,max,options,optionLabels}>
 */
export function buildControls(device, writableAttrs) {
  const wa = writableAttrs || {}
  const code = String((device && device.product_code) || '')
  const allow = TAB1_FIELDS[code]
  // 已知预设类型：按 OQ-01 白名单顺序；未知类型：退回设备骨架里的可写参数（防御）。
  const tags = allow
    ? allow.slice()
    : ((device && device.params) || []).map((p) => p.param_name)

  const seen = new Set()
  const result = []
  for (const tag of tags) {
    if (!wa[tag] || seen.has(tag)) continue
    seen.add(tag)
    const c = wa[tag]
    result.push({
      tag,
      label: c.label || tag,
      // 运行模式（mode）用「圆点」控件：四个圆点代表四状态，点哪个哪个生效，颜色区分当前态
      //（用户 2026-06-29 指定）；其余沿用后端控件类型。
      control: tag === 'mode' ? 'dots' : c.control,
      unit: c.unit,
      step: c.step || 1,
      min: c.min,
      max: c.max,
      options: c.options || [],
      optionLabels: (c.options || []).map((o) => o.label),
    })
  }
  return result
}

function toPanelDevice(device, writableAttrs) {
  return {
    deviceSn: String(device.device_sn),
    productCode: device.product_code,
    deviceName: device.device_name || '',
    controls: buildControls(device, writableAttrs),          // tab1「设置」
    allParams: (device.params && device.params.length) ? device.params : [], // tab2「详细」
  }
}

/**
 * 由结构骨架 + 后端 config 构建面板列表（纯函数，不读 MQTT 实时值）。
 * 实时值在模板层按 device_sn + param_name 叠加，故本函数不依赖 devices，面板对 MQTT 更新稳定。
 *
 * @param structure owner/structure 响应：{rooms:[{room_id,room_name,ori_room_name,devices:[...]}], system_devices:[...], sync_status}
 * @param config 后端 config：{writable_attrs, product_code_role, ...}
 * @returns Array<{id,title,devices:[{deviceSn,productCode,deviceName,controls,allParams}]}>
 */
export function buildPanels(structure, config) {
  if (!structure || structure.sync_status === 'pending') return []
  const wa = (config && config.writable_attrs) || {}
  const roleMap = (config && config.product_code_role) || {}
  const rooms = structure.rooms || []
  const sysDevices = structure.system_devices || []

  const allDevices = []
  for (const room of rooms) for (const d of (room.devices || [])) allDevices.push(d)
  for (const d of sysDevices) allDevices.push(d)

  const claimed = new Set()
  const panels = []

  // 1. 预设系统面板（按 product_code 抽取，标记已占用，避免重复进房间面板；一个面板可合并多个 code）
  for (const def of SYS_PANEL_ORDER) {
    const matched = allDevices.filter((d) => def.codes.includes(String(d.product_code)))
    if (matched.length === 0) continue
    matched.forEach((d) => claimed.add(String(d.device_sn)))
    panels.push({
      id: 'sys-' + def.codes.join('-'),
      title: def.title,
      devices: matched.map((d) => toPanelDevice(d, wa)),
    })
  }

  // 2. 房间面板（未被预设面板占用的房间设备；动态渲染——无设备的房间不出现）
  for (const room of rooms) {
    const devs = (room.devices || []).filter((d) => !claimed.has(String(d.device_sn)))
    if (devs.length === 0) continue
    devs.forEach((d) => claimed.add(String(d.device_sn)))
    panels.push({
      id: 'room-' + room.room_id,
      title: resolveRoomName(room),
      devices: devs.map((d) => toPanelDevice(d, wa)),
    })
  }

  // 3. 其余系统级设备（能量计 / 空气质量 / 未知），按 product_code 分组兜底，避免丢信息。
  //    用 Map 保插入顺序（普通对象会把数字串 key 按数值升序排，导致面板顺序错乱）。
  const leftover = sysDevices.filter((d) => !claimed.has(String(d.device_sn)))
  const byCode = new Map()
  for (const d of leftover) {
    const c = String(d.product_code || '')
    if (!byCode.has(c)) byCode.set(c, [])
    byCode.get(c).push(d)
  }
  for (const [code, devs] of byCode) {
    panels.push({
      id: 'sys-extra-' + code,
      title: EXTRA_SYS_TITLE[code] || roleMap[code] || '系统设备',
      devices: devs.map((d) => toPanelDevice(d, wa)),
    })
  }

  // 隐藏「真正为空」的面板：所有设备既无可设置控件、又无任何可展示属性（无 DeviceConfig 参数）。
  // 这类面板对用户无信息价值（多为未配置/未知 product_code 的系统设备），直接不渲染（用户 #4「没用就删」）。
  return panels.filter((p) =>
    p.devices.some((d) => d.controls.length > 0 || d.allParams.length > 0)
  )
}

/** 面板内是否存在任意可设置控件（用于 tab1「此设备无可设置项」占位判定）。 */
export function panelHasControls(panel) {
  return !!(panel && panel.devices && panel.devices.some((d) => d.controls.length > 0))
}

/**
 * 值展示格式化：可写属性按 options/unit 转中文（on→开 / cold→制冷 / 26→26℃）；
 * 只读属性（不在 writable_attrs）返回原值字符串。无值返回 null（由调用方决定占位文案）。
 */
export function formatValue(paramName, value, writableAttrs) {
  if (value === null || value === undefined || value === '') return null
  const c = (writableAttrs || {})[paramName]
  if (c && c.options && c.options.length) {
    const o = c.options.find((opt) => String(opt.value) === String(value))
    if (o) return o.label
  }
  if (c && c.unit) return `${value}${c.unit}`
  return String(value)
}
