# 模块设计文档

**文档编号**: ARCH-MODULE-DEVICE-SETTINGS-001  
**项目名称**: FreeArk 设备参数设置功能  
**版本**: 0.4.0-APPROVED  
**状态**: APPROVED（v0.4.0：2026-05-19 P1~P5 模块 diff + Q10~Q12 落地；PM 门控通过）  
**创建日期**: 2026-05-19  
**最后更新**: 2026-05-19  
**作者**: system-architect (via pm-orchestrator)  
**审核**: pm-orchestrator（v0.4.0 增量模块设计门控通过）

---

## 1. 模块总览

```
┌─────────────────────────────────────────────────────────────────────┐
│  前端 (Vue 3 + Element Plus + mqtt.js)                              │
│  ┌─────────────────────┐   ┌──────────────────────────────────┐    │
│  │ DeviceManagement    │   │ DeviceSettingsPanelView.vue      │    │
│  │ DeviceListView.vue  │──→│ (弹窗/抽屉)                      │    │
│  │ [新增"设置"按钮]     │   │  ├─ 参数分组列表                 │    │
│  └─────────────────────┘   │  ├─ 可写控件 / 只读文本          │    │
│                             │  ├─ 下发按钮 + 状态              │    │
│  ┌─────────────────────┐   │  └─ WebSocket 状态指示           │    │
│  │ PlcWriteRecord      │   └──────────────────────────────────┘    │
│  │ View.vue            │        ↑↓ useMqttWebSocket.js              │
│  │ (审计日志查询页)     │   ┌──────────────────────────────────┐    │
│  └─────────────────────┘   │ mqtt.js                          │    │
│                             │ WebSocket ws://192.168.31.98:32797/mqtt │
│                             └──────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
         │ HTTP (Axios + Token)                  ↑ WebSocket (MQTT)
         ↓                                       │
┌─────────────────────────────────────────────┐  │
│  Django 后端 (DRF + paho-mqtt)              │  │
│  ┌─────────────────────────────────────┐   │  │
│  │ views_device_settings.py           │   │  │
│  │  ├─ GET  /api/device-settings/     │   │  │
│  │  │       params/{specific_part}/   │   │  │
│  │  ├─ POST /api/device-settings/     │   │  │
│  │  │       write/                    │   │  │
│  │  └─ GET  /api/device-settings/     │   │  │
│  │          records/                  │   │  │
│  └─────────────────────────────────────┘   │  │
│  ┌─────────────────────────────────────┐   │  │
│  │ models.py (PLCWriteRecord)          │   │  │
│  └─────────────────────────────────────┘   │  │
└─────────────────────────────────────────────┘  │
         │ MQTT publish (QoS=1)                   │ MQTT ack
         ↓                                        │
┌──────────────────────────────────────────────────────────┐
│  MQTT Broker (192.168.31.98:32788)                       │
│  TCP port: 32788  |  WebSocket port: 32797 (已确认)      │
└──────────────────────────────────────────────────────────┘
         │ MQTT subscribe                         │
         ↓                                        │
┌─────────────────────────────────────────────┐  │
│  datacollection 进程 (物理机进程)            │  │
│  ┌─────────────────────────────────────┐   │  │
│  │ PLCWriteSubscriber (新增线程)        │   │  │
│  │  ├─ 订阅 /datacollection/plc/       │   │  │
│  │  │   write/command/{specific_part}  │   │  │
│  │  ├─ 调用 PLCWriteManager.write_db_  │   │  │
│  │  │   data(db_num, offset, val, type)│   │  │
│  │  └─ 发布回执到 /ack/{specific_part} │───┘  │
│  └─────────────────────────────────────┘      │
│  (现有) PLCWriteManager, MQTTClient, ...       │
└─────────────────────────────────────────────────┘
         │ snap7 (S7 协议)
         ↓
┌──────────────────────────────────────────────┐
│  PLC 设备 (各户 IP，来自 OwnerInfo.plc_ip)   │
└──────────────────────────────────────────────┘
         │ 写入成功后，采集侧照常读取
         ↓
┌──────────────────────────────────────────────┐
│  MySQL DB (192.168.31.98:3306)               │
│  ├─ plc_write_record（新增）                 │
│  ├─ plc_latest_data（读取当前值，不改动）    │
│  ├─ device_config（读取参数分组，不改动）    │
│  ├─ device_attr_def（读取值域约束，不改动）  │
│  └─ owner_info（读取 plc_ip_address，不改动）│
└──────────────────────────────────────────────┘
```

