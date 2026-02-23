from django.test import TestCase, Client
from django.urls import reverse
from rest_framework import status
from .models import SpecificPartInfo, UsageQuantityMonthly

class SpecificPartInfoModelTest(TestCase):
    """测试SpecificPartInfo模型的创建和查询功能"""
    
    def setUp(self):
        """设置测试数据"""
        # 创建测试数据
        SpecificPartInfo.objects.create(
            screenMAC="00:11:22:33:44:55",
            specific_part="1-1-2-201"
        )
        
    def test_specific_part_info_creation(self):
        """测试创建SpecificPartInfo记录"""
        # 验证测试数据是否创建成功
        specific_part_info = SpecificPartInfo.objects.get(screenMAC="00:11:22:33:44:55")
        self.assertEqual(specific_part_info.specific_part, "1-1-2-201")
    
    def test_specific_part_info_query(self):
        """测试使用screenMAC查询SpecificPartInfo记录"""
        # 使用screenMAC查询
        specific_part_info = SpecificPartInfo.objects.get(screenMAC="00:11:22:33:44:55")
        self.assertEqual(specific_part_info.specific_part, "1-1-2-201")
    
    def test_specific_part_info_unique_screenmac(self):
        """测试screenMAC的唯一性"""
        # 尝试创建重复的screenMAC记录，应该抛出异常
        with self.assertRaises(Exception):
            SpecificPartInfo.objects.create(
                screenMAC="00:11:22:33:44:55",  # 与已存在的screenMAC重复
                specific_part="1-1-2-202"
            )

class GetBillListAPITest(TestCase):
    """测试get_bill_list API的功能"""
    
    def setUp(self):
        """设置测试数据"""
        self.client = Client()
        
        # 创建SpecificPartInfo测试数据
        self.specific_part_info = SpecificPartInfo.objects.create(
            screenMAC="00:11:22:33:44:55",
            specific_part="1-1-2-201"
        )
        
        # 创建UsageQuantityMonthly测试数据
        UsageQuantityMonthly.objects.create(
            specific_part="1-1-2-201",
            building="1",
            unit="1",
            room_number="201",
            energy_mode="制冷",
            initial_energy=1000,
            final_energy=1100,
            usage_quantity=100,
            usage_month="2023-01"
        )
        
        UsageQuantityMonthly.objects.create(
            specific_part="1-1-2-201",
            building="1",
            unit="1",
            room_number="201",
            energy_mode="制热",
            initial_energy=2000,
            final_energy=2150,
            usage_quantity=150,
            usage_month="2023-02"
        )
    
    def test_get_bill_list_with_valid_screenmac(self):
        """测试使用有效的screenMAC查询账单数据"""
        # 构建请求数据
        request_data = {
            "startDate": "2023-01",
            "endDate": "2023-02",
            "energyType": "all",
            "page": 1,
            "size": 10
        }
        
        # 发送请求，在请求头中添加screenMAC
        response = self.client.post(
            reverse('get-bill-list'),
            data=request_data,
            content_type='application/json',
            HTTP_SCREENMAC="00:11:22:33:44:55"
        )
        
        # 验证响应状态码
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # 验证响应数据
        self.assertEqual(response.json()['code'], 200)
        self.assertEqual(response.json()['message'], 'success')
        self.assertEqual(len(response.json()['data']), 2)
    
    def test_get_bill_list_without_screenmac(self):
        """测试请求头中缺少screenMAC的情况"""
        # 构建请求数据
        request_data = {
            "startDate": "2023-01",
            "endDate": "2023-02",
            "energyType": "all",
            "page": 1,
            "size": 10
        }
        
        # 发送请求，不添加screenMAC请求头
        response = self.client.post(
            reverse('get-bill-list'),
            data=request_data,
            content_type='application/json'
        )
        
        # 验证响应状态码
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # 验证响应数据
        self.assertEqual(response.json()['code'], 400)
        self.assertEqual(response.json()['message'], '请求头中缺少screenMAC信息')
    
    def test_get_bill_list_with_invalid_screenmac(self):
        """测试使用无效的screenMAC查询账单数据"""
        # 构建请求数据
        request_data = {
            "startDate": "2023-01",
            "endDate": "2023-02",
            "energyType": "all",
            "page": 1,
            "size": 10
        }
        
        # 发送请求，使用不存在的screenMAC
        response = self.client.post(
            reverse('get-bill-list'),
            data=request_data,
            content_type='application/json',
            HTTP_SCREENMAC="99:99:99:99:99:99"
        )
        
        # 验证响应状态码
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        # 验证响应数据
        self.assertEqual(response.json()['code'], 404)
        self.assertIn('未找到对应的专有部分信息', response.json()['message'])
    
    def test_get_bill_list_with_energy_type_filter(self):
        """测试使用能源类型过滤账单数据"""
        # 构建请求数据，只查询制冷数据
        request_data = {
            "startDate": "2023-01",
            "endDate": "2023-02",
            "energyType": "electric",  # 对应制冷
            "page": 1,
            "size": 10
        }
        
        # 发送请求
        response = self.client.post(
            reverse('get-bill-list'),
            data=request_data,
            content_type='application/json',
            HTTP_SCREENMAC="00:11:22:33:44:55"
        )
        
        # 验证响应状态码
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # 验证响应数据，应该只返回1条制冷数据
        self.assertEqual(len(response.json()['data']), 1)
        self.assertEqual(response.json()['data'][0]['energyType'], 'electric')
    
    def test_get_bill_list_with_time_range_filter(self):
        """测试使用时间范围过滤账单数据"""
        # 构建请求数据，只查询2023-01的数据
        request_data = {
            "startDate": "2023-01",
            "endDate": "2023-01",
            "energyType": "all",
            "page": 1,
            "size": 10
        }
        
        # 发送请求
        response = self.client.post(
            reverse('get-bill-list'),
            data=request_data,
            content_type='application/json',
            HTTP_SCREENMAC="00:11:22:33:44:55"
        )
        
        # 验证响应状态码
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # 验证响应数据，应该只返回1条2023-01的数据
        self.assertEqual(len(response.json()['data']), 1)
        self.assertEqual(response.json()['data'][0]['billingCycle'], '202301')

