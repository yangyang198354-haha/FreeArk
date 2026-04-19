# Module Design — FreeArk Device Cards

**Status**: APPROVED
**Phase**: PHASE_03
**Date**: 2026-04-19

---

## Backend Modules

### M-BE-01: models.py additions

- `DeviceConfig`: metadata registry (group, sub_type, display names, device_id)
- `DeviceParamHistory`: append-only history per (device_id, param_name, collected_at)

### M-BE-02: serializers.py additions

- `DeviceConfigSerializer`: read-only, fields: device_id, display_name, group, sub_type, group_display, sub_type_display
- `DeviceParamHistorySerializer`: fields: id, param_name, value, collected_at

### M-BE-03: views.py additions

- `get_device_realtime_params(request)`: AllowAny, GET. Reads DeviceConfig for active devices (optional group filter), then queries PLCLatestData per device_id. Computes is_stale (now - collected_at > 600s). Returns nested JSON.
- `get_device_param_history(request, device_id)`: AllowAny, GET. Queries DeviceParamHistory filtered by device_id, optional param_name/start_time/end_time, ordered -collected_at, paginated.

### M-BE-04: urls.py additions

```python
path('devices/realtime-params/', views.get_device_realtime_params, name='device-realtime-params'),
path('devices/param-history/<str:device_id>/', views.get_device_param_history, name='device-param-history'),
```

### M-BE-05: migrations

- `0016_deviceconfig_deviceparamhistory.py`: creates DeviceConfig and DeviceParamHistory tables

### M-BE-06: mqtt_handlers.py addition (optional, for write path)

- `GenericDeviceHandler.handle(topic, payload)`: writes to PLCLatestData (upsert) + DeviceParamHistory (append). Activated only for devices registered in DeviceConfig.

---

## Frontend Modules

### M-FE-01: DeviceCardsView.vue

- Path: `FreeArkWeb/frontend/src/views/DeviceCardsView.vue`
- Route: `/device-cards`
- Responsibilities:
  - Calls `GET /api/devices/realtime-params/`
  - Renders el-card grid grouped by sub_type under each group header
  - Shows stale warning tag when `is_stale: true`
  - "历史数据 >" button navigates to `/device-history/:deviceId`
  - Auto-refresh every 30 seconds via setInterval

### M-FE-02: DeviceParamHistoryView.vue

- Path: `FreeArkWeb/frontend/src/views/DeviceParamHistoryView.vue`
- Route: `/device-history/:deviceId`
- Responsibilities:
  - Reads `deviceId` from `$route.params.deviceId`
  - Calls `GET /api/devices/param-history/<device_id>/`
  - Filter bar: param_name (text input), date range pickers (start_time, end_time)
  - el-table with columns: param_name, value, collected_at
  - el-pagination (page, page_size)
  - Back button to `/device-cards`

### M-FE-03: router/index.js additions

```javascript
{
  path: '/device-cards',
  name: 'DeviceCards',
  component: () => import('../views/DeviceCardsView.vue'),
  meta: { requiresAuth: true }
},
{
  path: '/device-history/:deviceId',
  name: 'DeviceParamHistory',
  component: () => import('../views/DeviceParamHistoryView.vue'),
  meta: { requiresAuth: true }
}
```

---

## Interface Contracts

### Backend → Frontend

All responses include `"success": true|false`. Error responses include `"error": "message"`.

Datetime fields formatted as `"YYYY-MM-DD HH:MM:SS"` (consistent with existing API).

### Frontend → Backend

Auth: existing `userToken` from localStorage via `Authorization: Token <token>` header (handled by existing `api.js` utility).

Public endpoints (`AllowAny`) do not require the token header, but the frontend always sends it if logged in.
