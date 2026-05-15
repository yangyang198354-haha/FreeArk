# NetApi 服务接口分析文档

## 1. 基础信息

### 1.1 服务器地址
- **正式环境**: `http://47.117.41.184:10013/homeauto-contact-screen/contact-screen/screen/`
- **测试环境**: `http://47.117.47.6:10013/homeauto-contact-screen/contact-screen/screen/`

### 1.2 通用请求格式
- **HTTP方法**: 所有接口均使用 `POST` 方法
- **通用请求头**: 
  - `screenMac`: 设备屏幕MAC地址 (大多数接口需要)
- **请求体**: 大多数接口使用 `NetRequest<T>` 封装请求数据，格式为 `{"request": T}`
- **响应格式**: 统一使用 `NetResponse<T>` 格式，包含 `code`、`success`、`message` 和 `data` 字段

## 2. 接口详细信息

### 2.1 APK版本检查接口
- **方法名**: `apkUpdate`
- **API端点**: `apk-version/check`
- **完整URL**: `{base_url}/apk-version/check`
- **请求参数**:
  - **请求头**: `screenMac: String`
  - **请求体**: `NetRequest<String>`
- **响应**: `NetResponse<VersionBean>`
- **作用**: 检查APK版本更新

### 2.2 节假日检查接口
- **方法名**: `checkHoliday`
- **API端点**: `holidays/check`
- **完整URL**: `{base_url}/holidays/check`
- **请求参数**:
  - **请求头**: `screenMac: String`
  - **请求体**: `NetRequest<String>`
- **响应**: `NetResponse<CheckHolidayBean>`
- **作用**: 检查指定日期是否为节假日

### 2.3 删除定时场景接口
- **方法名**: `deleteTimingScene`
- **API端点**: `timing/scene/delete`
- **完整URL**: `{base_url}/timing/scene/delete`
- **请求参数**:
  - **请求头**: `screenMac: String`
  - **请求体**: `NetRequest<List<Integer>>`
- **响应**: `NetResponse<List<SceneTiming>>`
- **作用**: 删除指定的定时场景

### 2.4 家庭绑定接口
- **方法名**: `familyBind`
- **API端点**: `family/bind`
- **完整URL**: `{base_url}/family/bind`
- **请求参数**:
  - **请求头**: `screenMac: String`
  - **请求体**: `NetRequest<FamilyModel>`
- **响应**: `NetResponse<Object>`
- **作用**: 绑定家庭信息

### 2.5 账单列表查询接口
- **方法名**: `getBillList`
- **API端点**: `ark/billing-managerment/list`
- **完整URL**: `{base_url}/ark/billing-managerment/list`
- **请求参数**:
  - **请求头**: `screenMac: String`
  - **请求体**: `GetBillRequestData`
- **响应**: `NetResponse<List<BillBean>>`
- **作用**: 查询账单列表

### 2.6 城市天气查询接口
- **方法名**: `getCityWeather`
- **API端点**: `city/weather`
- **完整URL**: `{base_url}/city/weather`
- **请求参数**:
  - **请求体**: `NetRequest<String>` (city)
- **响应**: `NetResponse<WeatherBean>`
- **作用**: 查询指定城市的天气信息

#### 2.6.1 调用时机
1. **应用初始化阶段**: 在应用启动时，通过`HttpHelper.initRequest()`方法启动一系列异步请求，其中包括天气查询
2. **用户交互触发**: 当用户切换城市或手动刷新天气时，会调用`HttpHelper.getWeather(city)`方法触发天气查询
3. **定时更新**: 应用可能会设置定时任务，定期更新天气信息

#### 2.6.2 先决条件
1. **城市名参数**: 必须提供有效的城市名（不能为空）
2. **网络连接**: 设备必须处于联网状态
3. **NetApi实例初始化**: 需要通过`ApiFactory.getNetApi()`获取有效的NetApi实例
4. **设备MAC地址**: 虽然接口本身不需要MAC地址，但应用需要MAC地址进行其他初始化操作

#### 2.6.3 处理流程
1. **请求发起**: 通过`ApiFactory.getNetApi()`获取NetApi实例，创建`NetRequest`对象并设置城市名参数，调用`netApi.getCityWeather(request)`发起请求
2. **响应处理**: 使用`collectLatest`操作符处理返回的`Flow<NetResponse<WeatherBean>>`响应流
3. **结果分发**: 将获取到的天气信息通过`FlowBusCore`发送给订阅者
4. **UI更新**: `MainActivity`和`ArgraceMainFragment`监听天气信息变化，将结果更新到`ViewModel`中，供UI组件使用
5. **数据格式化**: 在`HttpHelper.detailWeather()`方法中对天气数据进行格式化处理（如格式化更新时间、设置天气提示等）

