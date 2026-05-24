"""
Management Command: create_openclaw_agent_user

创建 openclaw-agent 专属服务账号并生成 DRF Token。

用途（来自 DECISIONS-LOBSTER-001 CONFIRM-6）：
  - 为 FreeArk Skill 提供合法的 FreeArk 身份
  - 账号规格：username=openclaw-agent，role=user，is_active=True
  - 生成 DRF Token（无过期时间，与 DRF TokenAuthentication 兼容）

使用方式：
  cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb
  python manage.py create_openclaw_agent_user

输出：Token 明文（仅打印一次），需管理员手动复制到 ~/.openclaw/openclaw.json 的
skill.env.FREEARK_AGENT_TOKEN 字段（不入仓库，mode 600）。

幂等性：若账号已存在则跳过创建；若 Token 已存在则显示 Token 前 8 字符并提示重新生成选项。

安全注意：
  - 此命令输出 Token 明文，在终端运行时注意屏幕安全
  - Token 生成后立即记录到安全位置，命令不会二次显示完整 Token
  - 禁止将 Token 提交到 git 仓库
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = '创建 openclaw-agent 专属服务账号并生成 DRF Token（CONFIRM-6）'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force-regenerate-token',
            action='store_true',
            default=False,
            help='若 Token 已存在，强制删除并重新生成',
        )

    def handle(self, *args, **options):
        from rest_framework.authtoken.models import Token

        User = get_user_model()
        username = 'openclaw-agent'
        force_regen = options['force_regenerate_token']

        self.stdout.write(self.style.NOTICE('\n=== FreeArk Skill — openclaw-agent 账号创建工具 ==='))
        self.stdout.write(self.style.NOTICE('来源: DECISIONS-LOBSTER-001 CONFIRM-6\n'))

        # Step 1: 创建或获取用户
        user, user_created = User.objects.get_or_create(
            username=username,
            defaults={
                'role': 'user',
                'is_active': True,
                'is_staff': False,
                'is_superuser': False,
                'email': 'openclaw-agent@freeark.internal',
                'department': 'AI Agent',
                'position': 'Service Account',
            }
        )

        if user_created:
            # 设置一个不可用的密码（此账号不应通过密码登录，只通过 Token 鉴权）
            user.set_unusable_password()
            user.save()
            self.stdout.write(self.style.SUCCESS(f'[OK] 用户 "{username}" 创建成功'))
        else:
            self.stdout.write(self.style.WARNING(f'[SKIP] 用户 "{username}" 已存在，跳过创建'))
            # 确保账号处于启用状态
            if not user.is_active:
                user.is_active = True
                user.save()
                self.stdout.write(self.style.WARNING(f'[FIX] 用户 "{username}" 已重新激活'))

        # 确认 role=user
        if user.role != 'user':
            self.stdout.write(self.style.WARNING(
                f'[WARN] 当前 role={user.role}，期望 role=user（最小权限原则）。'
                f'请手动通过 Django admin 修正。'
            ))

        # Step 2: 处理 Token
        existing_token = Token.objects.filter(user=user).first()

        if existing_token and not force_regen:
            self.stdout.write(self.style.WARNING(
                f'[SKIP] Token 已存在（前 8 字符: {existing_token.key[:8]}...）\n'
                f'       如需重新生成，请使用 --force-regenerate-token 参数。'
            ))
            self._print_config_instructions(existing_token.key[:8] + '...(已隐藏)', show_full=False)
            return

        if existing_token and force_regen:
            existing_token.delete()
            self.stdout.write(self.style.WARNING('[REGEN] 旧 Token 已删除，正在生成新 Token...'))

        # 生成新 Token
        token = Token.objects.create(user=user)

        self.stdout.write(self.style.SUCCESS('\n[OK] Token 生成成功！'))
        self.stdout.write(self.style.ERROR('\n' + '=' * 60))
        self.stdout.write(self.style.ERROR('!! 重要：以下 Token 只显示一次，请立即复制保存 !!'))
        self.stdout.write(self.style.ERROR('=' * 60))
        self.stdout.write(f'\nFREEARK_AGENT_TOKEN = {token.key}\n')
        self.stdout.write(self.style.ERROR('=' * 60 + '\n'))

        self._print_config_instructions(token.key, show_full=True)

    def _print_config_instructions(self, token_display, show_full=False):
        self.stdout.write(self.style.NOTICE('\n下一步操作：'))
        self.stdout.write('1. 在树莓派上编辑 ~/.openclaw/openclaw.json，在 skills.freeark-skill.env 中设置：')
        if show_full:
            self.stdout.write(f'   "FREEARK_AGENT_TOKEN": "{token_display}"')
        else:
            self.stdout.write(f'   "FREEARK_AGENT_TOKEN": "<上次生成的 Token 值>"')
        self.stdout.write('2. 确保文件权限为 600：chmod 600 ~/.openclaw/openclaw.json')
        self.stdout.write('3. 重启 openclaw-gateway：systemctl --user restart openclaw-gateway.service')
        self.stdout.write('4. 验证：curl -H "Authorization: Token <token>" http://127.0.0.1:8000/api/auth/me/')
        self.stdout.write('\n安全提醒：')
        self.stdout.write('  - Token 不得出现在任何 git 仓库文件中')
        self.stdout.write('  - Token 不得出现在对话内容或日志中')
        self.stdout.write('  - 若 Token 泄露，立即运行 manage.py create_openclaw_agent_user --force-regenerate-token\n')
