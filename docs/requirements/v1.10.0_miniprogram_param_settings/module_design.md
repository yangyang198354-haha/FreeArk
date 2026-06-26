# 模块设计说明书

**版本**：v1.10.0_miniprogram_param_settings
**日期**：2026-06-26
**配套**：`architecture_design.md`（同目录）

---

## 1. 模块清单总览

| # | 模块 | 位置 | 类型 | 说明 |
|---|------|------|------|------|
| M1 | 屏端参数配置表 | `FreeArkWeb/backend/freearkweb/api/screen_param_config.py` | 新增·后端 | 可写白名单 + 控件/标签 + codec + productCode 角色 + mode联动 |
| M2 | config 接口 | `api/views_miniapp_device_settings.py` | 新增·后端 | `GET /api/miniapp/device-settings/config/` |
| M3 | audit 接口 | 同 M2 | 新增·后端 | `POST /api/miniapp/device-settings/audit/` |
| M4 | 路由注册 | `api/urls_miniapp.py` | 改·后端 | 追加两条 path |
| M5 | PLCWriteRecord.channel | `api/models.py` + 迁移 | 改·后端 | 新增可空 `channel` 字段 |
| M6 | MQTT 客户端封装 | `miniprogram/utils/screenMqtt.js` | 新增·前端 | mqtt.js + wxs，连接/订阅/解析/发布/重连 |
| M7 | 参数设置页 | `miniprogram/subpackages/control/pages/param-settings.vue` | 新增·前端 | 主页面 |
| M8 | API 调用补充 | `miniprogram/utils/api.js` | 改·前端 | 加 config/audit 两个调用 |
| M9 | 路由/入口 | `miniprogram/pages.json` + `pages/home/index.vue` | 改·前端 | 注册分包 + 首页入口卡片 |

---

## 2. 后端模块

### M1 `screen_param_config.py`（单一权威配置）
```python
# 屏端「可写」attrTag → 控件定义（对齐 web 可写白名单）
SCREEN_WRITABLE_ATTRS = {
  'switch':             {'control':'toggle','label':'开关',
                         'options':[{'value':'off','label':'关'},{'value':'on','label':'开'}]},
  'system_switch':      {'control':'toggle','label':'系统开关',
                         'options':[{'value':'off','label':'关'},{'value':'on','label':'开'}]},
  'temp_set':           {'control':'number','label':'温度设定','unit':'℃','step':0.5,'min':16,'max':30},
  'out_temp_set':       {'control':'number','label':'出风温度设定','unit':'℃','step':0.5,'min':10,'max':30},
  'mode':               {'control':'select','label':'运行模式',
                         'options':[{'value':'cold','label':'制冷'},{'value':'hot','label':'制热'},
                                    {'value':'wind','label':'通风'},{'value':'dehumidification','label':'除湿'}]},
  'energy_supply_mode': {'control':'select','label':'能源供应',
                         'options':[{'value':'cold','label':'制冷'},{'value':'hot','label':'制热'},
                                    {'value':'no','label':'无'}]},
  'energy_saving_sign': {'control':'toggle','label':'离家节能',
                         'options':[{'value':'off','label':'未启用'},{'value':'on','label':'启用'}]},
}
# productCode → 设备角色显示名（分组用）
PRODUCT_CODE_ROLE = {260001:'主温控器',120003:'末端温控',270001:'系统/能源主机',
                     130004:'新风',250001:'能量计',100007:'空气质量',10016:'面板'}
# 系统机改 mode 时联动的 energy_supply_mode（ADR-08，实测）
MODE_ENERGY_LINK = {'cold':'cold','hot':'hot','wind':'no','dehumidification':'cold'}
# 触发联动的设备 productCode（系统/能源主机）
LINK_PRODUCT_CODES = {270001}

def get_screen_param_config() -> dict:
    return {'writable_attrs':SCREEN_WRITABLE_ATTRS,'product_code_role':PRODUCT_CODE_ROLE,
            'mode_energy_link':MODE_ENERGY_LINK,'link_product_codes':list(LINK_PRODUCT_CODES)}

def is_writable_attr(attr_tag:str)->bool: return attr_tag in SCREEN_WRITABLE_ATTRS
```
> 取值范围 min/max 为保守默认（R-2）；如需精确，开发期从 web `DeviceAttrDef.num_value_json` 校准。

