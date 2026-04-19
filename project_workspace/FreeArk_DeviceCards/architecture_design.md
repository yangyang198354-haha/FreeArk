# Architecture Design — FreeArk Device Cards (REQ-FUNC-033/034)

**Status**: APPROVED
**Phase**: PHASE_03
**Author**: sub_agent_system_architect
**Date**: 2026-04-19

---

## 1. Scope

This document covers the architectural decisions for:
- REQ-FUNC-033: Non-proprietary device realtime parameter card panel
- REQ-FUNC-034: Non-proprietary device historical parameter query
- US-033 / US-034: Operator-facing UI workflows

The feature operates entirely within the existing FreeArk Django + Vue 3 monorepo. No new services or infrastructure are introduced.

---

## 2. Architectural Decisions

### ADR-001: Data Model Strategy — DeviceConfig as param_name→group Mapping Table

**Context**: REQ-FUNC-033 requires grouping PLC parameters by system (e.g., hvac) and sub-type (e.g., main_thermostat, room_panel) for a given residential unit. `PLCLatestData` stores `(specific_part, param_name, value, collected_at)` — `specific_part` is the residential unit identifier (e.g., `9-1-31-3104`) and `param_name` is the PLC parameter name (e.g., `living_room_temperature`). The card panel is always viewed in the context of a selected `specific_part`.

**Options Considered**:
1. Create a new `DeviceLatestData` model separate from `PLCLatestData`
2. Reuse `PLCLatestData`, add a `DeviceConfig` model as a param→group metadata mapping table
3. Embed group/type in `param_name` via naming convention with no extra model

**Decision**: Option 2 — Reuse `PLCLatestData` with `DeviceConfig` as a param→group mapping table.

**Rationale**:
- `PLCLatestData` already has the correct schema. The card panel queries it by `specific_part` (the selected residential unit) and gets all PLC parameters for that unit.
- `DeviceConfig` maps each `param_name` → `(group, sub_type, display_name)`. It is a static configuration table, not a device registry.
- `DeviceConfig.device_id` (the old incorrect field) has been replaced by `DeviceConfig.param_name`. The previous design incorrectly stored device identifiers in this field and tried to JOIN with `PLCLatestData.specific_part`, which always returned empty results because the two fields have entirely different semantics.
- The correct JOIN is: query `PLCLatestData` by `specific_part`, then use `DeviceConfig` to look up each `param_name`'s group/sub_type.

**Rejected**: Option 1 duplicates schema. Option 3 is brittle and makes dynamic display names impossible.

---

### ADR-002: History Data Source — PLCLatestData is a Latest-Only Snapshot; Introduce DeviceParamHistory

**Context**: `PLCLatestData` has `unique_together = [['specific_part', 'param_name']]` — it only stores the latest value per (device, param). REQ-FUNC-034 requires historical snapshots with `collected_at` ordering and pagination.

**Options Considered**:
1. Remove `unique_together` from `PLCLatestData` and make it time-series
2. Add a new `DeviceParamHistory` model as a time-series append-only store
3. Use `PLCData` (which lacks param_name) for history

**Decision**: Option 2 — New `DeviceParamHistory` model.

**Rationale**:
- `PLCLatestData` is intentionally a "latest-only" cache. Changing its semantics breaks the existing PLC dashboard which depends on the unique_together guarantee.
- `DeviceParamHistory` can be an append-only log written by the MQTT handler every time a new reading arrives, independent of the upsert logic in `PLCLatestData`.
- `PLCData` schema does not include `param_name`, so Option 3 is not applicable.

**Rejected**: Option 1 breaks existing functionality. Option 3 is schema-incompatible.

---

### ADR-003: API Design — Two New Endpoints Under `/api/devices/`

**Endpoints**:
- `GET /api/devices/realtime-params/?specific_part=<sp>[&group=<g>]` — grouped card data (REQ-FUNC-033)
- `GET /api/devices/param-history/?specific_part=<sp>[&sub_type=<st>][&param_name=<pn>]` — paginated history (REQ-FUNC-034)

**Design**:
- Both are `AllowAny` (public, consistent with existing PLC status APIs).
- `specific_part` is a **required** query parameter on both endpoints. If omitted, the API returns 400.
- `realtime-params/` queries `PLCLatestData` filtered by `specific_part`, builds a `param_name → record` map, then uses `DeviceConfig` to assign each param to its `group/sub_type`. Response structure: `{group → sub_types → {sub_type → {display, params: [{param_name, display_name, value, is_stale}]}}}`. The `devices` nesting layer is removed — a `sub_type` IS the grouping unit for a given `specific_part`.
- `param-history/` queries `DeviceParamHistory` by `specific_part`, supports optional `sub_type` filter (resolved to `param_name` list via `DeviceConfig`), `param_name`, `start_time`, `end_time`, `page`, `page_size`.
- Data timeout detection (>10 min since `collected_at`) computed server-side and included in `realtime-params` response as `is_stale: bool`.
- The old `param-history/<device_id>/` URL path parameter is replaced by query param `?specific_part=...`.

