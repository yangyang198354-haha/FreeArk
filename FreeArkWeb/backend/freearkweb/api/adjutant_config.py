"""副官功能开关的数据库配置访问层。"""

from .models import AppFeatureConfig


def _config():
    """获取全局唯一配置；首读时创建，默认保持关闭。"""
    config, _ = AppFeatureConfig.objects.get_or_create(pk=1)
    return config


def read_adjutant_config():
    return {'enabled': _config().adjutant_enabled}


def write_adjutant_config(enabled):
    config = _config()
    config.adjutant_enabled = enabled is True
    config.save(update_fields=['adjutant_enabled', 'updated_at'])
    return {'enabled': config.adjutant_enabled}
