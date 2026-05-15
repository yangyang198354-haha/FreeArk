# 自由方舟App MQTT消息机制完整分析

## 一、MQTT架构概述

自由方舟App采用MQTT协议与云端进行双向通信，主要包含**消息发送**和**消息订阅**两大模块。

```
┌─────────────────────────────────────────────────────────────────┐
│                        MQTT Broker                              │
│                    tcp://{host}:11883                           │
└──────────────────────────┬──────────────────────────────────────┘
                           │
        ┌──────────────────┴──────────────────┐
        ▼                                     ▼
┌─────────────────┐                   ┌─────────────────┐
│   消息发送      │                   │   消息订阅      │
│ (App → Cloud)  │                   │ (Cloud → App)  │
└─────────────────┘                   └─────────────────┘
```

---

## 二、MQTT连接配置

| 参数 | 值 | 说明 |
|------|-----|------|
| **Broker地址** | `tcp://{MQTT_SERVER_HOST}:11883` | 动态获取自HttpConsts |
| **用户名** | `admin` | 固定值 |
| **密码** | `public` | 固定值 |
| **ClientID** | `appId` (设备MAC地址) | 唯一标识 |
| **连接超时** | 3秒 | 连接超时时间 |
| **心跳间隔** | 20秒 | KeepAlive周期 |
| **自动重连** | true | 断开自动重连 |
| **最大消息数** | 1000 | 飞行消息队列 |

---

## 三、消息发送（App → Cloud）

### 3.1 发送主题列表

| 主题前缀 | 完整格式 | QoS | 作用 |
|---------|---------|-----|------|
| `COMMON_SCREEN_2_CLOUD_TOPIC` | `/screen/service/screen/to/cloud/{mac}` | 0 | 通用上行消息 |
| `COMMON_UPDATA_TOPIC` | `/screen/upload/screen/to/cloud/{mac}` | 0 | 数据更新消息 |
| `COMMON_UPLOAD_OPT_TOPIC` | `/screen/event/status/change/{mac}` | 0 | 操作事件上报 |
| `COMMON_LOG_TOPIC` | `/screen/log/screen/to/cloud/{mac}` | 0 | 日志上报 |

### 3.2 发送消息类型详解

#### 1. 设备状态更新 (`DeviceStatusUpdate`)

**接口定义**: `MqttApi.sendDeviceUpdateMsg()`

**触发场景**: 设备属性变化时主动上报

**输入参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| `deviceModel` | `DeviceModel` | 设备模型 |
| `attrs` | `List<DeviceAttributeModel>` | 属性列表（过滤非活跃属性） |

**输出消息格式**:
```json
{
  "header": {
    "ackCode": 1,
    "messageId": "12345",
    "name": "DeviceStatusUpdate",
    "screenMac": "AA:BB:CC:DD:EE:FF"
  },
  "payload": {
    "code": 200,
    "message": "",
    "data": {
      "deviceSn": 1234567890,
      "productCode": 1001,
      "items": [
        {
          "attrTag": "temperature",
          "attrValue": 25.5,
          "nonActiveUpload": false
        }
      ]
    }
  }
}
```

---

#### 2. 日志上传 (`MsgLogUpload`)

**接口定义**: `MqttApi.sendLogMsg(String str)`

**触发场景**: 应用日志上报

**输入参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| `str` | `String` | 日志内容 |

**输出消息格式**:
```json
{
  "header": {
    "ackCode": 1,
    "messageId": "12346",
    "name": "MsgLogUpload",
    "screenMac": "AA:BB:CC:DD:EE:FF"
  },
  "payload": {
    "code": 200,
    "message": "应用启动成功",
    "data": {
      "data": "应用启动成功"
    }
  }
}
```

---

#### 3. 场景状态更新 (`ScreenSceneSetUpload`)

**接口定义**: `MqttApi.sendSceneStatusMsg(long sceneId)`

**触发场景**: 场景执行完成后上报

**输入参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| `sceneId` | `long` | 场景ID |

