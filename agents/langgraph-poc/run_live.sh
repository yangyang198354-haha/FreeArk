#!/usr/bin/env bash
# 真机端到端基准启动脚本（仅在 Pi 上 /tmp/lg-poc 运行；不入仓，跑完即删）
set -e

# 1) 解封 energy-agent 会话（服务账号现已豁免不活跃超时；此步保留为兜底，等价一次正常请求）
cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb
/home/yangyang/Freeark/FreeArk/venv/bin/python manage.py shell -c "from api.models import TokenActivity
from rest_framework.authtoken.models import Token
from django.utils.timezone import now
t=Token.objects.get(user__username='energy-agent')
TokenActivity.objects.update_or_create(token=t, defaults={'last_active_at': now()})
print('session_reactivated')"

# 2) 注入凭据（命令替换捕获，绝不回显）
export DEEPSEEK_API_KEY="$(/tmp/lg-poc/.venv/bin/python -c "import re;print(re.search(r'sk-[A-Za-z0-9_\-]{16,}',open('/home/yangyang/.openclaw/agents/main/agent/auth-profiles.json').read()).group())")"
export DEEPSEEK_BASE_URL=https://api.deepseek.com
export POC_MODEL=deepseek-v4-flash
export FREEARK_POC_LIVE=1
set -a; . /home/yangyang/.openclaw/freeark.env; set +a
export FREEARK_API_BASE=http://127.0.0.1:8000
export FREEARK_SKILL_DIR=/home/yangyang/Freeark/FreeArk/agents/freeark-skill

# 3) 跑端到端基准
cd /tmp/lg-poc
PYTHONIOENCODING=utf-8 .venv/bin/python live_bench.py
