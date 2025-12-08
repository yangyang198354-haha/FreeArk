# API配置说明文档

## 1. 环境变量配置

### 1.1 环境变量名称

前端应用使用环境变量 `VITE_API_BASE_URL` 统一管理所有指向后端的API调用。

### 1.2 配置文件

项目中使用以下环境变量配置文件：

| 文件名 | 环境 | 说明 |
|--------|------|------|
| `.env` | 所有环境共享 | 基础配置，会被特定环境配置覆盖（当前项目未使用） |
| `.env.development` | 开发环境 | 开发环境特定配置 |
| `.env.production` | 生产环境 | 生产环境特定配置 |

### 1.3 配置方法

在对应环境的配置文件中添加以下配置：

```
VITE_API_BASE_URL=http://your-api-url.com
```

### 1.4 示例配置

#### 开发环境配置（.env.development）

```
# 开发环境API地址
VITE_API_BASE_URL=http://localhost:8000
```

#### 生产环境配置（.env.production）

```
# 生产环境API地址
VITE_API_BASE_URL=http://et116374mm892.vicp.fun
```

## 2. 生效机制

### 2.1 环境变量加载顺序

Vite会按照以下顺序加载环境变量配置文件：

1. `.env` - 所有环境共享配置（当前项目未使用）
2. `.env.[mode]` - 特定环境配置，会覆盖`.env`中的同名变量

### 2.2 不同环境的mode值

| 命令 | mode值 | 使用的配置文件 |
|------|--------|----------------|
| `npm run dev` | development | `.env` + `.env.development` |
| `npm run build` | production | `.env` + `.env.production` |
| `npm run preview` | production | `.env` + `.env.production` |

### 2.3 API请求机制

项目中提供两种API请求方式：

#### 2.3.1 直接使用axios默认配置

1. 在`main.js`中，`axios.defaults.baseURL`会被设置为`VITE_API_BASE_URL`环境变量的值
2. 所有直接使用axios发起的API请求都会自动添加该基础URL
3. 例如：
   - 配置：`VITE_API_BASE_URL=http://localhost:8000`
   - 请求：`axios.get('/api/users/')`
   - 实际请求URL：`http://localhost:8000/api/users/`

#### 2.3.2 使用封装的API服务（推荐）

1. 项目中创建了`src/services/api.js`文件，封装了所有API请求
2. 该文件创建了一个独立的axios实例，自动在基础URL后添加`/api`前缀
3. 例如：
   - 配置：`VITE_API_BASE_URL=http://localhost:8000`
   - 请求：`api.get('/users/')`
   - 实际请求URL：`http://localhost:8000/api/users/`

## 3. API服务封装（推荐使用）

### 3.1 api.js文件结构

`src/services/api.js`文件提供了以下功能：

- 创建了独立的axios实例
- 配置了请求拦截器（自动添加认证token）
- 配置了响应拦截器（处理认证错误）
- 封装了各种API函数

### 3.2 拦截器功能

#### 请求拦截器
- 自动从localStorage获取认证token
- 为所有API请求添加`Authorization`头

#### 响应拦截器
- 处理401认证错误
- 清除无效token并跳转到登录页面

### 3.3 封装的API模块

文件中封装了以下API模块：

1. **authApi** - 认证相关API
   - login: 用户登录
   - logout: 用户登出
   - getCurrentUser: 获取当前用户信息

2. **userApi** - 用户管理相关API
   - getUsers: 获取用户列表
   - getUser: 获取单个用户信息
   - createUser: 创建用户
   - updateUser: 更新用户
   - deleteUser: 删除用户

3. **usageApi** - 能耗报表相关API
   - getDailyUsage: 查询日用量报表
   - getMonthlyUsage: 查询月用量报表
   - getUsageQuery: 查询特定时间段用量数据

## 4. 错误处理

### 4.1 环境变量未配置

当`VITE_API_BASE_URL`环境变量未配置时，应用会：

1. 在控制台输出明确的错误提示
2. 使用默认值`http://localhost:8000`继续运行
3. 错误提示示例：
   ```
   错误：环境变量VITE_API_BASE_URL未配置！请在.env文件中配置该环境变量。
   示例配置：VITE_API_BASE_URL=http://localhost:8000
   应用将使用默认值http://localhost:8000继续运行
   ```

### 4.2 API请求失败

当API请求失败时，应用会：

1. 在控制台输出错误信息
2. 在页面上显示友好的错误提示
3. 不影响应用的其他功能

### 4.3 认证错误处理

