# MQTT CONFIG_FLOOR_ROOM_DEVICE 指令分析

## 1. 指令概述

`CONFIG_FLOOR_ROOM_DEVICE` 是自由方舟应用中定义的一个MQTT指令常量，用于触发设备楼层房间信息的同步更新。

```java
public static final String CONFIG_FLOOR_ROOM_DEVICE = "FloorRoomDevice";
```

**定义位置**：`com.landleaf.sdk.cloud.net.mqtt.MqttConst.java` 第17行

## 2. 指令作用

当MQTT服务器向设备发送包含 `CONFIG_FLOOR_ROOM_DEVICE` 指令的消息时，设备会执行以下操作：

1. 触发设备楼层设备列表的同步获取
2. 从云端服务器获取最新的楼层和房间设备信息
3. 更新本地缓存的设备楼层房间数据
4. 确保设备显示的楼层房间信息与云端保持一致

## 3. MQTT消息处理流程

### 3.1 消息接收

MQTT消息通过 `MqttMsgHandler` 类进行处理。当接收到包含 `updateType` 为 `CONFIG_FLOOR_ROOM_DEVICE` 的消息时，会触发相应的处理逻辑：

```java
if (updateType.equals(MqttConst.CONFIG_FLOOR_ROOM_DEVICE)) {
    HardwareCtrlImpl.INSTANCE.getINSTANCE().getFloorDeviceList();
    break;
}
```

**处理位置**：`com.landleaf.sdk.cloud.net.mqtt.MqttMsgHandler.java` 第251行

### 3.2 硬件控制层处理

`HardwareCtrlImpl` 是硬件控制的实现类，它的 `getFloorDeviceList()` 方法会调用网络层获取楼层设备列表：

```java
public void getFloorDeviceList() {
    // 调用网络层获取楼层设备列表
    HttpHelper.getInstance().getFloorDeviceList();
}
```

### 3.3 网络层数据获取

`HttpHelper` 类的 `getFloorDeviceList()` 方法通过 Retrofit API 从云端服务器获取最新的楼层设备数据：

```java
public final Object getFloorDeviceList(Continuation<? super Unit> continuation) {
    Object objCollectLatest = FlowKt.collectLatest(
        FlowKt.m3466catch(
            ApiFactory.INSTANCE.getNetApi().getFloorDeviceList(mac), 
            new C20832(null)
        ), 
        new C20843(null), 
        continuation
    );
    // ...
}
```

**API接口**：`NetApi` 接口中的 `getFloorDeviceList` 方法，使用 POST 请求获取数据

```java
Flow<NetResponse<List<FloorModel>>> getFloorDeviceList(@Header("screenMac") String screenMac);
```

### 3.3.1 服务器地址配置

`getFloorDeviceList` 请求的服务器地址由 `HttpConsts` 类配置：

```java
public final String getBaseUrl() {
    return "http://" + HTTP_SERVER_HOST + ":10013/homeauto-contact-screen/contact-screen/screen/";
}
```

**服务器IP配置**：
- 正式环境：`47.117.41.184`
- 测试环境：`47.117.47.6`

**完整请求URL**：
- 正式环境：`http://47.117.41.184:10013/homeauto-contact-screen/contact-screen/screen/floor-device-list`
- 测试环境：`http://47.117.47.6:10013/homeauto-contact-screen/contact-screen/screen/floor-device-list`

### 3.3.2 请求结构

```http
POST /homeauto-contact-screen/contact-screen/screen/floor-device-list HTTP/1.1
Host: 47.117.41.184:10013
Content-Type: application/json
Accept: application/json
screenMac: 设备的MAC地址

{}
```

**请求参数说明**：
- `screenMac`：设备的MAC地址，作为HTTP请求头传递
- 请求体：空JSON对象 `{}`

### 3.3.3 返回结构

**响应格式**：

```json
{
  "code": 200,
  "success": true,
  "message": "请求成功",
  "data": [
    {
      "id": 1,
      "floorName": "1楼",
      "floor": 1,
      "rooms": [
        {
          "id": 101,
          "roomName": "会议室",
          "devices": [
            {
              "deviceSn": "device_001",
              "deviceName": "空调",
              "deviceType": "hvac"
              // ... 其他设备属性
            }
            // ... 更多设备
          ]
          // ... 其他房间属性
        }
        // ... 更多房间
      ]
    }
    // ... 更多楼层
  ]
}
```

**响应字段说明**：
- `code`：响应状态码，200表示成功
- `success`：布尔值，表示请求是否成功
- `message`：响应消息描述
- `data`：楼层设备列表数据

## 4. 数据模型

### 4.1 NetResponse 响应模型

所有HTTP请求的统一响应格式：

```java
public class NetResponse<T> {
    private int code;
    private boolean isSuccess;
    private String message;
    private T data;
    
    // Getters and setters
}
```

### 4.2 FloorModel 楼层模型

该指令获取的数据使用 `FloorModel` 类表示，包含楼层和房间设备信息：

```java
public class FloorModel {
    private long id;           // 楼层ID
    private String floorName;  // 楼层名称
    private int floor;         // 楼层号
    private List<RoomModel> rooms;  // 房间列表
    
    // Getters and setters
}
```

### 4.3 RoomModel 房间模型

房间信息的数据模型（FloorModel的rooms字段）：

```java
public class RoomModel {
    private long id;           // 房间ID
    private String roomName;   // 房间名称
    private List<DeviceModel> devices;  // 设备列表
    
    // Getters and setters
}
```

