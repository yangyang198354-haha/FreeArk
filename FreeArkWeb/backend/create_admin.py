"""
创建超级管理员用户的Django shell脚本
在backend目录下执行: python manage.py shell < create_admin.py
"""
from api.models import CustomUser

# 检查是否已存在管理员用户
if CustomUser.objects.filter(username='admin').exists():
    print("管理员用户 'admin' 已存在")
else:
    # 创建管理员用户
    admin_user = CustomUser.objects.create_superuser(
        username='admin',
        email='admin@example.com',
        password='admin123',
        role='admin',
        first_name='系统',
        last_name='管理员',
        department='IT部门',
        position='系统管理员'
    )
    
    print(f"超级管理员用户创建成功：")
    print(f"用户名: {admin_user.username}")
    print(f"邮箱: {admin_user.email}")
    print(f"角色: {admin_user.role}")
    print(f"密码: admin123 (请及时修改)")