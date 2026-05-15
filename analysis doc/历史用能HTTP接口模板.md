# 历史用能 HTTP 接口文档

## 1. 接口基本信息

| 项目 | 内容 |
|------|------|
| 接口名称 | 获取历史用能数据（账单列表） |
| 请求方法 | POST |
| 请求路径 | `ark/billing-managerment/list` |
| 接口版本 | v1 |
| 适用系统 | 自由方舟能源管理系统 |

## 2. 服务器地址

- **正式环境**: `http://47.117.41.184:10013/homeauto-contact-screen/contact-screen/screen/`
- **测试环境**: `http://47.117.47.6:10013/homeauto-contact-screen/contact-screen/screen/`

## 3. 请求头信息

```http
POST /ark/billing-managerment/list HTTP/1.1
Host: {base_url}
Content-Type: application/json; charset=utf-8
screenMac: {设备MAC地址}  # 必填，设备唯一标识
```

## 4. 请求参数

### 4.1 请求体 (JSON格式)

```json
{
  "startDate": "202301",
  "endDate": "202312"
}
```

### 4.2 参数说明

| 参数名 | 类型 | 必选 | 说明 |
|--------|------|------|------|
| startDate | String | 是 | 开始时间，格式：yyyyMM |
| endDate | String | 是 | 结束时间，格式：yyyyMM |

## 5. 响应格式

### 5.1 成功响应 (HTTP 200 OK)

```json
{
  "code": 200,
  "success": true,
  "message": "success",
  "data": [
    {
      "id": "bill_001",
      "billingCycle": "202301",
      "billingDate": "2023-02-01",
      "modeName": "标准模式",
      "usageAmount": "123.45",
      "basicAmount": "100.00",
      "basicPrice": "0.65",
      "beyondAmount": "23.45",
      "beyondPrice": "0.80",
      "billAmount": "80.24",
      "chargeItems": "电费",
      "familyId": "family_001",
      "familyName": "张三家",
      "realestateId": "realestate_001"
    },
    {
      "id": "bill_002",
      "billingCycle": "202302",
      "billingDate": "2023-03-01",
      "modeName": "标准模式",
      "usageAmount": "118.20",
      "basicAmount": "100.00",
      "basicPrice": "0.65",
      "beyondAmount": "18.20",
      "beyondPrice": "0.80",
      "billAmount": "76.83",
      "chargeItems": "电费",
      "familyId": "family_001",
      "familyName": "张三家",
      "realestateId": "realestate_001"
    }
  ]
}
```

### 5.2 错误响应

```json
{
  "code": 400,
  "success": false,
  "message": "参数错误：开始时间格式不正确",
  "data": null
}

{
  "code": 401,
  "success": false,
  "message": "未授权访问",
  "data": null
}

{
  "code": 500,
  "success": false,
  "message": "服务器内部错误",
  "data": null
}
```

## 6. 数据模型

### 6.1 请求数据模型 (GetBillRequestData)

```java
public final class GetBillRequestData {
    private final String startDate;
    private final String endDate;
    
    public GetBillRequestData(String startDate, String endDate) {
        this.startDate = startDate;
        this.endDate = endDate;
    }
}
```

### 6.2 响应数据模型 (BillBean)

```java
public final class BillBean {
    private final String id;
    private final String billingCycle;
    private final String billingDate;
    private final String modeName;
    private final String usageAmount;
    private final String basicAmount;
    private final String basicPrice;
    private final String beyondAmount;
    private final String beyondPrice;
    private final String billAmount;
    private final String chargeItems;
    private final String familyId;
    private final String familyName;
    private final String realestateId;
}
```

### 6.3 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | String | 账单ID |
| billingCycle | String | 计费周期，格式：yyyyMM |
| billingDate | String | 计费日期 |
| modeName | String | 供能模式名称 |
| usageAmount | String | 总使用量，单位：kWh |
| basicAmount | String | 基本用量 |
| basicPrice | String | 基本单价 |
| beyondAmount | String | 超出用量 |
| beyondPrice | String | 超出单价 |
| billAmount | String | 账单金额 |
| chargeItems | String | 收费项目 |
| familyId | String | 家庭ID |
| familyName | String | 家庭名称 |
| realestateId | String | 房产ID |

## 7. 调用示例

### 7.1 接口定义 (NetApi)