---

## 2. 后端 API 模块

### 2.1 GET /api/device-settings/params/{specific_part}/

**功能**：查询指定设备的参数列表（含分组、当前值、是否可写、值域约束）

**权限**：`IsAuthenticated`

**响应结构**：

```json
{
  "specific_part": "3-1-7-702",
  "groups": [
    {
      "sub_type": "main_thermostat",
      "sub_type_display": "主温控器",
      "params": [
        {
          "param_name": "living_room_temp_setting",
          "display_name": "客厅温度设置",
          "current_value": 26,
          "is_writable": true,
          "attr_value_type": 2,
          "num_value_json": "{\"min\": 16, \"max\": 30, \"step\": 0.5}",
          "select_values_json": ""
        },
        {
          "param_name": "living_room_temperature",
          "display_name": "客厅实际温度",
          "current_value": 24,
          "is_writable": false,
          "attr_value_type": 2,
          "num_value_json": "",
          "select_values_json": ""
        }
      ]
    }
  ]
}
```

**查询逻辑**：

```python
# 伪代码
def get_device_params(specific_part):
    # 1. 获取 DeviceConfig（is_active=True 的参数分组配置）
    configs = DeviceConfig.objects.filter(is_active=True).order_by('sub_type', 'param_name')
    
    # 2. 获取当前值（批量查询 PLCLatestData）
    latest_map = {r.param_name: r.value 
                  for r in PLCLatestData.objects.filter(specific_part=specific_part)}
    
    # 3. 获取值域约束（DeviceAttrDef，通过 attr_tag = param_name 匹配）
    attr_defs = {d.attr_tag: d 
                 for d in DeviceAttrDef.objects.filter(
                     attr_tag__in=[c.param_name for c in configs])}
    
    # 4. 判断 is_writable（按 Q2 白名单规则）
    WRITABLE_SUFFIXES = ('_temp_setting', '_switch')
    READONLY_SUFFIXES = ('_temperature', '_humidity', '_dew_point', '_error', '_alert', '_fault')
    def is_writable(param_name):
        return (any(param_name.endswith(s) for s in WRITABLE_SUFFIXES) and
                not any(param_name.endswith(s) for s in READONLY_SUFFIXES))
    
    # 5. 组装分组结构返回
```

---

### 2.2 POST /api/device-settings/write/

**功能**：接收前端写入命令，记录操作，发布 MQTT

**权限**：`IsAuthenticated`

**请求体**：

```json
{
  "specific_part": "3-1-7-702",
  "param_name": "living_room_temp_setting",
  "new_value": 26
}
```

**响应**：202 Accepted

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "命令已下发，等待结果...",
  "status": "pending"
}
```

**处理逻辑**：

```python
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def device_setting_write(request):
    specific_part = request.data['specific_part']
    param_name = request.data['param_name']
    new_value = request.data['new_value']
    
    # 权限校验：IsAuthenticated 即可（Q8：所有登录用户均可写）
    
    # 参数合法性校验：param_name 必须在 is_writable=true 列表中
    
    # 查询旧值（快照）
    old_value = PLCLatestData.objects.filter(
        specific_part=specific_part, param_name=param_name
    ).values_list('value', flat=True).first()
    
    # 查询 PLC IP
    plc_ip = OwnerInfo.objects.get(specific_part=specific_part).plc_ip_address
    
    # 生成 request_id
    request_id = str(uuid.uuid4())
    
    # 写 DB（在 Django ORM 事务中）
    with transaction.atomic():
        PLCWriteRecord.objects.create(
            request_id=request_id,
            specific_part=specific_part,
            param_name=param_name,
            old_value=str(old_value) if old_value is not None else '',
            new_value=str(new_value),
            operator=request.user.username,
            status='pending',
        )
    
    # 发布 MQTT 命令
    payload = json.dumps({
        'request_id': request_id,
        'specific_part': specific_part,
        'plc_ip': plc_ip,
        'param_name': param_name,
        'new_value': new_value,
        'operator': request.user.username,
    })
    topic = f'/datacollection/plc/write/command/{specific_part}'
    result = mqtt_client.publish(topic, payload, qos=1)
    
    if result.rc != MQTT_ERR_SUCCESS:
        PLCWriteRecord.objects.filter(request_id=request_id).update(
            status='failed', error_message='MQTT broker 不可达'
        )
        return Response({'error': '下发通道异常，请稍后重试'}, status=503)
    
    return Response({'request_id': request_id, 'status': 'pending'}, status=202)
