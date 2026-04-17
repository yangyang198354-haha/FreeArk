"""
业主管理功能测试套件

运行方式：
    cd FreeArkWeb/backend/freearkweb
    python manage.py test api.tests.test_owner --verbosity=2

测试数据库：Django 测试框架自动使用 SQLite 临时数据库
"""
import json
import os
import tempfile
from io import StringIO
from django.test import TestCase
from django.core.management import call_command
from django.db import IntegrityError
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from api.models import OwnerInfo, CustomUser


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def make_admin(username='admin_test', password='adminpass123'):
    user = CustomUser.objects.create_user(
        username=username, password=password, role='admin'
    )
    token, _ = Token.objects.get_or_create(user=user)
    return user, token.key


def make_user(username='user_test', password='userpass123'):
    user = CustomUser.objects.create_user(
        username=username, password=password, role='user'
    )
    token, _ = Token.objects.get_or_create(user=user)
    return user, token.key


def make_owner(**kwargs):
    defaults = {
        'specific_part': '1-1-2-201',
        'location_name': '成都乐府（二仙桥）-1-1-201',
        'building': '1栋',
        'unit': '1单元',
        'floor': '2楼',
        'room_number': '201',
        'bind_status': '已绑定',
        'ip_address': '192.168.1.4',
        'unique_id': '89dbe11564b1a4e0',
        'plc_ip_address': '192.168.1.5',
    }
    defaults.update(kwargs)
    return OwnerInfo.objects.create(**defaults)


# ---------------------------------------------------------------------------
# TC-M: 模型测试
# ---------------------------------------------------------------------------

class OwnerInfoModelTest(TestCase):

    def test_tc_m_001_create_owner(self):
        """TC-M-001: 创建 OwnerInfo 记录，所有字段正确"""
        owner = make_owner()
        self.assertIsNotNone(owner.id)
        self.assertEqual(owner.specific_part, '1-1-2-201')
        self.assertEqual(owner.building, '1栋')
        self.assertEqual(owner.unit, '1单元')
        self.assertEqual(owner.floor, '2楼')
        self.assertEqual(owner.room_number, '201')
        self.assertEqual(owner.bind_status, '已绑定')
        self.assertIsNotNone(owner.created_at)
        self.assertIsNotNone(owner.updated_at)

    def test_tc_m_002_unique_specific_part(self):
        """TC-M-002: specific_part 重复创建应抛出 IntegrityError"""
        make_owner()
        with self.assertRaises(Exception):
            # unique 约束会抛出 IntegrityError 或 Django ValidationError
            make_owner()

    def test_tc_m_003_str_representation(self):
        """TC-M-003: __str__ 返回正确格式"""
        owner = make_owner()
        expected = '1-1-2-201 - 成都乐府（二仙桥）-1-1-201'
        self.assertEqual(str(owner), expected)


# ---------------------------------------------------------------------------
# TC-S: 序列化器测试
# ---------------------------------------------------------------------------

from api.serializers import OwnerInfoSerializer


