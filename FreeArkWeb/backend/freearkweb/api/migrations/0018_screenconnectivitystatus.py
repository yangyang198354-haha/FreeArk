# CONFLICT RESOLUTION: This file was originally numbered 0018 but conflicted with
# 0018_deviceconfig_allow_multi_subtype. The actual table creation has been moved to
# 0019_screenconnectivitystatus.py. This file is now a no-op bridge migration.
# author_agent: sub_agent_test_engineer (conflict resolution)
# project: FreeArk_DeviceManagement

from django.db import migrations


class Migration(migrations.Migration):
    """No-op bridge migration — actual ScreenConnectivityStatus table creation is in 0019."""

    dependencies = [
        ('api', '0018_deviceconfig_allow_multi_subtype'),
    ]

    operations = [
        # No operations — table is created in 0019_screenconnectivitystatus
    ]