```

---

### 2.3 GET /api/device-settings/records/

**功能**：审计日志查询（FR6）

**权限**：`IsAuthenticated`

**查询参数**：`specific_part`（可选）、`start_time`、`end_time`、`operator`、`status`、`page`（默认 1）

**响应**：分页列表（每页 20 条，按 `created_at` 降序）

---

### 2.4 POST /api/device-settings/rollback/ — 延后至下期，本期不实现

**状态**：DEFERRED（2026-05-19 用户确认，本期不实现）。

本期不提供回滚接口，审计日志页面为只读。下期实现时重新设计此接口，预留设计：
- 以原记录 `old_value` 作为 `new_value` 重新下发一条写命令
- 在新记录的 `error_message` 字段记录 `rollback_from={source_request_id}`（字段本期已建，但本期不写入此值）

---

## 3. 数据库表结构

### 3.1 新增表：plc_write_record

```sql
CREATE TABLE plc_write_record (
    id             BIGINT AUTO_INCREMENT PRIMARY KEY,
    request_id     VARCHAR(64) NOT NULL UNIQUE COMMENT '唯一写入请求ID（UUID）',
    specific_part  VARCHAR(20) NOT NULL COMMENT '目标设备四段标识',
    param_name     VARCHAR(100) NOT NULL COMMENT '参数名（对应 plc_config.json 键名）',
    old_value      VARCHAR(50) NOT NULL DEFAULT '' COMMENT '写前快照值（来自 plc_latest_data）',
    new_value      VARCHAR(50) NOT NULL COMMENT '目标写入值',
    operator       VARCHAR(150) NOT NULL COMMENT '发起用户 username',
    status         VARCHAR(20) NOT NULL DEFAULT 'pending' 
                   COMMENT '状态：pending/success/failed/timeout',
    error_message  TEXT NULL COMMENT '失败原因或回滚溯源',
    created_at     DATETIME NOT NULL COMMENT '命令下发时间',
    acked_at       DATETIME NULL COMMENT '收到回执时间',
    INDEX idx_sp_created (specific_part, created_at),
    INDEX idx_status_created (status, created_at),
    INDEX idx_operator (operator),
    INDEX idx_request_id (request_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='PLC参数写入操作记录';
```

**Django Model**：

```python
class PLCWriteRecord(models.Model):
    STATUS_CHOICES = (
        ('pending', '待回执'),
        ('success', '写入成功'),
        ('failed', '写入失败'),
        ('timeout', '超时未回执'),
    )
    request_id = models.CharField(max_length=64, unique=True)
    specific_part = models.CharField(max_length=20, db_index=True)
    param_name = models.CharField(max_length=100)
    old_value = models.CharField(max_length=50, default='')
    new_value = models.CharField(max_length=50)
    operator = models.CharField(max_length=150)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    acked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'plc_write_record'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['specific_part', 'created_at']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['operator']),
        ]
```

### 3.2 不改动的表

| 表名 | 用途（只读） |
|------|------------|
| `device_config` | 读取参数分组和 display_name |
| `device_attr_def` | 读取值域约束（attr_value_type, num_value_json, select_values_json）|
| `plc_latest_data` | 读取参数当前值；写入成功后由采集侧自动更新（无需手动维护）|
| `owner_info` | 读取 plc_ip_address |

---

## 4. 前端模块

### 4.1 DeviceManagementDeviceListView.vue（修改）

**改动范围**：操作列新增"设置"按钮，约 8~12 行代码：

```vue
<el-button
  type="warning"
  link
  size="small"
  @click="handleOpenSettings(row)"
