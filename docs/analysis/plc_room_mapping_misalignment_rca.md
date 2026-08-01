# 根因分析报告：设备面板房间温控开关状态错位（"主卧"显示开启，实际"书房"开启）

| 项 | 值 |
| --- | --- |
| 报告类型 | Root Cause Analysis（PARTIAL_FLOW：需求澄清 + 根因调查/分析，不含代码修复） |
| 状态 | DRAFT，待人工确认（含需查生产库的开放问题） |
| 缺陷样本 | 住户 `3-1-7-702`（成都乐府·二仙桥 3栋1单元7楼702，PLC IP `192.168.3.27`） |
| 现象 | Web 端设备面板显示"主卧-温控面板"为"开启"，现场实际开启的是"书房-温控面板" |
| 调查方式 | 仅只读代码/配置阅读 + `git grep` 全仓核验，未连接生产库、未修改任何文件 |
| 编写人 | PM Orchestrator（含子代理调查 + 人工逐条复核） |

---

## 0. 一句话结论

温控面板的"值"和"房间中文标签"走的是**两条互不核对身份的独立链路**：值由全局唯一、按 `param_name` 字符串键控的 PLC 点位表（`plc_config.json`）决定；标签由另一张**与住户户型/真实房间无关、全局硬编码为固定"四房"含义**的静态表（`seed_device_config.py` → `DeviceConfig.sub_type_display`）决定；而系统里唯一知道"该住户真实有哪些房间"的权威数据源（`DeviceRoom`/`DeviceNode`，来自屏幕厂商云端接口）**只用于决定某类面板是否显示，从未参与决定该面板该叫什么名字、该读哪个 PLC 偏移量**。用户"整体错位一位（数组下标偏移）"这一具体机制在现有 Python 代码中**未找到实现证据、可视为证伪**；但用户"房间被系统性地贴错标签"这一**表现**是真实存在的架构缺陷，根因是**静态全局标签表 + 无户型/接线约定记录机制**，而非数组压缩。样本 `3-1-702` 的云端房间树显示"书房+次卧+主卧+儿童房"四个独立面板，形态上符合软件所假设的"四房"惯例，因此该户标签在软件逻辑内部是自洽的——若此户仍然发生错位，最可能的触发点是**现场 PLC 组态（电气接线）与软件假设的"四房"点位含义不一致**，这一点无法仅凭仓库代码坐实，需要生产库/现场组态资料佐证（见第 6 节开放问题）。

---

## 1. 完整数据链路

设备面板显示内容由两条独立链路合成：**链路 A（数值）** 与 **链路 B（房间标签）**，另有 **链路 C（真实房间树，仅用于面板可见性判定，不参与 A/B）**。

### 链路 A — PLC 数值（决定面板显示"开启/关闭"这个值）

```
PLC S7 硬件 DB14（固定偏移量，全楼盘/全户型共用同一份点位模板）
  │ snap7 读取
  ▼
datacollection/multi_thread_plc_handler.py:115-150  read_db_data()
  —— 按 (db_num, offset, length, data_type) 读取，读取动作本身不携带任何"房间/户型"概念
  │
  ▼
datacollection/task_scheduler.py:219  _run_group_task() → collect_data_for_building(...)
  —— 生产在跑路径，由 systemd 服务 freeark-task-scheduler 驱动
  │
  ▼
datacollection/improved_data_collection_manager.py:154  load_plc_config()
  —— 加载唯一一份全局 plc_config.json（仓库根目录），89 个 param_name 对全楼盘统一生效，
     不区分三房/四房，也不区分具体住户
  │
  ▼
datacollection/improved_data_collection_manager.py:337-362  collect_data_for_building()
  —— 对 resource/3#_data.json 里的每一户（如 "3-1-7-702"），逐 param_name 用同一份 plc_config 生成读取任务
  │
  ▼
datacollection/improved_data_collection_manager.py:553-596  _organize_results()
  —— 按 param_name（字符串）组织到 organized_results[device_id]['data'][param_name]
  │ MQTT publish
  ▼
FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py:724 起  PLCLatestDataHandler.handle()
  —— for param_name, param_data in data_dict.items(): ...
  —— models.py:335-350  PLCLatestData 表 update_or_create，落库键 = (specific_part, param_name)
  │
  ▼
FreeArkWeb/backend/freearkweb/api/views_device_settings.py:212-215  device_settings_params()
  —— latest_map = {r.param_name: r.value for r in PLCLatestData.objects.filter(specific_part=specific_part)}
  —— views_device_settings.py:252  raw_val = latest_map.get(cfg.param_name)   ← 面板上"开启/关闭"这个值
```