### M2 `GET /api/miniapp/device-settings/config/`（IsOwnerUser）
返回：
```json
{
  "broker": {"protocol":"wxs","host":"www.ttqingjiao.site","port":8084,
             "path":"/mqtt","username":"<env>","password":"<env>"},
  "topics": {"value_uplink":"/screen/upload/screen/to/cloud/{screenMac}",
             "write_downlink":"/screen/service/cloud/to/screen/{screenMac}"},
  "rooms": [ {"specific_part":"3-1-7-702","location_name":"...","screen_mac":"c5d29c52a237ade5"} ],
  "config": { ...get_screen_param_config()... }
}
```
- `rooms` 来自 `OwnerUserBinding.filter(user=request.user, active=True).select_related('owner')` → 取 `owner.specific_part / location_name / unique_id`。**只返回业主自己的房间**。
- broker username/password 取 `settings.SCREEN_MQTT_USERNAME/PASSWORD`（env，ADR-07）。
- 安全：无 active 绑定 → `rooms:[]`（前端提示先去绑定）。

### M3 `POST /api/miniapp/device-settings/audit/`（IsOwnerUser）
请求：`{request_id, specific_part, screen_mac, device_sn, items:[{attr_tag,attr_value,old_value?}]}`
处理：
1. 校验 `screen_mac` 属于该业主 active 绑定（`OwnerUserBinding`→`owner.unique_id==screen_mac`）；否 → 403。
2. 校验每个 `attr_tag` ∈ `SCREEN_WRITABLE_ATTRS`；否 → 400。
3. 为每个 item 建 `PLCWriteRecord(channel='screen-mqtt', specific_part, param_name=attr_tag, old_value, new_value=attr_value, operator=request.user.username, status='reported', request_id)`。
返回 `202 {recorded:n}`。
> 仅审计留痕，不回放/不下发（下发已由客户端直连完成）。status 用 `'reported'` 区别于 s7 的 pending/success。

### M4 `urls_miniapp.py`（追加）
```python
path('device-settings/config/', v.device_settings_config, name='miniapp-ds-config'),  # IsOwnerUser
path('device-settings/audit/',  v.device_settings_audit,  name='miniapp-ds-audit'),   # IsOwnerUser
```

### M5 `PLCWriteRecord.channel`
```python
channel = models.CharField(max_length=16, null=True, blank=True, default='s7')  # 's7' | 'screen-mqtt'
```
- 迁移 **scoped 手写**（仅加该字段，勿用 makemigrations 全产物，见 [[project-migration-drift-handwrite-scoped]]）；先 `git fetch` 对齐迁移号避免撞车。
- 旧数据 default='s7'，web 链路读写不受影响（C-01）。`device_settings_records` 视图可选加 `channel` 过滤（不破坏现有）。

---

## 3. 前端模块

### M6 `utils/screenMqtt.js`（MQTT 封装）
```
class ScreenMqtt {
  connect(broker)            // mqtt.connect('wxs://host:port/path',{username,password,...})
  subscribeRoom(screenMac)   // sub value_uplink + write_downlink(可选)
  onDeviceUpdate(cb)         // 解析 DeviceStatusUpdate → cb({deviceSn,productCode,attrs:{tag:val}})
  writeAttrs(screenMac, deviceSn, items) // 发 DeviceWrite，返回 request_id
  waitConfirm(deviceSn, attrTag, target, timeoutMs=8000) // Promise，监听值反映
  disconnect()
}
```
- 解析：`payload.data.{deviceSn,productCode,items}`；deviceSn 字符串/整数都转 String 归一（实测两种都有）。
- 发布 DeviceWrite envelope 见 architecture §3.4；`messageId` 用 `Date.now()` 串；自定义 `request_id`（uuid）放 `payload.data.requestId`（屏端忽略未知字段，仅供本端审计关联）。
- 重连：mqtt.js 自带；断线 UI 置「连接中」。
- 微信内存：页面 `onUnload` 必 `disconnect()`。