>
  设置
</el-button>

<!-- 在 methods 中 -->
handleOpenSettings(row) {
  this.settingsSpecificPart = row.specific_part;
  this.settingsDialogVisible = true;
}
```

新增 `<DeviceSettingsPanelView>` 组件引用和对应的 dialog 控制变量。

---

### 4.2 DeviceSettingsPanelView.vue（新增）

**组件职责**：
- 接收 `specific_part` prop，mount 时调用 `GET /api/device-settings/params/{specific_part}/`
- 按 `sub_type` 渲染 `el-collapse` 分组，每个分组内渲染参数行
- 可写参数（`is_writable=true`）：枚举型渲染 `el-select`（options 来自 `select_values_json`），数值型渲染 `el-input-number`（range 来自 `num_value_json`）
- 只读参数（`is_writable=false`）：渲染纯文本
- mount 时调用 `useMqttWebSocket` composable，订阅 `/datacollection/plc/write/ack/{specific_part}`
- unmount 时断开 WebSocket 订阅

**状态管理**：

```javascript
const writeStatus = ref({})  // { [param_name]: 'idle' | 'loading' | 'success' | 'failed' | 'timeout' }
const requestMap = ref({})   // { [param_name]: request_id }  // 用于超时计时器关联
```

**下发逻辑**：

```javascript
async function handleSubmit(param_name, new_value) {
  writeStatus.value[param_name] = 'loading'
  const res = await axios.post('/api/device-settings/write/', {
    specific_part: props.specificPart,
    param_name,
    new_value
  })
  requestMap.value[param_name] = res.data.request_id
  
  // 启动 30s 超时计时器
  setTimeout(() => {
    if (writeStatus.value[param_name] === 'loading') {
      writeStatus.value[param_name] = 'timeout'
    }
  }, 30000)
}
```

**MQTT 回执处理**：

```javascript
// useMqttWebSocket 触发的 onMessage 回调
function handleAck(message) {
  const data = JSON.parse(message.payload)
  const param_name = Object.keys(requestMap.value)
    .find(k => requestMap.value[k] === data.request_id)
  if (!param_name) return
  
  if (data.success) {
    writeStatus.value[param_name] = 'success'
    // 更新显示值（乐观更新）
    updateCurrentValue(param_name, data.value)
  } else {
    writeStatus.value[param_name] = 'failed'
    errorMessage.value[param_name] = data.error_message
  }
}
```

---

### 4.3 useMqttWebSocket.js（新增 Composable）

**功能**：封装 mqtt.js 的 WebSocket 连接生命周期

```javascript
// composables/useMqttWebSocket.js
import mqtt from 'mqtt'

export function useMqttWebSocket(brokerWsUrl, topic, onMessage) {
  let client = null
  
  const connect = () => {
    client = mqtt.connect(brokerWsUrl)  // 'ws://192.168.31.98:32797/mqtt'
    client.on('connect', () => {
      client.subscribe(topic, { qos: 1 })
    })
    client.on('message', (receivedTopic, payload) => {
      onMessage({ topic: receivedTopic, payload: payload.toString() })
    })
  }
  
  const disconnect = () => {
    if (client) {
      client.end()
      client = null
    }
  }
  
  return { connect, disconnect }
}
```

**配置常量**（可放在 `src/config/mqtt.js`）：

```javascript
export const MQTT_BROKER_WS_URL = import.meta.env.VITE_MQTT_WS_URL 
  || 'ws://192.168.31.98:32797/mqtt'
```

---

### 4.4 PlcWriteRecordView.vue（新增，本期只读）

**功能**：审计日志查询页面（FR6，本期只读，无回滚按钮）

- 顶部过滤栏：`specific_part` 输入框、时间范围选择器（`el-date-picker`）、`operator` 输入框、`status` 下拉
- 表格展示所有字段（FR6-3/FR6-4），分页 20 条/页
- **本期不显示"回滚"按钮**（回滚功能延后至下期，见 Out of Scope 第 6 条）

---

## 5. datacollection 模块

### 5.1 PLCWriteSubscriber（新增）

**文件**：`datacollection/plc_write_subscriber.py`

```python
import json
import threading
import uuid
import requests
from datacollection.plc_write_manager import PLCWriteManager
from datacollection.mqtt_client import MQTTClient
from datacollection.log_config_manager import get_logger

