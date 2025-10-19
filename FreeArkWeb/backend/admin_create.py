# 简化的管理员创建脚本
import os
def main():
    # 使用Django的shell命令来执行
    os.system('python manage.py shell -c "import django; django.setup(); from api.models import CustomUser; print(CustomUser.objects.create_superuser(username=\'admin\', email=\'admin@example.com\', password=\'admin123\', role=\'admin\'))"')

if __name__ == '__main__':
    main()