### 4.4 DeviceModel 设备模型

设备信息的数据模型（RoomModel的devices字段）：

```java
public class DeviceModel {
    private String deviceSn;   // 设备序列号
    private String deviceName; // 设备名称
    private String deviceType; // 设备类型
    // ... 其他设备属性
    
    // Getters and setters
}

### 4.2 响应格式（已移至3.3.3节）

> 注意：详细的响应格式和字段说明已移至3.3.3节 "返回结构" 部分

## 5. 使用场景

`CONFIG_FLOOR_ROOM_DEVICE` 指令主要用于以下场景：

1. **设备初始化**：设备首次启动或重置后，获取完整的楼层房间设备信息
2. **配置更新**：当云端楼层房间配置发生变化时，及时同步到设备
3. **手动同步**：管理员在云端修改配置后，主动触发设备同步
4. **故障恢复**：设备楼层信息异常时，通过该指令重新获取正确数据

## 6. 指令使用方法

### 6.1 MQTT订阅主题格式

设备需要订阅以下格式的MQTT主题，以接收来自云端的配置更新消息：

**订阅主题格式**：`/screen/service/cloud/to/screen/{设备MAC}`

**参数说明**：
| 参数名 | 类型 | 说明 |
|--------|------|------|
| {设备MAC} | String | 设备的唯一MAC地址，用于标识具体的屏幕设备 |

**订阅实现代码**：
```java
mqttAsyncClient.subscribe(
    MqttConst.COMMON_CLOUD_2_SCREEN_TOPIC + mac, 
    MqttConst.COMMON_QOS, 
    null, 
    new IMqttActionListener() {
        @Override
        public void onSuccess(IMqttToken asyncActionToken) {
            // 订阅成功回调
        }
        
        @Override
        public void onFailure(IMqttToken asyncActionToken, Throwable exception) {
            // 订阅失败回调
        }
    }
);
```

### 6.2 服务器发送MQTT消息

服务器需要向设备发送以下格式的MQTT消息：

**主题**：`/screen/service/cloud/to/screen/{设备MAC}`

**消息体**：

```json
{
  "method": "FamilyConfigUpdate",
  "updateType": "FloorRoomDevice",
  "data": {}
}
```

### 6.3 消息参数说明

| 参数名 | 类型 | 说明 |
|--------|------|------|
| method | String | 固定为 "FamilyConfigUpdate" |
| updateType | String | 固定为 "FloorRoomDevice" |
| data | Object | 附加数据（可选，当前版本未使用） |

### 6.4 完整订阅消息格式模板

**订阅主题**：`/screen/service/cloud/to/screen/{设备MAC}`

**完整消息结构**：
```json
{
  "method": "FamilyConfigUpdate",
  "updateType": "FloorRoomDevice",
  "data": {}
}
```

**字段详解**：
- **method**：消息方法名，标识消息类型，此处固定为`FamilyConfigUpdate`
- **updateType**：更新类型，标识具体的配置更新，此处固定为`FloorRoomDevice`
- **data**：附加数据对象，当前版本未使用，为空对象`{}`

**消息接收处理流程**：
1. 设备通过MQTT客户端订阅主题`/screen/service/cloud/to/screen/{设备MAC}`
2. 云端服务器向该主题发布包含`CONFIG_FLOOR_ROOM_DEVICE`指令的消息
3. 设备MQTT客户端收到消息后，解析`updateType`字段
4. 当`updateType`为`FloorRoomDevice`时，触发楼层设备列表同步逻辑
5. 调用`HardwareCtrlImpl.INSTANCE.getINSTANCE().getFloorDeviceList()`获取最新数据
6. 更新本地缓存并刷新显示界面

## 7. 代码优化建议

### 7.1 增加错误处理机制

当前实现中缺少完整的错误处理机制，建议在获取楼层设备列表失败时增加重试逻辑和错误日志记录：

```java
public final Object getFloorDeviceList(Continuation<? super Unit> continuation) {
    Object objCollectLatest = FlowKt.collectLatest(
        FlowKt.m3466catch(
            ApiFactory.INSTANCE.getNetApi().getFloorDeviceList(mac), 
            e -> {
                LandLeafLog.e("获取楼层设备列表失败: " + e.getMessage());
                // 增加重试逻辑
                delay(5000);
                return ApiFactory.INSTANCE.getNetApi().getFloorDeviceList(mac);
            }
        ), 
        new C20843(null), 
        continuation
    );
    // ...
}
```

### 7.2 添加数据版本控制

建议在数据模型中添加版本号字段，避免不必要的全量更新：

```java
public class FloorModel {
    private String floorId;
    private String floorName;
    private int version; // 增加版本号字段
    // ... 其他字段
}
```

### 7.3 优化数据同步策略

当前实现是全量同步，可以考虑实现增量同步机制，只更新发生变化的楼层房间信息，减少网络开销和数据处理时间。

## 8. 总结

`CONFIG_FLOOR_ROOM_DEVICE` 是自由方舟应用中用于同步设备楼层房间信息的重要MQTT指令。通过该指令，设备可以及时获取云端最新的楼层房间配置，确保显示的信息与云端保持一致。

该指令的处理流程清晰，从MQTT消息接收、硬件控制层处理到网络层数据获取，形成了完整的处理链路。在实际使用中，服务器可以通过发送包含该指令的MQTT消息，主动触发设备的楼层房间信息同步。

通过适当的优化，可以进一步提高该指令的可靠性和性能，为用户提供更好的使用体验。