#### 2.6.4 实现代码示例
```java
// 获取NetApi实例
NetApi netApi = ApiFactory.INSTANCE.getNetApi();

// 创建请求参数
NetRequest<String> request = new NetRequest<>();
request.setRequest("北京");

// 发起请求
netApi.getCityWeather(request).collectLatest(new Function2<NetResponse<WeatherBean>, Continuation<? super Unit>, Object>() {
    @Override
    public Object invoke(NetResponse<WeatherBean> response, Continuation<? super Unit> continuation) {
        if (response.isSuccess()) {
            WeatherBean weatherBean = response.getData();
            // 处理天气数据
            detailWeather(weatherBean);
            // 发送结果到FlowBus
            FlowBusCore.INSTANCE.postEvent(weatherBean);
        } else {
            // 处理请求失败
            LandLeafLog.e("天气查询失败: " + response.getMessage());
        }
        return Unit.INSTANCE;
    }
});
```

### 2.7 项目配置查询接口
- **方法名**: `getCommonProjectConfig`
- **API端点**: `common/config`
- **完整URL**: `{base_url}/common/config`
- **请求参数**:
  - **请求头**: `screenMac: String`
- **响应**: `NetResponse<ProjectUpdateBean>`
- **作用**: 获取通用项目配置信息

### 2.8 能耗数据查询接口
- **方法名**: `getEnergyList`
- **API端点**: `ark/usage-amount`
- **完整URL**: `{base_url}/ark/usage-amount`
- **请求参数**:
  - **请求头**: `screenMac: String`
- **响应**: `NetResponse<EnergyBean>`
- **作用**: 查询能耗数据列表

### 2.9 楼层设备列表查询接口
- **方法名**: `getFloorDeviceList`
- **API端点**: `floor-room-device/list`
- **完整URL**: `{base_url}/floor-room-device/list`
- **请求参数**:
  - **请求头**: `screenMac: String`
- **响应**: `NetResponse<List<FloorModel>>`
- **作用**: 查询楼层和房间设备列表（用于MQTT CONFIG_FLOOR_ROOM_DEVICE指令）

### 2.10 湿度更新查询接口
- **方法名**: `getHumiUpdate`
- **API端点**: `humidity/config`
- **完整URL**: `{base_url}/humidity/config`
- **请求参数**:
  - **请求头**: `screenMac: String`
- **响应**: `NetResponse<HumidityUpdateBean>`
- **作用**: 获取湿度更新配置

### 2.11 新能耗图表数据接口
- **方法名**: `getNewEnergyList`
- **API端点**: `ark/usage-amount/chart`
- **完整URL**: `{base_url}/ark/usage-amount/chart`
- **请求参数**:
  - **请求头**: `screenMac: String`
- **响应**: `NetResponse<EnergyNewBean>`
- **作用**: 获取新格式的能耗图表数据

### 2.12 V3版本能耗数据接口
- **方法名**: `getNewEnergyListV3`
- **API端点**: `ark/usage-amount/new`
- **完整URL**: `{base_url}/ark/usage-amount/new`
- **请求参数**:
  - **请求头**: `screenMac: String`
- **响应**: `NetResponse<EnergyV3Bean>`
- **作用**: 获取V3版本的能耗数据

### 2.13 V4版本能耗数据接口
- **方法名**: `getNewEnergyListV4`
- **API端点**: `ark/usage-amount/plus`
- **完整URL**: `{base_url}/ark/usage-amount/plus`
- **请求参数**:
  - **请求头**: `screenMac: String`
- **响应**: `NetResponse<EnergyV4Bean>`
- **作用**: 获取V4版本的能耗数据

### 2.14 新闻列表查询接口
- **方法名**: `getNewsList`
- **API端点**: `news/list`
- **完整URL**: `{base_url}/news/list`
- **请求参数**:
  - **请求头**: `screenMac: String`
- **响应**: `NetResponse<List<NewsModel>>`
- **作用**: 查询新闻列表

### 2.15 场景列表查询接口（已废弃）
- **方法名**: `getSceneList`
- **API端点**: `scene/list`
- **完整URL**: `{base_url}/scene/list`
- **请求参数**:
  - **请求头**: `screenMac: String`
- **响应**: `NetResponse<List<SceneModel>>`
- **作用**: 查询场景列表（已废弃，建议使用getSceneListEx）

