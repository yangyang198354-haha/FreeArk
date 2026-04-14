# FreeArkWeb 技术栈

<!-- file_header
author_agent: sub_agent_system_architect
phase: PHASE_04
project: FreeArkWeb
created_at: 2026-04-14
status: DRAFT
source: reverse_engineering — freearkweb/settings.py, api/ imports
-->

---

## 1. 技术栈清单

| 层次 | 技术 | 版本 | 用途 |
|------|------|------|------|
| Web 框架 | Django | 5.2.7 | HTTP 处理、ORM、Admin |
| REST API | Django REST Framework | latest | 序列化器、视图集、权限 |
| 认证 | DRF Token Authentication | built-in | Token 管理 |
| 跨域 | django-corsheaders | latest | CORS 支持 |
| 消息队列 | MQTT (paho-mqtt) | latest | PLC 数据采集 |
| 测试数据库 | SQLite3 | built-in | 单元/集成测试 |
| 生产数据库 | MySQL 8.x | 8.x | 生产数据存储（192.168.31.98:3306） |
| 语言 | Python | 3.x | 全栈 |
| 运行平台 | 树莓派 (物理机) | - | 192.168.31.51 |

## 2. 基础设施约束（硬性规则）

- **禁止 Docker**：全环境物理机直接部署
- **测试数据库**：仅使用 SQLite（Django TestCase 自动隔离），严禁连接 192.168.31.98:3306
- **时区**：Asia/Shanghai，USE_TZ=False
- **认证**：TokenAuthentication + SessionAuthentication

## 3. 测试运行命令

```bash
cd C:\Users\yanggyan\MyProject\FreeArk\FreeArkWeb\backend\freearkweb
python manage.py test api
```