### M7 `subpackages/control/pages/param-settings.vue`
- `onLoad`：取 `specific_part`（从首页入口带入；多房间时先选房间）。
- 流程：`api.getDeviceSettingsConfig()` → 找到该 specific_part 的 screen_mac+config → `ScreenMqtt.connect+subscribeRoom`。
- 渲染：按 deviceSn 分组卡片（标题=`PRODUCT_CODE_ROLE[productCode]` + deviceSn），卡片内列**可写 attr**控件（toggle/number/select，用 config.writable_attrs 标签与选项）；当前值来自实时 `onDeviceUpdate`。
- 编辑→提交：`ScreenMqtt.writeAttrs(...)`；若 deviceSn.productCode∈link_product_codes 且改了 mode → 追加 `energy_supply_mode = mode_energy_link[mode]`。
- 确认：`waitConfirm` → 成功 toast / 超时提示。
- 审计：成功路径 `api.reportDeviceSettingsAudit({...})`（失败静默，不阻断）。
- 隔离：页面只在 config.rooms 内房间操作；越权由后端接口兜（UI 不提供他人房间）。

### M8 `utils/api.js`（追加）
```js
getDeviceSettingsConfig: () => http.get('/api/miniapp/device-settings/config/'),
reportDeviceSettingsAudit: (data) => http.post('/api/miniapp/device-settings/audit/', data),
```

### M9 `pages.json` + `pages/home/index.vue`
- `pages.json` subPackages 追加：
  ```json
  {"root":"subpackages/control","pages":[{"path":"pages/param-settings",
     "style":{"navigationBarTitleText":"参数设置"}}]}
  ```
- 业主首页加「设备参数设置」入口卡片 → `uni.navigateTo('/subpackages/control/pages/param-settings?specific_part=...')`（specific_part 取自 bind/status，多房间则进页内选）。

---

## 4. 消息 schema（实测，开发对照）

**DeviceWrite（本端→broker，云→屏 topic）**
```json
{"header":{"name":"DeviceWrite","messageId":"1782445674746","sn":"22154","screenMac":"c5d29c52a237ade5"},
 "payload":{"code":200,"message":"","data":{"deviceSn":"22154","requestId":"<uuid>",
   "items":[{"attrTag":"mode","attrValue":"dehumidification"}]}}}
```
**DeviceStatusUpdate（broker→本端，上行 topic /screen/upload/...）**
```json
{"header":{"ackCode":1,"messageId":"2718","name":"DeviceStatusUpdate","screenMac":"c5d29c52a237ade5"},
 "payload":{"code":200,"data":{"deviceSn":22158,"productCode":260001,
   "items":[{"attrTag":"temp_set","attrValue":"26.0"}, ...]}}}
```

## 5. 边界与异常

| 场景 | 处理 |
|------|------|
| 业主无绑定房间 | config.rooms 空 → 页面提示去绑定 |
| broker 连不上 | UI「连接失败，请重试」；不产生假成功 |
| 8s 内无值反映 | 标「未确认」，提示重试/刷新（无 ack，ADR-04） |
| deviceSn 字符串/整数 | 归一为 String 比较 |
| 系统关机态改 mode 不生效 | waitConfirm 超时即提示（实测关机态可能不响应） |
| 审计上报失败 | 静默；不影响下发结果 |
| 越权 screenMac | 后端 config 不下发他人房间；audit 403 |

## 6. 测试要点（供 test-engineer）
- 后端单元：config 只返回自己房间（隔离）、audit 越权 403、非白名单 attr 400、PLCWriteRecord.channel 正确、web `device_settings` 回归不受 channel 影响。
- 前端：envelope 构造正确、mode 联动 energy_supply_mode、waitConfirm 成功/超时、归一化 deviceSn、onUnload 断连。
- e2e（真机或 mock broker）：连接→渲染→改 temp_set/switch/mode→值反映确认→审计入库。
