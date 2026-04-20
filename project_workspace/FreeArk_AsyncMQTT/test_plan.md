# Test Plan — FreeArk AsyncMQTT Fix
<!-- file_header: author_agent=sub_agent_test_engineer, status=APPROVED, version=1.0 -->

## 测试策略

本次测试在 Windows 开发机本地执行（无 EMQX、无 MySQL），通过 mock 隔离外部依赖。

## 测试范围

| 用户故事 | 测试类型 | 覆盖方法 |
|---------|---------|---------|
| US-001: on_message 零阻塞 | 单元测试 | mock queue.put_nowait，验证无 DB 调用 |
| US-002: worker 消费消息 | 单元测试 | 直接调用 _worker_loop，验证 _dispatch 被调用 |
| US-003: 队列满丢弃 | 单元测试 | 塞满队列后验证 WARNING 日志 |
| US-004: 优雅关闭 | 单元测试 | mock stop_event，验证 task_done 调用 |

## 测试文件

`project_workspace/FreeArk_AsyncMQTT/test_mqtt_consumer_async.py`

## 执行环境

- Python 3.13（Windows 开发机）
- unittest + unittest.mock（标准库，无外部依赖）
- 通过 DJANGO_SETTINGS_MODULE mock 规避 Django 初始化
