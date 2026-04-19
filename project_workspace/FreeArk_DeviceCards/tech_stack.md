# Tech Stack — FreeArk Device Cards

**Status**: APPROVED
**Phase**: PHASE_03
**Date**: 2026-04-19

---

## Backend

| Layer | Technology | Version | Notes |
|-------|-----------|---------|-------|
| Web Framework | Django | 5.2 | Existing |
| REST API | Django REST Framework | 3.x | Existing |
| Database (production) | MySQL | 8.x | 192.168.31.98:3306 |
| Database (test) | SQLite | :memory: | Enforced by test_settings.py |
| Authentication | Token Authentication | DRF built-in | Existing; new endpoints are AllowAny |
| Python | Python | 3.11+ | Existing |

## Frontend

| Layer | Technology | Version | Notes |
|-------|-----------|---------|-------|
| Framework | Vue.js | 3.x | Existing |
| UI Library | Element Plus | Latest | Existing; el-card, el-table, el-pagination, el-tag, el-input, el-date-picker |
| HTTP Client | axios (via api.js) | Existing | Existing utility |
| Router | Vue Router | 4.x | Existing |

## Deployment

- Physical machine (Raspberry Pi, 192.168.31.51), no Docker
- Backend served via existing systemd service `freeark-backend`
- Frontend built with Vite, served via Nginx
- No new services required for this feature

## Constraints Honoured

- No Docker
- Test database: SQLite :memory: (test_settings.py)
- No Mock DB in tests — real SQLite writes
- Frontend new views registered to existing router
- Backend new APIs registered to existing urlpatterns