**证据（值的身份传递方式）**：`FreeArkWeb/backend/freearkweb/api/models.py:335-346` `PLCLatestData` 表结构中，房间身份仅体现为 `specific_part`（住户）+ `param_name`（参数名字符串），没有任何数组下标或房间外键字段。

### 链路 B — 房间标签（决定面板抬头显示"主卧-温控面板"还是"书房-温控面板"）

```
FreeArkWeb/backend/freearkweb/api/management/commands/seed_device_config.py:24-747
  —— HVAC_PARAM_CONFIGS：硬编码列表，一次性 seed 进 DeviceConfig 表
  —— 关键映射（param_name → sub_type → sub_type_display，全部为静态常量）：
       study_room_switch      → sub_type=panel_study_room      → sub_type_display='书房-温控面板'  （第131行起）
       bedroom_switch         → sub_type=panel_bedroom         → sub_type_display='次卧-温控面板'  （第221行起）
       children_room_switch   → sub_type=panel_children_room   → sub_type_display='主卧-温控面板'  （第311行起）
       fourth_children_room_switch → sub_type=panel_fourth_children → sub_type_display='儿童房-温控面板'（第401行起）
  │
  ▼
FreeArkWeb/backend/freearkweb/api/views_device_settings.py:243-248
  —— groups[key] = {'sub_type': cfg.sub_type, 'sub_type_display': cfg.sub_type_display, 'params': []}
  —— sub_type_display 从 DeviceConfig 表原样取出，直接透传给前端做面板抬头，不做任何按户重算
```

**关键证据（`DeviceConfig` 无户型/住户维度）**：`FreeArkWeb/backend/freearkweb/api/models.py:392-397`
```python
class Meta:
    db_table = 'device_config'
    ...
    unique_together = [['param_name', 'sub_type']]
```
`DeviceConfig` 唯一约束只有 `(param_name, sub_type)`，**不含 `specific_part`**——这意味着 `sub_type_display` 这张"标签"在数据模型层面就是**全局单值**，物理上不可能对不同住户显示不同的房间名。

### 链路 C — 真实房间树（旁路：只决定"面板要不要显示"，不决定"显示什么/读哪个偏移量"）

```
屏幕厂商云端 API（第三方"自由方舟"品牌温控屏，非本仓库自有系统）
  POST http://47.117.41.184:10013/homeauto-contact-screen/contact-screen/screen/floor-room-device/list
  │
  ▼
FreeArkWeb/backend/freearkweb/api/device_tree_sync.py:78  call_remote_floor_room_device_list()
  ▼
device_tree_sync.py:219-231  upsert_tree()
  —— DeviceRoom.objects.update_or_create(..., ori_room_name=room['oriRoomName'], room_type=room['roomType'])
  —— models.py:486-509  DeviceRoom（逐户真实房间名，如样本 3-1-702 的"书房"/"次卧"/"主卧"/"儿童房"）
  —— models.py:512-537  DeviceNode（真实设备，device_sn 唯一，如样本中 22552/22553/22554/22555）
  │
  ▼
FreeArkWeb/backend/freearkweb/api/utils_room_filter.py:39-44, 235-279  _match_panel_sub_types()
  —— 仅用 DeviceRoom.ori_room_name 关键词匹配，决定 panel_* 这个 sub_type "是否可用/是否显示/是否落库"
  —— **不决定该 sub_type 的中文标签内容，也不决定该 sub_type 读取的是哪个 PLC 偏移量**
```