**输出消息格式**:
```json
{
  "header": {
    "ackCode": 1,
    "messageId": "12347",
    "name": "ScreenSceneSetUpload",
    "screenMac": "AA:BB:CC:DD:EE:FF"
  },
  "payload": {
    "code": 200,
    "message": "",
    "data": {
      "sceneId": 1001
    }
  }
}
```

---

#### 4. 安防告警事件 (`FamilySecurityAlarmEvent`)

**接口定义**: `MqttApi.sendSecurityAlarmMsg(List<SecurityModel> list)`

**触发场景**: 安防设备触发告警

**输入参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| `list` | `List<SecurityModel>` | 告警列表 |

**输出消息格式**:
```json
{
  "header": {
    "ackCode": 1,
    "messageId": "12348",
    "name": "FamilySecurityAlarmEvent",
    "screenMac": "AA:BB:CC:DD:EE:FF"
  },
  "payload": {
    "code": 200,
    "message": "",
    "data": {
      "deviceSn": 0,
      "items": [
        {
          "alarmType": "motion",
          "alarmTime": 1620000000000,
          "deviceSn": 123456
        }
      ]
    }
  }
}
```

---

#### 5. HVAC功率上传 (`HVACPowerUpload`)

**接口定义**: `MqttApi.sendHvacPowerMsg(long deviceSn, int productCode, List<HvacPowerModel> list)`

**触发场景**: HVAC设备功率数据上报

**输入参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| `deviceSn` | `long` | 设备序列号 |
| `productCode` | `int` | 产品编码 |
| `list` | `List<HvacPowerModel>` | 功率数据列表 |

**输出消息格式**:
```json
{
  "header": {
    "ackCode": 1,
    "messageId": "12349",
    "name": "HVACPowerUpload",
    "screenMac": "AA:BB:CC:DD:EE:FF"
  },
  "payload": {
    "code": 200,
    "message": "",
    "data": {
      "deviceSn": 1234567890,
      "productCode": 2001,
      "items": [
        {
          "power": 1500.5,
          "time": 1620000000000
        }
      ]
    }
  }
}
```

---

#### 6. 操作事件上传 (`OprDevice`)

**接口定义**: `MqttApiImpl.sendUploadOptMsg()`

**触发场景**: 用户操作设备后记录操作日志

**输出消息格式**:
```json
{
  "header": {
    "ackCode": 1,
    "messageId": "12350",
    "name": "OprDevice",
    "screenMac": "AA:BB:CC:DD:EE:FF"
  },
  "payload": {
    "code": 200,
    "message": "",
    "data": {
      "deviceSn": 1234567890,
      "productCode": 1001,
      "items": [
        {
          "attrTag": "power",
          "attrValue": "on",
          "source": "click",
          "optTime": 1620000000000
        }
      ]
    }
  }
}
```

---

#### 7. 场景操作上传 (`OprScene`)

**接口定义**: `MqttApiImpl.sendUploadOptSceneMsg()`

**触发场景**: 场景操作记录

**输出消息格式**:
```json
{
  "header": {
    "ackCode": 1,
    "messageId": "12351",
    "name": "OprScene",
    "screenMac": "AA:BB:CC:DD:EE:FF"
  },
  "payload": {
    "code": 200,
    "message": "",
    "data": {
      "sceneId": 1001,
      "sceneNo": "SCENE_001",
      "updateType": "execute"
    }
  }
}
```

---

#### 8. 错误消息上传 (`FamilyErrMsg`)

**接口定义**: `MqttExecutor.uploadErrorMsg()`

**触发场景**: 设备通信错误上报

**输出消息格式**（使用`MqttNewBean`格式）:
```json
{
  "header": {
    "ackCode": 1,
    "messageId": "12352",
    "name": "FamilyErrMsg",
    "screenMac": "AA:BB:CC:DD:EE:FF"
  },
  "payload": {
    "code": 500,
    "message": "PLC通信超时",
    "data": {
      "errorCode": "1",
      "ifError": 1,
      "msg": "PLC通信超时",
      "time": 1620000000000
    }
  }
}
```