```java
import com.landleaf.sdk.bean.BillBean;
import com.landleaf.sdk.cloud.bean.GetBillRequestData;
import com.landleaf.sdk.cloud.net.http.bean.NetResponse;
import kotlinx.coroutines.flow.Flow;
import retrofit2.http.Body;
import retrofit2.http.Header;
import retrofit2.http.POST;

public interface NetApi {
    @POST("ark/billing-managerment/list")
    Flow<NetResponse<List<BillBean>>> getBillList(
            @Header("screenMac") String screenMac,
            @Body GetBillRequestData request
    );
}
```

### 7.2 调用实现 (HttpHelper)

```java
import com.landleaf.sdk.cloud.net.http.HttpHelper;
import com.landleaf.sdk.cloud.bean.GetBillRequestData;
import com.landleaf.sdk.cloud.net.http.bean.NetResponse;
import com.landleaf.sdk.bean.BillBean;
import kotlinx.coroutines.flow.Flow;

public class HttpHelper {
    public final Flow<NetResponse<List<BillBean>>> getBillList(String startDate, String endDate) {
        return ApiFactory.INSTANCE.getNetApi()
            .getBillList(mac, new GetBillRequestData(startDate, endDate));
    }
}
```

### 7.3 ViewModel 调用示例

```java
import com.landleaf.sdk.cloud.net.http.HttpHelper;
import com.landleaf.sdk.cloud.net.http.bean.NetResponse;
import com.landleaf.sdk.bean.BillBean;
import com.landleaf.sdk.utils.TimeUtils;
import kotlinx.coroutines.Dispatchers;
import kotlinx.coroutines.flow.collectLatest;
import kotlinx.coroutines.launch;

public class BillViewModel extends ViewModel {
    private final HttpHelper httpHelper = HttpHelper.INSTANCE.getInstance();
    private final String timeFormatForNet = "yyyyMM";

    public void getBillWithTime(long start, long end) {
        String paramStart = TimeUtils.millis2String(start, timeFormatForNet);
        String paramEnd = TimeUtils.millis2String(end, timeFormatForNet);
        
        launch(Dispatchers.IO) {
            httpHelper.getBillList(paramStart, paramEnd)
                .collectLatest { response ->
                    if (response.getCode() == 200) {
                        List<BillBean> billList = response.getData();
                        updateAdapter(billList);
                    } else {
                        handleError(response.getMessage());
                    }
                }
        };
    }
}
```

## 8. 调用流程

```
BillViewModel.getBillWithTime(long start, long end)
    → HttpHelper.getBillList(String startDate, String endDate)
        → NetApi.getBillList(@Header("screenMac") String screenMac, @Body GetBillRequestData request)
            → Retrofit + OkHttp 网络请求
                → POST {base_url}/ark/billing-managerment/list
                    → 服务器返回 NetResponse<List<BillBean>>
                        → Flow.collectLatest 处理响应
                            → 更新 UI
```

## 9. 数据字典

### 9.1 响应状态码 (code)

| 码值 | success | 说明 |
|------|---------|------|
| 200 | true | 请求成功 |
| 400 | false | 参数错误 |
| 401 | false | 未授权 |
| 403 | false | 禁止访问 |
| 404 | false | 接口不存在 |
| 500 | false | 服务器内部错误 |
| 503 | false | 服务不可用 |

## 10. 接口使用说明

1. **时间格式**: 所有时间参数均使用 `yyyyMM` 格式（如：202301 表示2023年1月）
2. **权限验证**: 需要在请求头中添加 `screenMac` 设备唯一标识
3. **数据范围**: 接口返回指定时间范围内的所有账单数据
4. **数据更新**: 历史用能数据通常为每日更新，实时性要求不高的场景可适当缓存

## 11. 性能优化建议

1. **请求频率**: 避免频繁请求，建议设置合理的缓存策略
2. **时间范围**: 单次请求的时间范围不宜过大，建议不超过12个月
3. **并发控制**: 合理控制并发请求数量，避免服务器压力过大

## 12. 安全注意事项

1. **参数校验**: 客户端和服务端都需要对请求参数进行严格校验
2. **数据加密**: 敏感数据（如认证信息）需要进行加密传输
3. **访问控制**: 根据设备权限控制数据访问范围
4. **防止SQL注入**: 服务端需要对请求参数进行过滤，防止SQL注入攻击