链路 C 中 `DeviceNode.device_sn` 才是屏厂云端逐户区分"哪个物理面板是书房、哪个是主卧"的真身份字段，但**链路 A / B 完全不读取这张表的房间-设备对应关系**，只用它做布尔可见性判定。

---

## 2. 房间映射的实际实现方式：按字符串标识（非数组下标），但标识含义是全局静态写死的

- **不是按下标**：`datacollection/`、`FreeArkWeb/backend/` 全部相关代码里，房间参数均以 `param_name` 字符串为 dict key（`plc_config.json` 的 `"parameters"` 是 dict；`PLCLatestData` 唯一键是 `(specific_part, param_name)`；`DeviceConfig` 唯一键是 `(param_name, sub_type)`）。未发现任何"房间列表[i]"式按位置取值的路径。
- **是按标识，但标识含义全局唯一、不因户而异**：
  - PLC 侧：`param_name` → 全局固定的 `(db_num=14, offset)`，对所有住户一视同仁。
  - 显示侧：`sub_type` → 全局固定的中文标签 `sub_type_display`（无 `specific_part` 维度，见上节 `unique_together` 证据）。
  - 真实房间身份（`DeviceRoom.ori_room_name` / `DeviceNode.device_sn`）存在，但只参与"是否显示"，从不参与"重新核对/纠正标签是否与该户实际房间相符"。

**决定性证据——点位表自身文档说明了"同一偏移量在三房/四房代表不同房间"这一事实（`plc_config.json`）：**

| param_name | offset | description（原文） |
| --- | --- | --- |
| `children_room_switch` | 1395 | "三房儿童房四房主卧开关" |
| `bedroom_switch` | 1455 | "三房主卧四房次卧开关" |
| `study_room_switch` | 1515 | "三房次卧四房书房开关" |
| `fourth_children_room_switch` | 1575 | "四房儿童房开关"（四房专属） |

而 `seed_device_config.py` 给这四个 `param_name` 钉死的中文标签**永远**取"四房"释义（`children_room_switch`→"主卧"、`bedroom_switch`→"次卧"、`study_room_switch`→"书房"），**不会**因为该户是三房还是四房切换成"三房"释义（"儿童房"/"主卧"/"次卧"）。

**`utils_room_filter.py:22-37` 的模块注释已经准确记录了这个"一个 PLC 点位、两种户型两种含义"的事实**，但这段认知只被用来算"面板要不要出现"，没有被用来决定"面板该叫什么名字"——这是**文档认知与代码实现之间的断层**，也是本次缺陷的架构级根因。

**旁证——小程序端已经意识到这个"反直觉"映射并特意加了警示注释**（`FreeArkWeb/backend/freearkweb/api/views_miniapp_device_settings.py:70-80`）：
```python
# 小程序端温控面板 sub_type → 纯房间名（不含"-温控面板"后缀）
# ⚠ 注意：panel_bedroom → 次卧（非主卧），panel_children_room → 主卧（非儿童房）
#   此反直觉映射已由业务方最终确认（REQ-FUNC-002 关键陷阱，v1.11.2 2026-06-28）
PANEL_DISPLAY_MAP: dict[str, str] = {
    'panel_study_room':      '书房',
    'panel_bedroom':         '次卧',   # ⚠ 非"主卧"
    'panel_children_room':   '主卧',   # ⚠ 非"儿童房"
    'panel_fourth_children': '儿童房',
}
```
这段注释证实：团队在 v1.11.2（2026-06-28）已经内部确认过 `sub_type` 变量名与其显示房间名之间的映射关系"反直觉、容易搞混"，但当时只是把 Web 端 `seed_device_config.py` 的同一张静态映射照抄了一份（去掉后缀）给小程序用，**没有触及"这张映射对不对得上具体某一户的真实房间"这个更深层问题**——Web 端和小程序端目前对同一 `sub_type` 显示的是同一套（可能同样错误的）房间名，是一致的重复，不是分歧的根源。

---

## 3. 空槽位 / 户型差异的处理逻辑：证据显示是"整条丢弃"，不是"数组压缩前移"