**错误码定义**:
| 错误码 | 类型 | 说明 |
|--------|------|------|
| 1 | PLC | PLC通信错误 |
| 2 | Rs485 | RS485通信错误 |
| 3 | Smart | 智能设备错误 |

---

## 四、消息订阅（Cloud → App）

### 4.1 订阅主题

| 主题 | 格式 | QoS |
|------|------|-----|
| `COMMON_CLOUD_2_SCREEN_TOPIC` | `/screen/service/cloud/to/screen/{mac}` | 0 |

### 4.2 接收消息类型详解

#### 1. 设备写操作 (`DeviceWrite`)

**作用**: 云端下发设备控制指令

**处理方法**: `MqttMsgHandler.handlerDeviceWriteMsg()`

**输入消息格式**:
```json
{
  "header": {
    "ackCode": 0,
    "messageId": "CMD_001",
    "name": "DeviceWrite",
    "screenMac": "AA:BB:CC:DD:EE:FF"
  },
  "payload": {
    "code": 200,
    "message": "",
    "data": {
      "deviceSn": 1234567890,
      "items": [
        {
          "attrTag": "power",
          "attrValue": "on"
        },
        {
          "attrTag": "temperature",
          "attrValue": 26.0
        }
      ]
    }
  }
}
```

**处理流程**:
1. 根据`deviceSn`查找设备
2. 构建`DeviceCtrlBean`控制对象
3. 调用`HardwareCtrlImpl.writeDeviceState()`执行写入

---

#### 2. 设备状态读取 (`DeviceStatusRead`)

**作用**: 云端主动请求设备状态

**处理方法**: `MqttMsgHandler.handlerDeviceReadMsg()`

**输入消息格式**:
```json
{
  "header": {
    "ackCode": 0,
    "messageId": "CMD_002",
    "name": "DeviceStatusRead",
    "screenMac": "AA:BB:CC:DD:EE:FF"
  },
  "payload": {
    "code": 200,
    "message": "",
    "data": {
      "deviceSn": 1234567890
    }
  }
}
```

**处理流程**:
1. 根据`deviceSn`查找设备
2. 调用`MqttApi.sendDeviceUpdateMsg()`回传设备状态

---

#### 3. 场景设置 (`FamilySceneSet`)

**作用**: 云端下发场景执行指令

**处理方法**: `MqttMsgHandler.handlerSceneSetMsg()`

**输入消息格式**:
```json
{
  "header": {
    "ackCode": 0,
    "messageId": "CMD_003",
    "name": "FamilySceneSet",
    "screenMac": "AA:BB:CC:DD:EE:FF"
  },
  "payload": {
    "code": 200,
    "message": "",
    "data": {
      "sceneId": 1001,
      "sceneNo": "SCENE_001",
      "conditionIds": [1, 2, 3]
    }
  }
}
```

**处理流程**:
1. 检查用户控制锁状态
2. 发送确认消息
3. 调用`SceneExeManager.executeSceneBySceneId()`执行场景

---

#### 4. 配置更新 (`FamilyConfigUpdate`)

**作用**: 云端推送配置更新通知

**处理方法**: `MqttMsgHandler.handlerConfigUpdateMsg()`

**输入消息格式**:
```json
{
  "header": {
    "ackCode": 0,
    "messageId": "CMD_004",
    "name": "FamilyConfigUpdate",
    "screenMac": "AA:BB:CC:DD:EE:FF"
  },
  "payload": {
    "code": 200,
    "message": "",
    "data": {
      "updateType": "FloorRoomDevice"
    }
  }
}
```

**更新类型映射**:

| updateType | 配置类型 | 触发操作 |
|------------|---------|---------|
| `FloorRoomDevice` | 楼层房间设备配置 | `getFloorDeviceList()` |
| `Scene` | 场景配置 | `getSceneList()` |
| `SceneTiming` | 定时场景配置 | `getSceneTimingList()` |
| `News` | 新闻配置 | `getNews()` |
| `ApkUpdate` | APK更新 | `apkUpdate()` |
| `HumidityConfigUpdate` | 湿度配置 | `projectHumidityUpdate()` |
| `ProjectCommonConfigUpdate` | 项目通用配置 | `projectCommonConfigUpdate()` |