当API请求返回401未认证错误时：

1. 自动清除localStorage中的token和用户信息
2. 自动跳转到登录页面

## 5. 代码示例

### 5.1 直接使用axios（不推荐）

```javascript
import axios from 'axios'

// 直接使用axios默认配置
axios.get('/api/users/')
  .then(response => {
    console.log(response.data)
  })
  .catch(error => {
    console.error('API请求失败：', error)
  })

// 直接使用axios默认配置发送POST请求
axios.post('/api/auth/login/', { username: 'admin', password: '123456' })
  .then(response => {
    console.log(response.data)
  })
  .catch(error => {
    console.error('登录失败：', error)
  })
```

### 5.2 使用封装的API服务（推荐）

```javascript
import { authApi, userApi, usageApi } from '@/services/api'

// 使用authApi登录
authApi.login({ username: 'admin', password: '123456' })
  .then(response => {
    console.log('登录成功:', response.data)
  })
  .catch(error => {
    console.error('登录失败:', error)
  })

// 使用userApi获取用户列表
userApi.getUsers({ page: 1, pageSize: 10 })
  .then(response => {
    console.log('用户列表:', response.data)
  })
  .catch(error => {
    console.error('获取用户列表失败:', error)
  })

// 使用usageApi获取日用量报表
usageApi.getDailyUsage({ date: '2023-10-01' })
  .then(response => {
    console.log('日用量报表:', response.data)
  })
  .catch(error => {
    console.error('获取日用量报表失败:', error)
  })
```

### 5.3 错误的API请求方式

```javascript
// 错误：硬编码API地址，没有使用环境变量
axios.get('http://localhost:8000/api/users/')
  .then(response => {
    console.log(response.data)
  })
  .catch(error => {
    console.error('API请求失败：', error)
  })
```

## 6. 开发和部署流程

### 6.1 开发流程

1. 在`.env.development`文件中配置开发环境API地址
2. 运行`npm run dev`启动开发服务器
3. 开发过程中，所有API请求都会使用配置的开发环境API地址

### 6.2 构建流程

1. 在`.env.production`文件中配置生产环境API地址
2. 运行`npm run build`构建生产版本
3. 构建后的应用会使用生产环境API地址

### 6.3 部署流程

1. 确保生产环境服务器上的环境变量配置正确
2. 将构建后的`dist`目录部署到服务器
3. 启动Web服务器，应用会自动使用配置的API地址

## 7. 常见问题及解决方法

### 7.1 API请求404错误

**问题**：API请求返回404错误

**可能原因**：
- 环境变量`VITE_API_BASE_URL`配置错误
- API路径错误
- 后端服务未启动

**解决方法**：
1. 检查环境变量配置是否正确
2. 检查API路径是否正确（注意使用封装API时不需要添加`/api`前缀）
3. 确保后端服务已启动
4. 在浏览器控制台查看实际请求URL

### 7.2 环境变量未生效

**问题**：修改环境变量后，API请求仍然使用旧的URL

**可能原因**：
- 开发服务器未重启
- 配置文件名称或路径错误
- 环境变量名称拼写错误

**解决方法**：
1. 重启开发服务器
2. 检查配置文件名称和路径
3. 检查环境变量名称拼写
4. 在浏览器控制台查看`API基础URL配置`输出

### 7.3 CORS错误

**问题**：API请求返回CORS错误

**可能原因**：
- 后端未配置CORS允许前端域名
- API地址配置错误

**解决方法**：
1. 检查后端CORS配置
2. 确保API地址配置正确
3. 检查前端域名是否在后端CORS允许列表中

### 7.4 认证失败（401错误）

**问题**：API请求返回401未认证错误

**可能原因**：
- 用户未登录或登录已过期
- token无效或已被清除

**解决方法**：
1. 检查用户是否已登录
2. 尝试重新登录获取新的token
3. 检查浏览器localStorage中的token是否存在

## 8. 最佳实践

1. **优先使用封装的API服务**：推荐使用`src/services/api.js`中封装的API函数，而不是直接使用axios
2. **统一使用环境变量**：所有API请求都使用环境变量配置的基础URL，不要硬编码API地址
3. **不同环境使用不同配置**：在对应环境的配置文件中配置相应的API地址
4. **定期检查配置**：定期检查环境变量配置，确保配置正确
5. **添加注释**：在配置文件中添加注释，说明配置的用途
6. **版本控制**：将配置文件纳入版本控制，便于团队协作

## 9. 联系方式

如果遇到配置问题，请联系前端开发团队。