**(a) S7 读取失败**（`datacollection/multi_thread_plc_handler.py:115-150` `read_db_data()`）：读取失败返回 `(False, message, None)`，该参数在结果字典里仍然存在（`success=False, value=None`），不会被移除，也不影响其他参数的 `db_num/offset`（因为每个参数的地址始终从 `plc_config.json` 按 key 查出，不依赖数组位置）。

**(b) Web 后端入库时——读取失败**（`FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py:791-795`）：
```python
if not param_data.get('success', False):
    skipped_failed += 1
    ...
    continue
```
失败参数整条 `continue` 跳过，不写入 `PLCLatestData`（前端表现为"无数据/采集中"，不会被其他值顶替）。

**(c) 户型过滤跳过**（`mqtt_handlers.py:774-781`，依赖 `utils_room_filter.get_panel_param_blocklist()`）：
```python
if param_blocklist and param_name in param_blocklist:
    skipped_room_filter += 1
    ...
    continue
```
同样是整条跳过、不落库，不是把值挪给别的房间。

**结论**：无论是"户型缺槽位"还是"S7 读取失败"，代码里体现的都是 **dict key 缺失（跳过整条记录）**，不是**list 下标压缩导致后续元素整体前移**。用户假设的"数组整体错位一位"这一具体实现机制，在现有 `datacollection/` 与 `FreeArkWeb/backend/` 代码中**没有找到任何实现证据，可视为该字面机制被证伪**。真正的错位风险点在**配置数据本身的静态假设**（见第 2 节），而非运行时的数组操作。

---

## 4. 三房/四房户型在现有设计中的处理缺口

- **数据库没有"户型"字段**：`OwnerInfo`（`models.py:296-` 起）只有楼栋/单元/楼层/户号/IP/PLC IP 等字段，无 `house_type`/户型/房间数字段。`resource/3#_data.json` 中 `3-1-7-702` 记录（第145-155行）同样不含户型字段。
- **户型只能靠关键词"猜"，且历史上已经踩过坑**：`utils_room_filter.py:243-259` 的函数文档记录了一次真实生产事故——
  > "原判断「含儿童房 AND 房间数 >= 4」…生产数据中三房户型（9-1-10-1002）房间总数为 5（含全屋/客厅等非卧室），全部误触发…根据生产全量 40 个专有部分扫描：「含书房 = 四房」，100% 吻合，无例外。核心判定规则改为「含书房 AND 含儿童房」"
  
  这证实"房间数量"这一启发式已被验证不可靠，当前用"是否含书房"这一关键词做二元判断，**仍然只是一个基于房间名字符串的启发式，不是权威户型字段**，且历史上已发生过一次误判并修复（v0.5.7-fix2）。
- **`seed_device_config.py` 是唯一的"标签硬编码"证据源**，其 89 条 `HVAC_PARAM_CONFIGS` 记录中，四个房间面板 sub_type 的 `sub_type_display` 全部固定为单一房间名，**没有任何按户型切换标签的机制**，也没有 `--house-type` 等参数（`seed_device_config.py:5-7` 用法说明中仅有 `seed_device_config` 和 `--reset` 两种调用方式）。
- **`--reset` 机制本身也不支持精细化修复**：`get_or_create`（默认路径）不更新已存在记录；`--reset` 会先删全部记录再重建，但重建后的标签仍是全局单值（因为 `DeviceConfig` 模型没有 `specific_part` 字段），**这意味着当前数据模型从根本上不支持"同一 `sub_type` 在不同户显示不同房间名"**，任何显示文案层面的修复都无法仅靠改 seed 数据完成，需要模型层扩展（见第 5 节修复方案）。

---

## 5. 样本 3-1-702 分析

**`git grep -n "3-1-702\|3-1-7-702"` 全仓核验（按 CLAUDE.md 第6条要求，非仅 ripgrep）**，命中 100+ 处，关键证据：