logger = get_logger('plc_write_subscriber')

class PLCWriteSubscriber:
    """订阅 MQTT 写命令 topic，执行 snap7 写入，发布回执"""
    
    COMMAND_TOPIC_PATTERN = '/datacollection/plc/write/command/#'
    ACK_TOPIC_TEMPLATE = '/datacollection/plc/write/ack/{specific_part}'
    
    def __init__(self, mqtt_broker, mqtt_port, plc_config_path, django_api_url):
        self.mqtt_client = MQTTClient(broker=mqtt_broker, port=mqtt_port)
        self.plc_writer = PLCWriteManager()
        self.plc_config = self._load_plc_config(plc_config_path)
        self.django_api_url = django_api_url  # 用于更新 DB（或直接写 DB）
        self._processed_requests = set()  # 幂等去重缓存（内存，进程级）
    
    def start(self):
        """在独立线程中启动订阅循环"""
        thread = threading.Thread(target=self._run, daemon=True, name='PLCWriteSubscriber')
        thread.start()
        logger.info('PLCWriteSubscriber 线程已启动')
    
    def _run(self):
        self.mqtt_client.connect()
        self.mqtt_client.subscribe(self.COMMAND_TOPIC_PATTERN, qos=1)
        self.mqtt_client.on_message = self._handle_message
        self.mqtt_client.loop_forever()
    
    def _handle_message(self, topic, payload):
        try:
            cmd = json.loads(payload)
            request_id = cmd['request_id']
            specific_part = cmd['specific_part']
            plc_ip = cmd['plc_ip']
            param_name = cmd['param_name']
            new_value = cmd['new_value']
            
            # 幂等检查
            if request_id in self._processed_requests:
                logger.info(f'重复消息，跳过: {request_id}')
                return
            
            # 查找 plc_config.json
            if param_name not in self.plc_config['parameters']:
                self._publish_ack(specific_part, request_id, success=False,
                                  error_message=f'param_name {param_name} 未定义')
                return
            
            param_cfg = self.plc_config['parameters'][param_name]
            db_num = param_cfg['db_num']
            offset = param_cfg['offset']
            data_type = param_cfg['data_type']
            
            # 执行写入
            ok, error_msg = self._write_plc(plc_ip, db_num, offset, new_value, data_type)
            
            # 发布回执
            self._publish_ack(specific_part, request_id, 
                              success=ok, value=new_value, error_message=error_msg)
            
            # 更新 DB（调用 Django API 或直接 ORM，取决于是否在同一进程）
            self._update_db_record(request_id, ok, error_msg)
            
            self._processed_requests.add(request_id)
            
        except Exception as e:
            logger.error(f'处理写命令时发生异常: {e}', exc_info=True)
    
    def _write_plc(self, plc_ip, db_num, offset, value, data_type):
        try:
            self.plc_writer.write_db_data(db_num, offset, value, data_type)
            return True, None
        except Exception as e:
            return False, str(e)
    
    def _publish_ack(self, specific_part, request_id, success, value=None, error_message=None):
        topic = self.ACK_TOPIC_TEMPLATE.format(specific_part=specific_part)
        payload = {
            'request_id': request_id,
            'specific_part': specific_part,
            'success': success,
        }
        if success:
            payload['value'] = value
        else:
            payload['error_message'] = error_message
        
        import datetime
        payload['written_at'] = datetime.datetime.utcnow().isoformat()
        
        self.mqtt_client.publish(topic, json.dumps(payload), qos=1)
    
    def _update_db_record(self, request_id, success, error_message):
        """调用 Django API 更新 plc_write_record 状态（或直接写 DB）"""
        # 若 PLCWriteSubscriber 在独立进程中，通过 HTTP 调用 Django API
        # 若在 Django 进程内，直接使用 ORM
        pass