---

### ADR-004: Frontend — Two New Vue 3 Views

**Views**:
- `DeviceCardsView.vue` — card grid grouped by system → sub-type, polls every 30s
- `DeviceParamHistoryView.vue` — paginated table with filters, accessible via `/device-history/:deviceId`

**Design**:
- Uses existing Element Plus component set (el-card, el-table, el-pagination, el-tag).
- Navigation from card's "历史数据 >" link passes `device_id` via route param.
- Stale data (`is_stale: true`) renders param value with an `el-tag` warning "数据超时".
- No global state store needed — each view manages its own local data via `data()` and `methods`, consistent with existing views.

---

### ADR-005: MQTT Write Path — DeviceParamHistory Written by Existing Handler Infrastructure

**Decision**: The `DeviceParamHistory` write will be performed in the same MQTT handler flow used by `PLCLatestData`. A new `GenericDeviceHandler` class will be added to `mqtt_handlers.py`, following the existing `PLCLatestDataHandler` pattern.

**Rationale**: Keeps all MQTT processing in one module. The handler checks `DeviceConfig` to determine if a message topic/device_id belongs to a registered non-proprietary device before writing history.

---

## 3. Component Interaction Diagram

```
MQTT Broker
    |
    v
mqtt_consumer.py
    |---> PLCLatestDataHandler  (existing, writes plc_latest_data)
    |---> GenericDeviceHandler  (NEW, writes plc_latest_data + device_param_history)
    
Frontend (Vue 3)
    |
    |---> DeviceCardsView.vue
    |       GET /api/devices/realtime-params/?group=hvac
    |       <-- { hvac: { main_thermostat: [{device_id, name, params, is_stale}] }}
    |
    |---> DeviceParamHistoryView.vue
            GET /api/devices/param-history/<device_id>/?param_name=&start_time=&end_time=&page=1&page_size=50
            <-- { count, page, page_size, results: [{param_name, value, collected_at}] }

Backend (Django DRF)
    |
    |---> DeviceRealtimeParamsView    (new view function)
    |---> DeviceParamHistoryView      (new view function)
    |---> DeviceConfig model          (new)
    |---> DeviceParamHistory model    (new)
    |---> PLCLatestData model         (existing, reused)
```

---

## 4. Database Schema

### New Model: DeviceConfig

| Field | Type | Notes |
|-------|------|-------|
| id | AutoField PK | |
| param_name | CharField(100) unique | PLC parameter name, matches PLCLatestData.param_name |
| display_name | CharField(200) | Human-readable display name for this param (e.g. "客厅实际温度") |
| group | CharField(50) | e.g. "hvac" |
| sub_type | CharField(50) | e.g. "main_thermostat", "panel_living_room" |
| group_display | CharField(100) | e.g. "暖通" |
| sub_type_display | CharField(100) | e.g. "主温控器" |
| is_active | BooleanField default True | Inactive params are excluded from card panel |
| created_at | DateTimeField auto_now_add | |

Note: The previous `device_id` field (a device identifier string) has been replaced by `param_name`. `DeviceConfig` is now a parameter→group mapping table, not a device registry.

### New Model: DeviceParamHistory

| Field | Type | Notes |
|-------|------|-------|
| id | BigAutoField PK | |
| specific_part | CharField(50) db_index | Residential unit identifier, e.g. "9-1-31-3104" |
| param_name | CharField(100) | Parameter name, matches PLCLatestData.param_name |
| value | TextField nullable | |
| collected_at | DateTimeField db_index | Timestamp from MQTT message |
| created_at | DateTimeField auto_now_add | Record creation time |

Note: The previous `device_id` field has been replaced by `specific_part`, aligning with how PLCLatestData identifies residential units.

Indexes: `(specific_part, collected_at)`, `(specific_part, param_name, collected_at)`

---

## 5. API Response Schemas

### GET /api/devices/realtime-params/?specific_part=9-1-31-3104

```json
{
  "success": true,
  "specific_part": "9-1-31-3104",
  "data": {
    "hvac": {
      "display": "暖通",
      "sub_types": {
        "main_thermostat": {
          "display": "主温控器",
          "params": [
            {
              "param_name": "living_room_temperature",
              "display_name": "客厅实际温度",
              "value": 245,
              "collected_at": "2026-04-19 10:00:00",
              "is_stale": false
            }
          ]
        }
      }
    }
  }
}
```

Note: The `devices` list nesting is removed. A `sub_type` directly contains `params`. Sub-types with no data for the given `specific_part` are excluded from the response.

### GET /api/devices/param-history/?specific_part=9-1-31-3104&sub_type=main_thermostat

```json
{
  "success": true,
  "specific_part": "9-1-31-3104",
  "count": 120,
  "page": 1,
  "page_size": 50,
  "results": [
    {
      "id": 1,
      "param_name": "living_room_temperature",
      "value": 245,
      "collected_at": "2026-04-19 10:00:00"
    }
  ]
}
```