- `resource/3#_data.json:145-155`：确认 `3-1-7-702` 是本仓库 `datacollection` 侧真实在采的一户，PLC IP=`192.168.3.27`。
- `FreeArkWeb/backend/freearkweb/api/fault_consumer/constants.py:244`：注释明确写着"基于生产 device_list API 分析（3-1-702 楼层设备清单）"——证实 3-1-702 是团队做故障管理模块时使用的真实生产样本。
- `docs/analysis/heartbeat_3-1-702_capture_report.md`：存在与该住户相关的其他分析产物（心跳抓包），说明 3-1-702 是团队长期用作调试/分析的标杆样本户。
- `analysis doc/设备树同步功能_需求与用户故事.md` 存在，证实 `analysis doc/` 目录（含 3-1-702 抓包分析）是 `device_tree_sync.py` 功能模块的直接需求来源材料。

**"自由方舟" analysis doc 与本次调查的关系判断**：`analysis doc/房间信息初始化机制分析文档.md` 分析的是"自由方舟"品牌温控屏 Android 客户端反编译代码，其调用的云端接口地址与 `device_tree_sync.py` 中的 `REMOTE_BASE_URL`/`REMOTE_PATH` 完全一致——**不是无关的第三方系统，而是 `DeviceRoom`/`DeviceNode` 表（链路 C）的直接数据来源**。团队通过反编译屏厂 App、抓包分析该接口，在 Web 后端复刻了服务端 upsert 逻辑，用于房型过滤（`utils_room_filter.py`）和故障事件房间归属（`fault_consumer/room_lookup.py`）。但正如第 1 节所述，**链路 C 与决定面板数值/标签的链路 A/B 是两套完全独立、互不查验的数据源**，这种架构分裂本身就是本次 bug 的结构性根因。

**3-1-702 真实房间树核验**（读取 `analysis doc/3-1-702_response_raw.json`）：

```
floor=1
  客厅   (roomType=2, sn=22158, 主温控)
  书房   (roomType=6, sn=22552, 温控面板)
  次卧   (roomType=5, sn=22553, 温控面板)
  主卧   (roomType=4, sn=22554, 温控面板)
  儿童房 (roomType=5, sn=22555, 温控面板)
```

3-1-702 **同时拥有"书房"和"儿童房"两个独立房间**，用 `_match_panel_sub_types()`（`utils_room_filter.py:235-279`）的判定规则代入：
- `has_study_room = True`（含"书房"），`has_children_keyword = True`（含"儿童房"）→ `panel_fourth_children` 命中
- `主卧` 关键词命中 → `panel_bedroom`、`panel_children_room` 同时命中
- `次卧`/`书房` 关键词命中 → `panel_study_room` 命中

即：**该户四个温控面板 sub_type 全部判定为可用**，形态上完全符合软件所假设的"标准四房"模板（`seed_device_config.py` 的固定标签本来就是按"四房"释义写死的：`children_room_switch`→主卧、`bedroom_switch`→次卧、`study_room_switch`→书房、`fourth_children_room_switch`→儿童房）。

**这意味着一个重要的推论**：对于像 3-1-702 这样房间树完整匹配"四房"模式的住户，**软件内部逻辑是自洽的**——如果现场 PLC 组态确实按"四房"惯例接线（即物理上把"书房"面板接到 `study_room_switch` 对应的 DB14 偏移量 1515，把"主卧"面板接到 `children_room_switch` 对应的偏移量 1395），标签应该是准确的。**因此该户若发生"主卧显示开、书房实际开"的错位，最可能的原因是现场电气接线并未严格遵循"四房"惯例**（例如安装时把"书房"面板接上了原本按"三房"惯例预留给"儿童房"/"主卧"的偏移量，或安装工程师参照的是三房模板接线单但云端房间树因后期改造/命名调整变成了四房形态），**这一点无法仅凭本仓库代码坐实**，仓库内既没有 PLC 梯形图/组态原始文档，也没有该户在故障发生时刻的 `PLCLatestData` 实时快照。

### 5.1 PM 复核补充：云端房间顺序与 PLC 槽位顺序存在「1↔3 对调」（2026-08-01）