```

**集成到 ImprovedDataCollectionManager**：

在 `improved_data_collection_manager.py` 的 `start()` 方法中增加：

```python
from datacollection.plc_write_subscriber import PLCWriteSubscriber

# 在现有采集任务启动后
self.write_subscriber = PLCWriteSubscriber(
    mqtt_broker='192.168.31.98',
    mqtt_port=32788,
    plc_config_path=get_resource_path('plc_config.json'),
    django_api_url='http://localhost:8000'
)
self.write_subscriber.start()
```

---

## 6. 回执更新 DB 的两种方案

由于 `PLCWriteSubscriber` 可能运行在独立进程（datacollection）而非 Django 进程中，更新 DB 有两种方式：

**方案 A（推荐）**：Django 后端同时订阅回执 topic

在 Django `mqtt_consumer.py` 的现有 `MQTTConsumer` 中，新增订阅 `/datacollection/plc/write/ack/#`，收到回执时直接用 ORM 更新 `PLCWriteRecord`。

```python
# 在 MQTTConsumer.on_connect 中追加订阅
self.client.subscribe('/datacollection/plc/write/ack/#', qos=1)

# 在 on_message 中新增分支
if topic.startswith('/datacollection/plc/write/ack/'):
    self._handle_write_ack(payload)

def _handle_write_ack(self, payload):
    data = json.loads(payload)
    request_id = data['request_id']
    PLCWriteRecord.objects.filter(request_id=request_id).update(
        status='success' if data['success'] else 'failed',
        acked_at=timezone.now(),
        error_message=data.get('error_message', ''),
    )
```

**方案 B**：PLCWriteSubscriber 通过内部 API 调用 Django 接口（HTTP POST）更新状态。适合独立进程部署场景。

**推荐方案 A**，因为 Django MQTT 消费者已经在后台运行且已连接同一 broker，零额外进程开销。

---

## v0.4.0 增量模块 Diff（基于 Q10~Q12 决策 + P1~P5）

---

### MOD-DIFF-01：新增 `api/param_value_label.py`（P3/Q11）

**状态**：新增文件，不影响任何现有模块。

**结构**：见 `architecture_design.md` 章节 "P3 — 人类可读映射"。

**与现有模块的接口**：
- 由 `views_device_settings.py` 的 `device_settings_params` 函数 import 并调用 `get_value_options(param_name)` 和 `get_display_value(param_name, raw_value)`
- 不需要 Django model、ORM、DB 访问
- 不影响 `mqtt_consumer.py`、`plc_write_subscriber.py`、任何前端文件

---

### MOD-DIFF-02：`api/views_device_settings.py` 改动清单（P2/P3/P4/P5）

| 函数 | 变更类型 | 变更说明 |
|------|---------|---------|
| `device_settings_params` | 修改 | P5：在 `groups[key]['params'].append(...)` 前加 `if not _is_writable(cfg.param_name): continue`；P3：追加 `display_value` + `value_options` 字段（调用 `param_value_label` 函数） |
| `device_settings_write` | 修改 | P4：请求体改为接受 `items: [{param_name, new_value}]` 数组；循环为每个 item 创建 `PLCWriteRecord` 行（共享 `batch_request_id`，各自唯一 `request_id`）；MQTT publish payload 改为 v0.4.0 批量 schema |
| `_get_mqtt_client` | 修改 | P2：加 `client.is_connected()` 检查，未连接时返回明确错误（`"MQTT_UNREACHABLE"`）而非静默返回不可用 client |

**对 v0.3.0 已部署行为的影响**：
- `device_settings_params`：过滤只读参数（P5），响应字段增加（P3），接口 URL 不变，前端需更新渲染逻辑
- `device_settings_write`：接口协议变化（单字段 → items 数组），**前端必须同步更新**，否则原有单字段下发调用将返回 400

---

### MOD-DIFF-03：`api/serializers_device_settings.py` 改动（P4）

`DeviceSettingWriteSerializer` 修改：

```python
# v0.4.0
class BatchWriteItemSerializer(serializers.Serializer):
    param_name = serializers.CharField(max_length=100)
    new_value = serializers.CharField(max_length=50)

class DeviceSettingWriteSerializer(serializers.Serializer):
    specific_part = serializers.CharField(max_length=20)
    items = BatchWriteItemSerializer(many=True, min_length=1, max_length=20)
```