---

#### 5. 屏幕通知 (`ScreenNotify`)

**作用**: 云端下发屏幕通知消息

**处理方法**: `MqttMsgHandler.handlerScreenNotify()`

**输入消息格式**:
```json
{
  "header": {
    "ackCode": 0,
    "messageId": "CMD_005",
    "name": "ScreenNotify",
    "screenMac": "AA:BB:CC:DD:EE:FF"
  },
  "payload": {
    "code": 200,
    "message": "",
    "data": {
      "notifyType": "NgrokConfig",
      "notifyMsg": "start"
    }
  }
}
```

**通知类型映射**:

| notifyType | 通知类型 | 触发操作 |
|------------|---------|---------|
| `NgrokConfig` | Ngrok配置 | 启动Ngrok隧道 |
| `ArkMode` | 方舟模式 | 设置节能模式 |

---

#### 6. 命令执行 (`Cmd`)

**作用**: 云端下发系统级命令

**处理方法**: `MqttMsgHandler.executeCmd()`

**输入消息格式**:
```json
{
  "header": {
    "ackCode": 0,
    "messageId": "CMD_006",
    "name": "Cmd",
    "screenMac": "AA:BB:CC:DD:EE:FF"
  },
  "payload": {
    "code": 200,
    "message": "",
    "data": {
      "data": "restart"
    }
  }
}
```

**命令类型**:

| 命令值 | 操作 |
|--------|------|
| `restart` | 重启应用 |
| `reboot` | 重启设备 |

---

#### 7. 日志上传控制 (`MsgLogUpload`)

**作用**: 云端控制日志上传

**处理方法**: `MqttMsgHandler.startUploadLog()`

**输入消息格式**:
```json
{
  "header": {
    "ackCode": 0,
    "messageId": "CMD_007",
    "name": "MsgLogUpload",
    "screenMac": "AA:BB:CC:DD:EE:FF"
  },
  "payload": {
    "code": 200,
    "message": "",
    "data": {
      "logKeepTime": 86400000
    }
  }
}
```

**字段说明**:
- `logKeepTime`: 日志保留时长（毫秒）

---

#### 8. HVAC功率响应 (`HVACPowerUpload`)

**作用**: 云端响应HVAC功率查询

**处理方法**: `MqttMsgHandler.handlerHvacPowerUpload()`

**输入消息格式**:
```json
{
  "header": {
    "ackCode": 0,
    "messageId": "CMD_008",
    "name": "HVACPowerUpload",
    "screenMac": "AA:BB:CC:DD:EE:FF"
  },
  "payload": {
    "code": 200,
    "message": "",
    "data": {
      "deviceSn": 1234567890,
      "items": [...]
    }
  }
}
```

---

#### 9. 安防告警 (`FamilySecurityAlarmEvent`)

**作用**: 云端下发安防告警配置

**处理方法**: `MqttMsgHandler.handleSecurityAlarmMsg()`

**输入消息格式**:
```json
{
  "header": {
    "ackCode": 0,
    "messageId": "CMD_009",
    "name": "FamilySecurityAlarmEvent",
    "screenMac": "AA:BB:CC:DD:EE:FF"
  },
  "payload": {
    "code": 200,
    "message": "",
    "data": {
      "items": [...]
    }
  }
}
```

---

#### 10. 场景设置上传响应 (`ScreenSceneSetUpload`)

**作用**: 云端响应场景设置上传

**处理方法**: `MqttMsgHandler.screenSceneSetUpload()`

**输入消息格式**:
```json
{
  "header": {
    "ackCode": 0,
    "messageId": "CMD_010",
    "name": "ScreenSceneSetUpload",
    "screenMac": "AA:BB:CC:DD:EE:FF"
  },
  "payload": {
    "code": 200,
    "message": "",
    "data": {}
  }
}
```