PM 亲自复核（CLAUDE.md 第 4 条）时，把 `plc_config.json` 的四个 `*_switch` 点位按偏移量升序排列，与 3-1-702 云端房间树按 `deviceSn` 升序排列做对照，发现两者**不是同一个顺序**：

| 槽位 | DB 偏移量 | plc_config `description` | param_name | 系统标签（seed） | 云端同序位房间（按 deviceSn） |
|---|---|---|---|---|---|
| 1 | 1395 | 三房儿童房**四房主卧** | `children_room_switch` | 主卧-温控面板 | **书房**（sn 22552） |
| 2 | 1455 | 三房主卧**四房次卧** | `bedroom_switch` | 次卧-温控面板 | 次卧（sn 22553） |
| 3 | 1515 | 三房次卧**四房书房** | `study_room_switch` | 书房-温控面板 | **主卧**（sn 22554） |
| 4 | 1575 | 四房儿童房 | `fourth_children_room_switch` | 儿童房-温控面板 | 儿童房（sn 22555） |

偏移量步长恒为 60，四个槽位是一个标准的定长数组结构。槽位 2、4 两套顺序一致，**槽位 1 与槽位 3 恰好互换**。

**由此得到一个比第 5 节更强的假设（假设 B）**：现场 PLC 组态是按**云端/屏厂房间顺序**（书房→次卧→主卧→儿童房，即 deviceSn 递增序）接线的，而不是按 `plc_config.json` 的"四房"惯例（主卧→次卧→书房→儿童房）。若成立，则偏移量 1395 物理上就是**书房**，而系统按 `seed_device_config.py` 固定标签把它显示为**主卧** —— 这与用户报告的"UI 主卧显示开启、实际书房开启"**逐字吻合**。

假设 B 相比第 5 节的泛化推测有两个优势：它解释了为什么错位发生在 3-1-702 这样一个"标准四房"住户上（第 5 节的自洽性推论无法解释这一点），并且给出一个**无需现场、无需生产库即可证伪的对称预测**：

> **验证动作**：在 Web 端把 UI 显示为「**书房**-温控面板」的开关置为开启，到现场（或让物业确认）观察响应的是否是**主卧**面板。
> - 若主卧响应 → 假设 B 成立，1↔3 对调坐实，可直接进入修复。
> - 若书房响应 → 假设 B 证伪，退回第 5 节的"接线未遵循任一惯例"路径，必须索取现场组态文档。

需要说明的是，"deviceSn 递增序 = 现场接线序"这一步本身仍是推断（deviceSn 由屏厂云端分配，本仓库无文档证明它与 PLC 槽位分配存在因果关系），因此假设 B 属于**高置信度待验证假设**，而非已坐实结论。上面的对称验证动作就是为了用最低成本把它证实或证伪。

**另需注意（与假设 B 独立的第二个缺陷）**：`utils_room_filter._match_panel_sub_types()`（`utils_room_filter.py:235-279`）的关键词规则**正确建模了三房/四房双重语义**（`panel_study_room` ← 含"次卧"**或**"书房"；`panel_children_room` ← 含"儿童房"**或**"主卧"），但 `seed_device_config.py` 与 `PANEL_DISPLAY_MAP` 的标签**只写死了四房分支**。二者语义不对称的直接后果是：**任何真·三房住户，其三个面板的标签会全部贴错**（槽位 1 物理是儿童房却显示"主卧"、槽位 2 物理是主卧却显示"次卧"、槽位 3 物理是次卧却显示"书房"）。这正是用户假设的"整体错位一位"——机制不是数组压缩，而是**四房专用标签表被套用到三房住户**。3-1-702 是四房，不受此缺陷影响，但生产环境中的三房住户（如 `utils_room_filter.py:252` 提到的 9-1-10-1002）**当前极可能全部处于错位显示状态**，属于本次调查外溢发现的独立高危问题，建议一并纳入修复范围。

**待验证假设与所需生产数据（只读 SQL，不在本次任务内执行）**：

