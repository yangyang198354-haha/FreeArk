"""Web 管理端的副官功能开关 API。"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .adjutant_config import read_adjutant_config, write_adjutant_config


def _is_admin(user):
    return (
        getattr(user, 'role', None) == 'admin'
        or getattr(user, 'is_staff', False)
        or getattr(user, 'is_superuser', False)
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def adjutant_config_get(request):
    if not _is_admin(request.user):
        return Response({'success': False, 'error': '权限不足，仅管理员可查看副官配置'}, status=403)
    return Response({'success': True, 'data': read_adjutant_config()})


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def adjutant_config_put(request):
    if not _is_admin(request.user):
        return Response({'success': False, 'error': '权限不足，仅管理员可修改副官配置'}, status=403)
    enabled = request.data.get('enabled')
    if not isinstance(enabled, bool):
        return Response(
            {'success': False, 'error': 'enabled 必须为布尔值'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    config = write_adjutant_config(enabled)
    return Response({'success': True, 'data': config, 'message': '副官开关已保存'})