### 2.16 扩展场景列表查询接口
- **方法名**: `getSceneListEx`
- **API端点**: `scene/list/ex`
- **完整URL**: `{base_url}/scene/list/ex`
- **请求参数**:
  - **请求头**: `screenMac: String`
- **响应**: `NetResponse<List<SceneModelEx>>`
- **作用**: 查询扩展场景列表

### 2.17 定时场景查询接口
- **方法名**: `getTimingScene`
- **API端点**: `timing/scene/list`
- **完整URL**: `{base_url}/timing/scene/list`
- **请求参数**:
  - **请求头**: `screenMac: String`
- **响应**: `NetResponse<List<SceneTiming>>`
- **作用**: 查询定时场景列表

### 2.18 天气查询接口
- **方法名**: `getWeather`
- **API端点**: `weather` (使用SPTags.TAG_SP_WEATHER常量)
- **完整URL**: `{base_url}/weather`
- **请求参数**:
  - **请求头**: `screenMac: String`
- **响应**: `NetResponse<WeatherBean>`
- **作用**: 查询天气信息

### 2.19 重置家庭信息接口
- **方法名**: `resetFamilyInfo`
- **API端点**: `proprietor/clear`
- **完整URL**: `{base_url}/proprietor/clear`
- **请求参数**:
  - **请求头**: `screenMac: String`
- **响应**: `NetResponse<Object>`
- **作用**: 重置家庭信息

### 2.20 更新定时场景接口
- **方法名**: `updateTimingScene`
- **API端点**: `timing/scene/save-update`
- **完整URL**: `{base_url}/timing/scene/save-update`
- **请求参数**:
  - **请求头**: `screenMac: String`
  - **请求体**: `NetRequest<List<SceneTiming>>`
- **响应**: `NetResponse<List<SceneTiming>>`
- **作用**: 更新定时场景

### 2.21 错误上报接口
- **方法名**: `uploadError`
- **API端点**: `save-err-msg`
- **完整URL**: `{base_url}/save-err-msg`
- **请求参数**:
  - **请求头**: `screenMac: String`
  - **请求体**: `String` (错误信息)
- **响应**: `NetResponse<Object>`
- **作用**: 上报错误信息

## 3. 数据模型结构

### 3.1 通用请求包装类 (NetRequest)
```java
public final class NetRequest<T> {
    private T request;
    // getter和setter方法
}
```

### 3.2 通用响应包装类 (NetResponse)
```java
public class NetResponse<T> {
    private boolean isSuccess;
    private int code;
    private String message;
    private T data;
    // getter和setter方法
}
```

### 3.3 主要数据模型

#### 3.3.1 VersionBean (版本信息)
```java
public final class VersionBean {
    private String version;
    private String url;
    private boolean updateFlag;
    private int upgradeType;
    private String description;
    // getter和setter方法
}
```

#### 3.3.2 CheckHolidayBean (节假日检查结果)
```java
public final class CheckHolidayBean {
    private boolean result;
    // getter和setter方法
}
```

#### 3.3.3 SceneTiming (定时场景)
```java
public final class SceneTiming extends BaseObservable {
    private Long timingId;
    private String sceneName;
    private long sceneId;
    private int skipHoliday;
    private String weekday;
    private int type;
    private int enabled;
    private String startDate;
    private String endDate;
    private String executeTime;
    // getter和setter方法
}
```

## 4. 代码优化建议

1. **接口命名统一**：建议将API端点URL统一命名规范，例如所有接口都加上版本前缀（如"v1/"），以便未来版本升级。

2. **请求参数验证**：在发送请求前增加参数验证逻辑，避免无效参数导致的网络请求失败。

3. **错误处理增强**：为每个API接口添加更详细的错误处理和重试机制，特别是网络请求失败的情况。

4. **缓存策略实现**：对一些不经常变化的数据（如天气、新闻列表）实现本地缓存策略，减少网络请求次数。

5. **使用密封类处理响应**：考虑使用Kotlin密封类来处理不同类型的API响应，使代码更加安全和易读。

6. **分页加载实现**：对于列表类型的接口（如账单列表、新闻列表），建议实现分页加载功能，避免一次性加载过多数据。

7. **接口文档自动生成**：建议使用Swagger或其他API文档生成工具，自动生成和维护API文档，提高开发效率。

## 5. 总结

NetApi接口提供了一系列用于与服务器进行交互的方法，涵盖了版本检查、天气查询、能耗数据、场景管理、设备管理等多个功能模块。所有接口都遵循统一的请求和响应格式，便于维护和扩展。

通过对这些接口的分析，我们可以看到应用的整体架构和数据流向，为后续的功能开发和性能优化提供了基础。