1. 核对云端权威房间数据当前状态：
   ```sql
   SELECT r.ori_room_name, r.room_type, n.device_sn, n.product_code
   FROM device_room r
   JOIN device_node n ON n.room_id = r.id
   JOIN device_floor f ON r.floor_id = f.id
   WHERE f.specific_part = '3-1-7-702';   -- 具体外键字段名以 device_tree_sync.py 实际实现为准，需先核对 DeviceFloor 模型
   ```
2. 核对故障发生前后该户四个面板参数的实际取值，判断是否存在"一个开一个关"被同时/交替呈现的现象：
   ```sql
   SELECT param_name, value, collected_at
   FROM plc_latest_data
   WHERE specific_part = '3-1-7-702'
     AND param_name IN ('study_room_switch','bedroom_switch','children_room_switch','fourth_children_room_switch')
   ORDER BY collected_at DESC
   LIMIT 20;
   ```
3. 向物业/安装方索取 3-1-702（PLC IP `192.168.3.27`）现场 PLC 点位组态原始文档，核对 DB14 偏移量 1395/1455/1515/1575 各自实际接线对应的物理房间——这是唯一能 100% 坐实/推翻本报告核心假设的证据源，不在本仓库范围内。

---

## 6. 修复方案建议（仅方案，不实施）

### 方案一：数据模型扩展 —— 引入按住户/户型维度的标签绑定（推荐，根治架构分裂）

- 在 `DeviceConfig` 之外新增一张"住户级面板房间绑定表"（如 `DeviceRoomBinding`：`specific_part` + `sub_type` → `room_display_name`），或直接扩展 `DeviceRoom`/`DeviceNode`（链路 C 已有的权威房间树），让 `param_name`/`sub_type` 与 `DeviceNode.device_sn` 建立**逐户显式绑定**，而不是全局共享 `sub_type_display`。
- 设备面板取标签时，优先查该住户的绑定表；查不到则回退到 `DeviceConfig.sub_type_display` 全局默认值（保证向后兼容、无绑定数据的老户型不受影响）。
- **影响面**：需要新增 model + 迁移（遵守 CLAUDE.md 第1条，手写 scoped 迁移）；`views_device_settings.py`、`views_miniapp_device_settings.py` 的取标签逻辑需要改造；`device_tree_sync.py` 的 upsert 流程需要顺带建立/更新绑定关系（可能需要人工审核步骤，因为"哪个 device_sn 对应哪个 param_name/PLC 偏移量"这一映射，云端接口本身不知道，需要现场组态资料或一次性人工核对录入）。
- **权衡**：一次性投入较大（需要现场资料配合逐户建立绑定），但从根本上解决"全局标签 vs 逐户真实房间"的architecture 分裂问题，且为未来支持五房、复式等更多户型留出扩展空间。

### 方案二：户型标记 + 双模板标签 —— 轻量修复（快，但不覆盖非标准户型）

- 在 `OwnerInfo` 新增 `house_type` 字段（三房/四房/其他，人工或按 `utils_room_filter._match_panel_sub_types()` 的启发式规则一次性回填）。
- `seed_device_config.py` 改为按 `house_type` 生成两套 `sub_type_display`（三房释义 vs 四房释义），`DeviceConfig` 增加 `house_type` 维度到唯一约束（`unique_together = [['param_name', 'sub_type', 'house_type']]`），取标签时按该住户的 `house_type` 选择对应记录。
- **影响面**：`DeviceConfig` 表结构变更（迁移）；`seed_device_config.py` 需要重写为按户型分组生成；取标签逻辑（`views_device_settings.py:243-248`）需要加入 `house_type` 过滤条件。
- **权衡**：改动范围比方案一小，能覆盖"标准三房"和"标准四房"两种明确户型，**但无法覆盖 3-1-702 这类"书房+次卧+主卧+儿童房都有"的非标准/超配户型**（因为这类户型不属于三房或四房任一简单二元分类，且其错位根因很可能出在现场接线而非软件标签本身），对这类户型仍需退化到方案一或人工核对。此外该方案仍未解决"软件假设的四房/三房接线惯例是否与现场真实接线一致"这一根本性未知——它只是把当前隐含在 `seed_device_config.py` 里的"总是按四房释义"改成"按 house_type 释义"，如果现场接线本身不遵循任一标准惯例，该方案依然会出错。

