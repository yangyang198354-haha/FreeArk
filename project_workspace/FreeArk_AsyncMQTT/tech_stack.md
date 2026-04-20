# Tech Stack — FreeArk AsyncMQTT Fix
<!-- file_header: author_agent=sub_agent_system_architect, status=APPROVED, version=1.0 -->

## 核心技术栈（不变）

| 层 | 技术 | 版本 |
|----|------|------|
| 语言 | Python | 3.13 |
| Web 框架 | Django | 5.2 |
| MQTT 客户端 | paho-mqtt | 最新稳定版 |
| 数据库驱动 | MySQLdb | 最新稳定版 |
| 数据库 | MySQL | 生产: 192.168.31.98:3306 |

## 新增标准库依赖（无外部包）

| 模块 | 用途 |
|------|------|
| `queue.Queue` | 有界内部消息队列 |
| `threading.Thread` | Worker 线程 |
| `threading.Event` | 停止信号 |

注：`close_old_connections` 已在原文件导入，无需新增 import。

## 部署环境

| 环境 | 详情 |
|------|------|
| 生产服务器 | 树莓派, IP=192.168.31.51 |
| 操作系统 | Linux (ARM) |
| 服务管理 | systemd, 单元: freeark-mqtt-consumer |
| 部署方式 | plink SSH 推送文件 + 远程 systemctl restart |

## 配置参数（mqtt_config.json，不变）

```json
{
  "host": "192.168.31.98",
  "port": 32788,
  "keepalive": 120,
  "qos": 0
}
```
