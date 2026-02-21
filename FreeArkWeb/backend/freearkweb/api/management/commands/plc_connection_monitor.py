import time
import logging
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from api.models import PLCConnectionStatus, PLCStatusChangeHistory

# 导入统一的日志工具
from .common import get_service_logger, log_service_start, log_service_stop, log_task_start, log_task_completion, log_error, log_warning

# 获取配置好的日志器
logger = get_service_logger('plc_connection_monitor')


class Command(BaseCommand):
    """
    Django管理命令：PLC连接状态监控服务
    用于定期检查PLC设备的连接状态，标记长时间未通信的设备为离线
    """
    help = '启动PLC连接状态监控服务，定期检查设备连接状态（使用schedule机制）'

    def add_arguments(self, parser):
        # 添加检查间隔参数（秒）
        parser.add_argument(
            '--check-interval',
            type=int,
            default=300,
            help='设备检查间隔（秒），默认为300秒（5分钟）'
        )
        # 添加超时阈值参数（秒）
        parser.add_argument(
            '--timeout-threshold',
            type=int,
            default=600,
            help='设备超时阈值（秒），默认为600秒（10分钟）'
        )

    def handle(self, *args, **options):
        """命令处理函数"""
        check_interval = options['check_interval']
        timeout_threshold = options['timeout_threshold']
        
        logger.info('🚀 正在启动PLC连接状态监控服务...')
        self.stdout.write(self.style.SUCCESS('🚀 正在启动PLC连接状态监控服务...'))
        
        # 记录服务启动信息
        service_config = {
            'check_interval': f'{check_interval}秒',
            'timeout_threshold': f'{timeout_threshold}秒'
        }
        log_service_start(logger, 'PLC连接状态监控服务', service_config)
        
        exit_code = 0
        
        try:
            # 定期检查设备连接状态
            while True:
                try:
                    log_task_start(logger, 'PLC连接状态检查')
                    self._check_connection_status(timeout_threshold)
                    log_task_completion(logger, 'PLC连接状态检查')
                except Exception as e:
                    log_error(logger, 'PLC连接状态检查失败', e)
                    self.stdout.write(self.style.ERROR(f'❌ PLC连接状态检查失败: {e}'))
                
                # 等待下一次检查
                time.sleep(check_interval)
        
        except KeyboardInterrupt:
            stop_signal_msg = '🛑 收到停止信号...'
            logger.info(stop_signal_msg)
            self.stdout.write('\n' + stop_signal_msg)
        
        except Exception as e:
            log_error(logger, '运行过程中发生错误', e)
            self.stdout.write(self.style.ERROR(f'运行PLC连接状态监控服务时发生错误: {str(e)}'))
            exit_code = 1
        
        finally:
            log_service_stop(logger, 'PLC连接状态监控服务')
            self.stdout.write(self.style.SUCCESS('✅ PLC连接状态监控服务已停止'))
        
        logger.info(f'📋 服务退出，退出码: {exit_code}')
        return exit_code
    
    def _check_connection_status(self, timeout_threshold):
        """检查设备连接状态，标记超时设备为离线"""
        logger.info(f'🔍 开始检查PLC连接状态，超时阈值: {timeout_threshold}秒')
        
        # 计算超时时间
        timeout_time = timezone.now() - timedelta(seconds=timeout_threshold)
        
        # 查询所有在线但超过超时时间未更新的设备
        offline_devices = PLCConnectionStatus.objects.filter(
            connection_status='online',
            last_online_time__lt=timeout_time
        )
        
        offline_count = offline_devices.count()
        logger.debug(f'⏱️  超时时间: {timeout_time}, 发现 {offline_count} 个超时设备')
        
        if offline_count > 0:
            # 记录状态变化历史
            status_change_count = 0
            for device in offline_devices:
                # 记录状态变化历史
                try:
                    PLCStatusChangeHistory.objects.create(
                        specific_part=device.specific_part,
                        status='offline',
                        building=device.building,
                        unit=device.unit,
                        room_number=device.room_number
                    )
                    status_change_count += 1
                except Exception as e:
                    logger.error(f'❌ 记录设备状态变化历史失败 - {device.specific_part}: {e}')
            
            # 批量更新设备状态为离线
            updated_count = offline_devices.update(
                connection_status='offline',
                updated_at=timezone.now()
            )
            
            logger.info(f'🔄 已将 {updated_count} 个超时设备标记为离线，记录了 {status_change_count} 条状态变化历史')
            self.stdout.write(self.style.SUCCESS(f'✅ 已将 {updated_count} 个超时设备标记为离线，记录了 {status_change_count} 条状态变化历史'))
        else:
            logger.info('✅ 所有在线设备均在正常通信范围内')
            self.stdout.write(self.style.SUCCESS('✅ 所有在线设备均在正常通信范围内'))
        
        # 统计当前状态
        online_count = PLCConnectionStatus.objects.filter(connection_status='online').count()
        total_count = PLCConnectionStatus.objects.count()
        
        logger.info(f'📊 当前状态统计: 在线设备 {online_count}/{total_count} 台')
        self.stdout.write(f'📊 当前状态统计: 在线设备 {online_count}/{total_count} 台')
