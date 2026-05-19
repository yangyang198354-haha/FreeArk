<file_header>
  <author_agent>sub_agent_system_architect</author_agent>
  <timestamp>2026-05-20T00:00:00+08:00</timestamp>
  <project_name>FreeArk-DeviceSettings-v0.5.0</project_name>
  <version>0.1.0</version>
  <input_files>
    <file>docs/requirements/requirements_spec_v0.5.0_device_settings.md</file>
    <file>docs/architecture/tech_stack.md</file>
    <file>docs/architecture/architecture_design_v0.5.0_device_settings.md</file>
  </input_files>
  <phase>PHASE_03</phase>
  <status>DRAFT</status>
</file_header>

---

# 技术栈说明（v0.5.0 增量）

**文档编号**：ARCH-TECH-v0.5.0-device-settings  
**项目名称**：FreeArk 设备设置页面增量变更  
**版本**：v0.5.0  
**基线技术栈版本**：v0.3.0-APPROVED（`docs/architecture/tech_stack.md`）  
**日期**：2026-05-20  
**状态**：DRAFT

---

## 1. 技术栈变更声明

**v0.5.0 不引入任何新技术依赖。**

本次 4 项变更（CHG-01~04）均在 v0.4.7 已有技术栈范围内完成：

| 变更 | 所用技术 | 是否为新依赖 |
|------|---------|------------|
| CHG-01（is_active 数据修正） | Django ORM（已有）、management command（已有） | 否 |
| CHG-02（_mode 后缀扩展） | Python 内置字符串操作（已有）、frozenset（已有） | 否 |
| CHG-03（精确名白名单 + 标签映射） | Python dict/frozenset（已有） | 否 |
| CHG-04（dirtyFields 脏值追踪） | Vue 3 `ref`（已有）、JavaScript `Set`（浏览器内置） | 否 |

---

## 2. 基线技术栈继承（不变）

以下技术栈完全继承自 `tech_stack.md`（v0.3.0-APPROVED），无任何版本变更：

| 层次 | 技术 | 约束状态 |
|------|------|---------|
| 后端框架 | Django 5.2.x + DRF | 不变 |
| 后端 MQTT | paho-mqtt（已有） | 不变 |
| 前端框架 | Vue 3 + Element Plus | 不变 |
| 前端构建 | Vite ^6.0.1 | 不变 |
| 前端 MQTT | mqtt.js（v0.4.0 已引入） | 不变 |
| 部署 | git + plink + Waitress，物理机（树莓派） | 不变 |
| 数据库 | MySQL（生产）/ SQLite（测试） | 不变 |

---

## 3. 基础设施约束合规检查（v0.5.0）

| 约束条件 | 合规状态 |
|---------|---------|
| 不引入 Docker | 合规（无新依赖） |
| 无新 DB migration | 合规（无 schema 变更） |
| API 接口结构不变（REQ-NFUNC-003） | 合规（URL/HTTP 方法/schema 均不变） |
| `seed_device_config.py` 幂等性（REQ-NFUNC-004） | 合规（`update_or_create` 语义保证） |
