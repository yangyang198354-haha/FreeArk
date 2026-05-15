# GetBillRequestData 发送流程分析

## 1. 数据发送机制概述

`GetBillRequestData` 是作为 **请求体(Body)** 数据发送给 `ark/billing-managerment/list` 接口的，而不是作为请求头(Header)数据。整个发送流程基于 Retrofit 网络框架实现。

## 2. 完整发送流程

### 2.1 调用链分析

```
BillViewModel.getBillWithTime()
    → HttpHelper.getBillList(String startDate, String endDate)
        → NetApi.getBillList(@Header("screenMac") String screenMac, @Body GetBillRequestData request)
            → Retrofit + OkHttp 网络请求
                → POST /ark/billing-managerment/list
```

### 2.2 关键代码解析

#### 2.2.1 BillViewModel 触发请求

```java
// 调用 HttpHelper 获取历史用能数据
httpHelper.getBillList(paramStart, paramEnd)
    .collectLatest {
        // 处理响应数据
    }
```

#### 2.2.2 HttpHelper 构造请求

```java
public final Flow<NetResponse<List<BillBean>>> getBillList(String startDate, String endDate) {
    // 参数校验
    Intrinsics.checkNotNullParameter(startDate, "startDate");
    Intrinsics.checkNotNullParameter(endDate, "endDate");
    
    // 创建 GetBillRequestData 对象并发送请求
    return ApiFactory.INSTANCE.getNetApi().getBillList(
        mac,  // Header 中的 screenMac
        new GetBillRequestData(startDate, endDate)  // Body 中的请求参数
    );
}
```

#### 2.2.3 NetApi 接口定义

```java
@POST("ark/billing-managerment/list")
Flow<NetResponse<List<BillBean>>> getBillList(
    @Header("screenMac") String screenMac,  // Header 参数
    @Body GetBillRequestData request  // Body 参数
);
```

**关键注解说明：**
- `@POST("ark/billing-managerment/list")`：指定请求方法为 POST，路径为 `ark/billing-managerment/list`
- `@Header("screenMac")`：将设备 MAC 地址作为请求头字段发送
- `@Body`：将 `GetBillRequestData` 对象作为请求体发送

### 2.3 GetBillRequestData 数据结构

```java
public final class GetBillRequestData {
    private final String startDate;  // 开始时间，格式：yyyyMM
    private final String endDate;    // 结束时间，格式：yyyyMM

    // 构造函数
    public GetBillRequestData(String startDate, String endDate) {
        this.startDate = startDate;
        this.endDate = endDate;
    }

    // Getter 方法
    public final String getStartDate() { return startDate; }
    public final String getEndDate() { return endDate; }
}
```

## 3. 网络请求配置

### 3.1 Retrofit 配置

`ApiFactory` 类负责创建和配置 Retrofit 实例：

```java
public final class ApiFactory {
    private static volatile NetApi netApi;
    
    static {
        // 初始化 Retrofit
        Retrofit retrofit = new Retrofit.Builder()
            .baseUrl(BASE_URL)
            .client(okHttpClient)
            .addConverterFactory(GsonConverterFactory.create())
            .addCallAdapterFactory(FlowCallAdapterFactory.create())
            .build();
        
        // 创建 NetApi 实例
        netApi = retrofit.create(NetApi.class);
    }
    
    public final NetApi getNetApi() {
        return netApi;
    }
}
```

### 3.2 请求转换过程

1. **对象转换**：Retrofit 使用 GsonConverterFactory 将 `GetBillRequestData` 对象转换为 JSON 格式
2. **请求构建**：OkHttpClient 构建完整的 HTTP 请求，包含请求头和请求体
3. **数据发送**：发送请求到服务器 `ark/billing-managerment/list` 接口
4. **响应处理**：接收服务器响应，转换为 `NetResponse<List<BillBean>>` 对象

## 4. 实际发送的 HTTP 请求示例

```http
POST /ark/billing-managerment/list HTTP/1.1
Host: {服务器地址}
Content-Type: application/json; charset=UTF-8
Accept: application/json
Accept-Language: zh-CN
User-Agent: LandLeaf/1.0.0 (Android)
screenMac: 00:11:22:33:44:55  # Header 数据

{"startDate":"202301","endDate":"202312"}  # Body 数据 (GetBillRequestData 转换后的 JSON)
```

## 5. 总结

`GetBillRequestData` 是通过以下方式发送给 `bill-managerment/list` 接口的：

1. **数据类型**：作为请求体(Body)数据发送，不是请求头(Header)数据
2. **传输格式**：通过 Retrofit 自动转换为 JSON 格式
3. **请求方法**：使用 POST 请求方法
4. **关键配置**：
   - 使用 `@Body` 注解标记请求体参数
   - 使用 `@Header("screenMac")` 单独发送设备 MAC 地址
5. **技术框架**：基于 Retrofit + OkHttp 实现网络请求

这种实现方式符合 RESTful API 设计规范，将业务参数放在请求体中，将设备标识等元数据放在请求头中，使请求结构更加清晰合理。