# 技术栈说明

**版本**：v0.5.9-heartbeat-broker-config  
**日期**：2026-05-23  
**状态**：DRAFT — 待用户 CONFIRM  
**作者**：SDLC System Architect (sub_agent_system_architect)

---

## 1. 核心技术栈（继承，不新增）

| 层次 | 技术 | 版本 | 说明 |
|------|------|------|------|
| 后端框架 | Django | 5.2 | 现有，不变 |
| 后端 API | Django REST Framework | 3.x | 现有，不变 |
| MQTT 客户端 | paho-mqtt | >= 1.6.1 | **已有依赖，本次扩展使用 wss transport** |
| 数据库 | MySQL 8 | - | 现有，heartbeat 配置不走 DB |
| 前端框架 | Vue 3 (Composition API) | 3.x | 现有，不变 |
| 前端 UI | Element Plus | 2.x | 现有，不变 |
| 部署 | systemd + Waitress + Nginx | - | 现有，不变 |
| 操作系统 | Raspberry Pi OS (Linux) | - | 生产环境 |

---

## 2. MQTT 客户端库选型分析：paho-mqtt wss 能力确认

### 2.1 paho-mqtt wss 支持版本历史

| paho 版本 | wss 支持状态 |
|-----------|-------------|
| < 1.4 | 不支持 websockets transport |
| >= 1.4 | 支持 `Client(transport="websockets")`，`ws_set_options(path=...)` |
| >= 1.6.1 | 稳定版，当前 requirements.txt 下限 |
| 2.0.0 | 引入 `CallbackAPIVersion`；旧式回调仍可用但需显式指定版本（向后兼容期） |
| 2.1.x | 主流稳定 2.x 版本 |

**结论**：`paho-mqtt >= 1.6.1` 完全支持 wss transport，无需引入其他库。

### 2.2 paho wss 初始化方式（版本适配）

**paho 1.x（当前生产可能版本）**：

```python
import paho.mqtt.client as mqtt

client = mqtt.Client(client_id='freeark-screen-heartbeat', transport='websockets')
client.tls_set()          # 使用系统 CA bundle（PEM），验证服务端证书
client.ws_set_options(path='/mqtt')
client.username_pw_set('admin', 'public')
client.connect('www.ttqingjiao.site', 8084, keepalive=60)
client.loop_forever(retry_first_connection=True)
```

**paho 2.x（若升级后）**：

```python
import paho.mqtt.client as mqtt

# paho 2.x 推荐显式指定 CallbackAPIVersion，避免 DeprecationWarning
client = mqtt.Client(
    callback_api_version=mqtt.CallbackAPIVersion.VERSION1,  # 兼容旧式回调签名
    client_id='freeark-screen-heartbeat',
    transport='websockets',
)
client.tls_set()
client.ws_set_options(path='/mqtt')
client.username_pw_set('admin', 'public')
client.connect('www.ttqingjiao.site', 8084, keepalive=60)
client.loop_forever(retry_first_connection=True)
```

**兼容写法（同时兼容 1.x 和 2.x）**：

```python
import paho.mqtt.client as mqtt

kwargs = {'client_id': client_id, 'transport': transport}
try:
    # paho 2.x：尝试使用 CallbackAPIVersion
    kwargs['callback_api_version'] = mqtt.CallbackAPIVersion.VERSION1
    client = mqtt.Client(**kwargs)
except AttributeError:
    # paho 1.x：无此参数，回退
    del kwargs['callback_api_version']
    client = mqtt.Client(**kwargs)
```

**推荐**：开发时检查生产 paho 版本（见 OQ-001），根据实际版本选择单一写法；若版本确定为 1.x，不引入 `CallbackAPIVersion` 代码，减少复杂度。

### 2.3 TLS 配置说明

`client.tls_set()` 无参数时使用 Python `ssl` 模块的系统默认 CA bundle：

- 树莓派 Raspberry Pi OS：`/etc/ssl/certs/ca-certificates.crt`（已含 Let's Encrypt、DigiCert 等主流 CA）。
- 若 `www.ttqingjiao.site:8084` 使用 Let's Encrypt 证书，`tls_set()` 无参数即可成功验证。
- 若为自签证书，需 `client.tls_set(ca_certs='/path/to/ca.crt')`，同时在配置文件中增加 `ca_certs` 字段（OQ-002 待确认）。

### 2.4 为何不选择其他库

| 库 | 排除原因 |
|----|---------|
| gmqtt | async 库，需 asyncio event loop；当前 consumer 是同步 management command，改造成本高 |
| aiomqtt | 同上，async 依赖 |
| mqtt.js（Node） | 后端为 Python，不适用 |
| mosquitto C client | 无 Python 绑定，不适用 |

---

## 3. 配置文件格式

使用 JSON（与现有 `mqtt_config.json` 一致）：

- 原生 Python `json` 模块处理，无额外依赖。
- 人类可读，运维人员可直接 vim 编辑。
- Django 进程读写权限与 systemd 服务权限均为 yangyang 用户，无权限冲突。

---

## 4. 部署依赖确认清单

| 确认项 | 检查命令 | 期望结果 |
|--------|---------|---------|
| paho 实际版本 | `pip show paho-mqtt` | >= 1.6.1 |
| wss broker CA 类型 | 浏览器访问 https://www.ttqingjiao.site 或 `openssl s_client -connect www.ttqingjiao.site:8084` | 受信任 CA（Let's Encrypt 等） |
| sudoers 白名单含 heartbeat | `sudo -l -U yangyang \| grep freeark-screen-heartbeat` | 有匹配条目 |
| Python ssl 模块 CA bundle | `python3 -c "import ssl; print(ssl.get_default_verify_paths())"` | cafile 路径存在 |

---

## 5. 开放技术问题（对应需求 OQ-001/002）

### OQ-001：生产 paho 版本

**影响**：决定是否需要引入 `CallbackAPIVersion` 兼容代码。

**解决方案**：
- 在生产服务器执行 `pip show paho-mqtt`（或 `/home/yangyang/Freeark/FreeArk/venv/bin/pip show paho-mqtt`）。
- 若版本 < 2.0：直接使用 1.x API，无需兼容代码。
- 若版本 >= 2.0：使用 `CallbackAPIVersion.VERSION1` 显式指定，或将 requirements.txt 固定为 `paho-mqtt>=1.6.1,<2.0`（推荐后者，保持确定性）。

**推荐**：无论实际版本，建议在 requirements.txt 明确固定 `paho-mqtt>=1.6.1,<2.0`，避免 pip 自动升级到 2.x 引入 DeprecationWarning 甚至 API 不兼容。

### OQ-002：wss broker TLS 证书类型

**影响**：决定 `tls_set()` 是否需要 `ca_certs` 参数。

**解决方案**：
- 用浏览器或 `curl` 访问确认证书类型：`curl -v https://www.ttqingjiao.site:8084` 看 issuer。
- Let's Encrypt 或其他主流 CA：`client.tls_set()` 无参数即可。
- 自签：需要 `client.tls_set(ca_certs='/path/to/ca.crt')`，配置文件增加 `ca_certs` 字段，部署时需上传 CA 证书到服务器。

---

*文档状态：DRAFT。请用户确认后进入开发阶段。*