---

## 五、消息数据结构

### 5.1 消息体结构 (`MqttMsgBodyModel`)

```
MqttMsgBodyModel
├── header: MqttHeaderModel      // 消息头
│   ├── ackCode: int             // 是否需要回复 (0=需要, 1=不需要)
│   ├── messageId: String        // 消息ID（自增，最大65500）
│   ├── name: String             // 消息类型/方法名
│   └── screenMac: String        // 设备MAC地址
└── payload: MqttPayloadModel    // 消息载荷
    ├── code: int                // 状态码 (200=成功, 500=失败)
    ├── message: String          // 消息描述
    └── data: MqttDataModel      // 业务数据
        ├── deviceSn: Long       // 设备序列号
        ├── productCode: int     // 产品编码
        ├── items: List<T>       // 数据列表
        ├── sceneId: Long        // 场景ID
        ├── sceneNo: String      // 场景编号
        ├── conditionIds: List   // 条件ID列表
        ├── updateType: String   // 更新类型
        ├── logKeepTime: Long    // 日志保留时间
        ├── data: T              // 通用数据字段
        ├── notifyType: String   // 通知类型
        └── notifyMsg: String    // 通知消息
```

### 5.2 AckCode说明

| 值 | 含义 | 行为 |
|-----|------|------|
| 0 | 需要回复 | 收到消息后必须返回响应 |
| 1 | 无需回复 | 单向消息，不需要响应 |

---

## 六、消息处理流程图

```
云服务                    MQTT Broker                    自由方舟App
   │                           │                              │
   │                           │  [订阅]                       │
   │                           │  /screen/service/cloud/to/screen/{mac}
   │                           │◄─────────────────────────────│
   │                           │                              │
   │  [发布]                   │                              │
   │  /screen/service/cloud/to/screen/{mac}                   │
   │───────────────────────────►│                              │
   │                           │─────────────────────────────►│
   │                           │      messageArrived()        │
   │                           │                              │
   │                           │     根据header.name路由       │
   │                           │                              │
   │     [响应]                │                              │
   │◄──────────────────────────│◄─────────────────────────────│
   │  /screen/service/screen/to/cloud/{mac}                   │
   │                           │                              │
```

---

## 七、关键设计特点

### 7.1 消息ID机制

- **生成策略**: 原子自增，范围1-65500，达到上限后重置为1
- **作用**: 用于消息追踪和去重

### 7.2 重连机制

- 连接断开后自动重连（默认5秒间隔）
- 使用DisconnectedBufferOptions缓存离线消息（最多1024条）

### 7.3 忽略日志的消息类型

```java
private final String[] ignoreTopicList = new String[]{
    MqttConst.METHOD_HVAC_POWER_UPLOAD,  // HVAC功率上传
    MqttConst.METHOD_LOG_UPLOAD           // 日志上传
};
```

这两类消息量大，不记录日志以节省存储空间。

### 7.4 定时设备状态上报

每10分钟（600000ms）遍历所有设备，逐一上报状态（间隔100ms避免消息拥堵）。

---

## 八、总结

| 类别 | 数量 | 说明 |
|------|------|------|
| **发送消息类型** | 8种 | 设备状态、日志、场景、安防、HVAC、操作事件等 |
| **订阅消息类型** | 10种 | 设备控制、配置更新、场景执行、系统命令等 |
| **发送主题** | 4个 | 通用上行、数据更新、操作事件、日志 |
| **订阅主题** | 1个 | 云到屏消息（按MAC区分） |

自由方舟App的MQTT通信设计遵循以下原则：

1. **单向消息无需回复**：`ackCode=1`的消息为单向通知，减少网络往返
2. **设备唯一标识**：使用MAC地址作为ClientID和主题后缀，确保消息准确路由
3. **批量上报优化**：定时批量上报设备状态，降低网络频率
4. **缓存机制**：离线时缓存消息，重连后补发
5. **日志分级**：过滤高频消息的日志输出，避免日志膨胀