---

### MOD-DIFF-04：`datacollection/plc_write_subscriber.py` 改动（P2/P4）

| 方法 | 变更类型 | 变更说明 |
|------|---------|---------|
| `_on_command` | 修改 | P4：解析 `cmd.get('items', [])` 替代单 `param_name/new_value`；循环每个 item 调用 `_write_plc`；汇总 item 结果列表；P2：增加入口 `logger.info` 日志（`topic` + `request_id`） |
| `_publish_ack` | 修改 | P4：payload 改为含 `items: [{param_name, success, error_message}]` 的整体 ack（方案 A） |
| `_write_plc` | 不变 | 单次写入逻辑复用 |

**对 `freeark-task-scheduler` 服务的影响**：需重启服务使改动生效；协议变化后旧格式 command 将无法被正确处理（需前后端同步上线）。

---

### MOD-DIFF-05：`DeviceSettingsPanelView.vue` 改动（P2/P3/P4/P5）

| 功能 | 变更类型 | 变更说明 |
|------|---------|---------|
| 参数渲染 | 修改 | P3：枚举类下拉 `options` 改用 `row.value_options`（`[{raw, label}]`），`v-model` 绑定 `raw` 值；当前值展示改用 `row.display_value` |
| 只读参数过滤 | 简化 | P5：后端已过滤，前端 `v-if="row.is_writable"` 保留为防御性 guard，无业务逻辑变化 |
| 提交逻辑 `handleSubmit` | 修改 | P4：不再逐行调用，改为汇总所有 `inputValues` 变化生成 `items` 数组，单次 POST；P4：取消按钮还原 `inputValues` 为 `loadParams` 时的快照值 |
| 错误展示 | 修改 | P2：ack 回执中 `items[].error_message` 分类展示（`MQTT_UNREACHABLE` / `SUBSCRIBER_NOT_CONSUMING` / `PLC_WRITE_FAILED`） |
| MQTT ack 处理 `handleAck` | 修改 | P4：从 `ack.items[]` 遍历更新每个 param_name 的 `writeStatus` 和 `currentValues` |

---

### MOD-DIFF-06：`PLCWriteRecord` model 可选变更（P4/Q12）

**Q12**：`new_value` 字段语义不变（存 PLC 原始值），无 model 变化。

**P4 `batch_request_id` 方案**（推荐，零风险 migration）：

```python
# 在 PLCWriteRecord model 新增字段
batch_request_id = models.CharField(max_length=64, null=True, blank=True, db_index=True,
                                     help_text='批量下发时的批次ID，对应 MQTT command 的 request_id')
```

- 单字段下发时：`batch_request_id=None`，`request_id=UUID`（唯一）
- 批量下发时：`batch_request_id=<command_request_id>`，`request_id=UUID`（各自唯一，N 行共享同一 `batch_request_id`）
- `request_id` 的 `UNIQUE` 约束不变，审计页按 `batch_request_id` 分组即可查看批次

**Migration**：新增 `0024_plcwriterecord_batch_request_id.py`（追加可空字段，无数据风险）。

---

### MOD-DIFF-07：`mqtt_consumer._handle_write_ack` 适配（P4）

现有 `_handle_write_ack` 按单 `request_id` 更新单行，P4 ack 为整体含 `items[]`。需改为：

```python
def _handle_write_ack(self, payload):
    # ...（解析 data）
    batch_request_id = data.get('request_id')
    items = data.get('items', [])
    written_at = timezone.now()
    for item in items:
        param_name = item.get('param_name')
        success = item.get('success', False)
        # 按 batch_request_id + param_name 定位行
        PLCWriteRecord.objects.filter(
            batch_request_id=batch_request_id, param_name=param_name, status='pending'
        ).update(
            status='success' if success else 'failed',
            acked_at=written_at,
            error_message=item.get('error_message', '') if not success else None,
        )
```

**对 `mqtt_consumer.py` 的影响**：该文件为已在线 `freeark-mqtt-consumer` 服务，改动后需重启服务。