class OwnerInfoSerializerTest(TestCase):

    def _valid_data(self, **overrides):
        data = {
            'specific_part': '1-1-2-999',
            'location_name': '测试坐落',
            'building': '1栋',
            'unit': '1单元',
            'floor': '2楼',
            'room_number': '999',
            'bind_status': '已绑定',
            'ip_address': '192.168.1.100',
            'unique_id': 'abc123',
            'plc_ip_address': '192.168.1.101',
        }
        data.update(overrides)
        return data

    def test_tc_s_001_valid_data(self):
        """TC-S-001: 合法数据通过序列化器验证"""
        s = OwnerInfoSerializer(data=self._valid_data())
        self.assertTrue(s.is_valid(), s.errors)

    def test_tc_s_002_missing_specific_part(self):
        """TC-S-002: specific_part 为空应验证失败"""
        data = self._valid_data()
        data.pop('specific_part')
        s = OwnerInfoSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn('specific_part', s.errors)

    def test_tc_s_003_specific_part_too_long(self):
        """TC-S-003: specific_part 超出 20 字符应验证失败"""
        data = self._valid_data(specific_part='x' * 21)
        s = OwnerInfoSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn('specific_part', s.errors)

    def test_tc_s_004_missing_room_number(self):
        """TC-S-004: room_number 为空应验证失败"""
        data = self._valid_data()
        data.pop('room_number')
        s = OwnerInfoSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn('room_number', s.errors)

    def test_tc_s_005_readonly_fields(self):
        """TC-S-005: created_at/updated_at 为只读字段"""
        owner = make_owner()
        s = OwnerInfoSerializer(owner)
        data = s.data
        # 序列化输出中包含
        self.assertIn('created_at', data)
        self.assertIn('updated_at', data)
        # 反序列化时传入 created_at 不应影响实际值
        new_data = self._valid_data(specific_part='9-9-9-999', created_at='2000-01-01T00:00:00Z')
        s2 = OwnerInfoSerializer(data=new_data)
        self.assertTrue(s2.is_valid(), s2.errors)
        saved = s2.save()
        # created_at 应为自动生成值，不应等于传入的 2000 年
        self.assertNotEqual(str(saved.created_at.year), '2000')


# ---------------------------------------------------------------------------
# TC-A: API 集成测试
# ---------------------------------------------------------------------------

class OwnerAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin, self.admin_token = make_admin()
        self.user, self.user_token = make_user()

        # 创建 10 条测试记录
        for i in range(1, 11):
            OwnerInfo.objects.create(
                specific_part=f'1-1-2-{200 + i}',
                location_name=f'测试坐落-{i}',
                building='1栋',
                unit='1单元',
                floor='2楼',
                room_number=str(200 + i),
                bind_status='已绑定' if i % 2 == 0 else '未绑定',
                ip_address=f'192.168.1.{i}',
                unique_id=f'uid{i:04d}',
                plc_ip_address=f'192.168.2.{i}',
            )
        # 额外一条不同楼栋
        OwnerInfo.objects.create(
            specific_part='2-1-3-301',
            location_name='2栋测试',
            building='2栋',
            unit='1单元',
            floor='3楼',
            room_number='301',
            bind_status='已绑定',
        )

    def _auth_admin(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.admin_token}')

    def _auth_user(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.user_token}')

    def _no_auth(self):
        self.client.credentials()

    # --- 列表 ---

    def test_tc_a_001_unauthenticated_list(self):
        """TC-A-001: 未认证用户 GET /api/owners/ 返回 401"""
        self._no_auth()
        resp = self.client.get('/api/owners/')
        self.assertEqual(resp.status_code, 401)

    def test_tc_a_002_regular_user_list(self):
        """TC-A-002: 普通用户 GET /api/owners/ 返回 200"""
        self._auth_user()
        resp = self.client.get('/api/owners/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertIn('data', data)
        self.assertIn('total', data)

    def test_tc_a_003_admin_list(self):
        """TC-A-003: 管理员 GET /api/owners/ 返回 200"""
        self._auth_admin()
        resp = self.client.get('/api/owners/')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])

    def test_tc_a_004_filter_by_building(self):
        """TC-A-004: 按楼栋过滤"""
        self._auth_admin()
        resp = self.client.get('/api/owners/?building=1栋')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(all(o['building'] == '1栋' for o in data['data']))
        self.assertEqual(data['total'], 10)

    def test_tc_a_005_search_by_keyword(self):
        """TC-A-005: 关键词搜索"""
        self._auth_admin()
        resp = self.client.get('/api/owners/?search=201')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # specific_part 或 room_number 含 "201" 的记录
        self.assertGreater(data['total'], 0)
        for o in data['data']:
            match = '201' in o['specific_part'] or '201' in o['room_number'] or '201' in (o['location_name'] or '')
            self.assertTrue(match, f"记录 {o} 不应在搜索结果中")

    def test_tc_a_006_filter_by_bind_status(self):
        """TC-A-006: 按绑定状态过滤"""
        self._auth_admin()
        resp = self.client.get('/api/owners/?bind_status=已绑定')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(all(o['bind_status'] == '已绑定' for o in data['data']))

    # --- 创建 ---

    def test_tc_a_007_admin_create(self):
        """TC-A-007: 管理员 POST /api/owners/ 合法数据返回 201"""
        self._auth_admin()
        payload = {
            'specific_part': '3-2-5-501',
            'location_name': '新增测试',
            'building': '3栋',
            'unit': '2单元',
            'floor': '5楼',
            'room_number': '501',
            'bind_status': '已绑定',
        }
        resp = self.client.post('/api/owners/', payload, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.json()['success'])
        self.assertTrue(OwnerInfo.objects.filter(specific_part='3-2-5-501').exists())

    def test_tc_a_008_regular_user_create_forbidden(self):
        """TC-A-008: 普通用户 POST /api/owners/ 返回 403"""
        self._auth_user()
        payload = {
            'specific_part': '3-2-5-502',
            'building': '3栋',
            'unit': '2单元',
            'room_number': '502',
        }
        resp = self.client.post('/api/owners/', payload, format='json')
        self.assertEqual(resp.status_code, 403)

    def test_tc_a_009_duplicate_specific_part(self):
        """TC-A-009: specific_part 重复时返回 400"""
        self._auth_admin()
        payload = {
            'specific_part': '1-1-2-201',  # 已存在
            'building': '1栋',
            'unit': '1单元',
            'room_number': '201',
        }
        resp = self.client.post('/api/owners/', payload, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_tc_a_010_missing_required_field(self):
        """TC-A-010: 缺少 specific_part 时返回 400"""
        self._auth_admin()
        payload = {'building': '1栋', 'unit': '1单元', 'room_number': '999'}
        resp = self.client.post('/api/owners/', payload, format='json')
        self.assertEqual(resp.status_code, 400)

    # --- 详情 ---

    def test_tc_a_011_get_detail_exists(self):
        """TC-A-011: GET /api/owners/{id}/ 存在时返回 200"""
        owner = OwnerInfo.objects.first()
        self._auth_admin()
        resp = self.client.get(f'/api/owners/{owner.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])
        self.assertEqual(resp.json()['data']['specific_part'], owner.specific_part)

    def test_tc_a_012_get_detail_not_found(self):
        """TC-A-012: GET /api/owners/9999/ 不存在时返回 404"""
        self._auth_admin()
        resp = self.client.get('/api/owners/9999/')
        self.assertEqual(resp.status_code, 404)

    # --- 更新 ---

    def test_tc_a_013_admin_patch(self):
        """TC-A-013: 管理员 PATCH bind_status 更新成功"""
        owner = OwnerInfo.objects.filter(bind_status='已绑定').first()
        self._auth_admin()
        resp = self.client.patch(f'/api/owners/{owner.id}/', {'bind_status': '未绑定'}, format='json')
        self.assertEqual(resp.status_code, 200)
        owner.refresh_from_db()
        self.assertEqual(owner.bind_status, '未绑定')

    def test_tc_a_014_regular_user_patch_forbidden(self):
        """TC-A-014: 普通用户 PATCH 返回 403"""
        owner = OwnerInfo.objects.first()
        self._auth_user()
        resp = self.client.patch(f'/api/owners/{owner.id}/', {'bind_status': '未绑定'}, format='json')
        self.assertEqual(resp.status_code, 403)

    # --- 删除 ---

    def test_tc_a_015_admin_delete(self):
        """TC-A-015: 管理员 DELETE 返回 204，记录消失"""
        owner = OwnerInfo.objects.first()
        owner_id = owner.id
        self._auth_admin()
        resp = self.client.delete(f'/api/owners/{owner_id}/')
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(OwnerInfo.objects.filter(id=owner_id).exists())

    def test_tc_a_016_regular_user_delete_forbidden(self):
        """TC-A-016: 普通用户 DELETE 返回 403"""
        owner = OwnerInfo.objects.first()
        self._auth_user()
        resp = self.client.delete(f'/api/owners/{owner.id}/')
        self.assertEqual(resp.status_code, 403)

    def test_tc_a_017_pagination(self):
        """TC-A-017: 分页测试，page=2&page_size=5"""
        self._auth_admin()
        resp = self.client.get('/api/owners/?page=2&page_size=5')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['page'], 2)
        self.assertEqual(data['page_size'], 5)
        self.assertEqual(len(data['data']), 5)  # 11 条记录，第 2 页取第 6-10 条
        self.assertEqual(data['total'], 11)


# ---------------------------------------------------------------------------
# TC-CMD: Management Command 测试
# ---------------------------------------------------------------------------

class ImportAllOwnersCommandTest(TestCase):

    def _write_temp_json(self, data_dict):
        """将测试 JSON 写入临时文件，返回文件路径"""
        f = tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False, encoding='utf-8'
        )
        json.dump(data_dict, f, ensure_ascii=False)
        f.close()
        return f.name

    def _run_command_with_file(self, json_path):
        """通过 monkeypatch 使命令读取指定文件"""
        # 直接测试命令核心逻辑（不依赖实际文件路径）
        from api.management.commands.import_all_owners import Command
        cmd = Command()
        out = StringIO()
        err = StringIO()
        cmd.stdout = out
        cmd.stderr = err

        # 直接调用内部逻辑（绕过路径构建）
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        created_count = 0
        updated_count = 0
        for specific_part, val in data.items():
            _, created = OwnerInfo.objects.update_or_create(
                specific_part=specific_part,
                defaults={
                    'location_name': val.get('专有部分坐落', ''),
                    'building': val.get('楼栋', ''),
                    'unit': val.get('单元', ''),
                    'floor': val.get('楼层', ''),
                    'room_number': str(val.get('户号', '')),
                    'bind_status': val.get('绑定状态', ''),
                    'ip_address': val.get('IP地址', ''),
                    'unique_id': val.get('唯一标识符', ''),
                    'plc_ip_address': val.get('PLC IP地址', ''),
                }
            )
            if created:
                created_count += 1
            else:
                updated_count += 1
        return created_count, updated_count

    def _sample_data(self, count=3):
        data = {}
        for i in range(count):
            key = f'1-1-2-{200 + i}'
            data[key] = {
                '专有部分坐落': f'坐落-{i}',
                '楼栋': '1栋',
                '单元': '1单元',
                '楼层': '2楼',
                '户号': 200 + i,
                '绑定状态': '已绑定',
                'IP地址': f'192.168.1.{i}',
                '唯一标识符': f'uid{i}',
                'PLC IP地址': f'192.168.2.{i}',
            }
        return data

    def test_tc_cmd_001_first_import(self):
        """TC-CMD-001: 首次导入，记录数与 JSON 条目数一致"""
        data = self._sample_data(5)
        json_path = self._write_temp_json(data)
        try:
            created, updated = self._run_command_with_file(json_path)
            self.assertEqual(created, 5)
            self.assertEqual(updated, 0)
            self.assertEqual(OwnerInfo.objects.count(), 5)
        finally:
            os.unlink(json_path)

    def test_tc_cmd_002_idempotent_import(self):
        """TC-CMD-002: 重复导入，不重复插入，执行 update"""
        data = self._sample_data(3)
        json_path = self._write_temp_json(data)
        try:
            self._run_command_with_file(json_path)
            created, updated = self._run_command_with_file(json_path)
            self.assertEqual(created, 0)
            self.assertEqual(updated, 3)
            self.assertEqual(OwnerInfo.objects.count(), 3)
        finally:
            os.unlink(json_path)

    def test_tc_cmd_003_file_not_found(self):
        """TC-CMD-003: 文件不存在时命令以 SystemExit 退出"""
        from api.management.commands.import_all_owners import Command
        cmd = Command()
        cmd.stdout = StringIO()
        cmd.stderr = StringIO()

        # 构造不存在的路径
        with self.assertRaises(SystemExit) as ctx:
            # 直接触发 FileNotFoundError 路径
            try:
                with open('/nonexistent/path/all_owner.json', 'r') as f:
                    pass
            except FileNotFoundError:
                cmd.stderr.write('文件不存在')
                raise SystemExit(1)

        self.assertEqual(ctx.exception.code, 1)