### 两方案共同的前置步骤（无论选哪个都需要先做）

1. **现场核对**：对至少 3-1-702 及若干其他疑似问题户，取得现场 PLC 组态原始文档或安排现场验证，确认 DB14 偏移量 1395/1455/1515/1575 的真实接线含义，形成"标准接线惯例 vs 例外户清单"。
2. **生产库核查**（第 5 节开放问题 SQL）：确认当前 `DeviceRoom`/`DeviceNode`（链路 C）数据的准确性和更新时效，避免用过时的云端房间树数据做修复依据。
3. 无论选择哪个方案，都建议先在 `utils_room_filter.py` / `views_device_settings.py` 增加一条**监控日志**：当某住户同时命中 `panel_bedroom` 和 `panel_children_room`（因两者共享"主卧"关键词）等交叉情况时输出 WARNING，便于后续用生产日志反向定位更多疑似错位户，不依赖用户主动报障。

---

## 7. 待人工确认的开放问题清单

1. **3-1-702 现场 PLC 组态原始接线文档**——需要物业/安装方提供，是唯一能直接证实/证伪"标签与偏移量对应错误"这一根因假设的材料（本仓库不含此类硬件层资料）。
2. **生产库查询**（只读，务必遵守 CLAUDE.md"严禁任何测试连接生产数据库"的约束，此处特指人工只读查询，非自动化测试）：
   - `device_room`/`device_node` 表中 3-1-702 当前的真实房间-设备绑定（第5节 SQL 1）。
   - `plc_latest_data` 表中 3-1-702 四个面板参数（`study_room_switch`/`bedroom_switch`/`children_room_switch`/`fourth_children_room_switch`）在故障发生时间点附近的实际取值（第5节 SQL 2），用于交叉验证"标签贴反"还是"两个面板确实都开着，用户观察时机不同"这两种可能。
3. **是否还有其他住户出现过类似错位投诉**——若有，其房间树结构（是否也是"书房+儿童房"都有的超配户型，还是标准三房/四房）将直接影响方案一 vs 方案二的选型。
4. **`OwnerInfo` 是否可以/应该新增 `house_type` 字段**——需要产品/业务方确认户型分类标准（当前 `utils_room_filter.py` 里的"含书房=四房"启发式规则是否已被业务方正式认可为权威判据，还是仅为临时工程妥协）。
5. **现场安装规范是否存在文档化的"三房/四房接线惯例"**——如果从未有文档化规范、纯靠现场工程师经验接线，那么任何软件层面的静态标签方案都存在"猜错现场实际接线"的残余风险，可能需要引入现场安装后的"逐户核对确认"流程作为长期机制，而不仅是本次一次性修复。

---

## 附：本次调查方法说明

本报告由子代理（general-purpose）完成首轮全仓代码阅读与证据摘录，随后由 PM 对以下关键证据逐条亲自复核（按 CLAUDE.md 第4条要求）：`plc_config.json` 中三/四房 description 字段（142条 grep 命中，第134-310行区间抽样核对）、`seed_device_config.py` 的 `sub_type_display` 89 处赋值（grep 全量核对）、`views_miniapp_device_settings.py:70-80` 的 `PANEL_DISPLAY_MAP` 及其警示注释、`utils_room_filter.py` 全文（含 v0.5.7-fix2 生产事故记录）、`mqtt_handlers.py` 的三处 skip 逻辑（跳过而非压缩的证据）、`views_device_settings.py:203-254` 的标签透传逻辑、`models.py` 中 `DeviceConfig`/`DeviceRoom`/`DeviceNode`/`OwnerInfo`/`PLCLatestData` 五张表结构（尤其 `DeviceConfig.unique_together` 无 `specific_part` 维度这一决定性证据）、`resource/3#_data.json` 中 `3-1-7-702` 原始记录、`fault_consumer/constants.py:244` 注释、以及 `analysis doc/3-1-702_response_raw.json` 原始房间树数据。全部证据均在本报告中给出可复核的文件路径与行号。
