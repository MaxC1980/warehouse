import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from config import Config
from database import init_db
import tempfile
import shutil


class TestConfig(Config):
    """测试配置，使用临时数据库"""
    TEST_DB_DIR = tempfile.mkdtemp()
    DATABASE_PATH = os.path.join(TEST_DB_DIR, 'test_api.db')


class TestBase(unittest.TestCase):
    """API测试基类"""

    @classmethod
    def setUpClass(cls):
        cls.old_db_path = Config.DATABASE_PATH
        Config.DATABASE_PATH = TestConfig.DATABASE_PATH
        init_db()
        cls.client = app.test_client()

    @classmethod
    def tearDownClass(cls):
        Config.DATABASE_PATH = cls.old_db_path
        if os.path.exists(TestConfig.TEST_DB_DIR):
            shutil.rmtree(TestConfig.TEST_DB_DIR)


class TestAuthAPI(TestBase):

    def test_login_success(self):
        """登录成功"""
        resp = self.client.post('/api/auth/login', json={
            'username': 'admin',
            'password': 'admin123'
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['username'], 'admin')
        self.assertEqual(data['permission_level'], 3)

    def test_login_invalid_password(self):
        """密码错误"""
        resp = self.client.post('/api/auth/login', json={
            'username': 'admin',
            'password': 'wrong'
        })
        self.assertEqual(resp.status_code, 401)

    def test_login_missing_fields(self):
        """缺少用户名或密码"""
        resp = self.client.post('/api/auth/login', json={
            'username': 'admin'
        })
        self.assertEqual(resp.status_code, 400)

    def test_current_user_not_logged_in(self):
        """未登录获取当前用户"""
        # 登出以确保未登录状态
        self.client.post('/api/auth/logout')
        resp = self.client.get('/api/auth/current_user')
        self.assertEqual(resp.status_code, 401)

    def test_current_user_logged_in(self):
        """登录后获取当前用户"""
        self.client.post('/api/auth/login', json={
            'username': 'admin',
            'password': 'admin123'
        })
        resp = self.client.get('/api/auth/current_user')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['username'], 'admin')

    def test_logout(self):
        """登出"""
        self.client.post('/api/auth/login', json={
            'username': 'admin',
            'password': 'admin123'
        })
        resp = self.client.post('/api/auth/logout')
        self.assertEqual(resp.status_code, 200)
        # 登出后再访问需要重新登录
        resp = self.client.get('/api/auth/current_user')
        self.assertEqual(resp.status_code, 401)


class TestMaterialAPI(TestBase):

    def setUp(self):
        self.client = app.test_client()
        self.client.post('/api/auth/login', json={
            'username': 'admin',
            'password': 'admin123'
        })

    def test_get_materials(self):
        """获取物料列表"""
        resp = self.client.get('/api/materials')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('items', data)

    def test_get_materials_with_pagination(self):
        """物料列表分页"""
        resp = self.client.get('/api/materials?page=1&per_page=10')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('page', data)
        self.assertIn('per_page', data)


class TestInventoryAPI(TestBase):

    def setUp(self):
        self.client = app.test_client()
        self.client.post('/api/auth/login', json={
            'username': 'admin',
            'password': 'admin123'
        })

    def test_get_inventory(self):
        """获取库存列表"""
        resp = self.client.get('/api/inventory')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('items', data)

    def test_get_inventory_by_material(self):
        """获取指定物料库存"""
        # 先创建物料
        resp = self.client.post('/api/materials', json={
            'name': '测试物料X',
            'code': 'TEST-X-001',
            'unit': '个',
            'category_code': '0101'
        })
        material_id = resp.get_json()['id']

        resp = self.client.get(f'/api/inventory/{material_id}')
        # 库存不存在返回404
        self.assertEqual(resp.status_code, 404)


class TestInOrderAPI(TestBase):

    def setUp(self):
        self.client = app.test_client()
        self.client.post('/api/auth/login', json={
            'username': 'admin',
            'password': 'admin123'
        })

    def test_get_in_orders(self):
        """获取入库单列表"""
        resp = self.client.get('/api/in-orders')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('items', data)

    def test_create_in_order(self):
        """创建入库单"""
        # 先创建供应商
        resp = self.client.post('/api/suppliers', json={
            'name': '测试供应商-入',
            'contact': '张三',
            'phone': '13800138000'
        })
        supplier_id = resp.get_json()['id']

        # 创建物料
        resp = self.client.post('/api/materials', json={
            'name': '测试物料-IN',
            'code': 'TEST-IN-001',
            'unit': '个',
            'category_code': '0101'
        })
        material_id = resp.get_json()['id']

        # 创建入库单
        resp = self.client.post('/api/in-orders', json={
            'supplier_id': supplier_id,
            'operator_id': 1,
            'receiver': '张三',
            'remark': 'API测试入库',
            'items': [{
                'material_id': material_id,
                'batch_no': 'BATCH-API-001',
                'quantity': 100,
                'unit_price': 10.0
            }]
        })
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()
        self.assertEqual(data['remark'], 'API测试入库')

    def test_in_order_detail_pagination_by_items(self):
        """入库台账按items分页，一个订单跨页"""
        # 先创建供应商
        resp = self.client.post('/api/suppliers', json={
            'name': '测试供应商-分页',
            'contact': '测试',
            'phone': '13800138001'
        })
        supplier_id = resp.get_json()['id']

        # 创建10个物料
        material_ids = []
        for i in range(10):
            resp = self.client.post('/api/materials', json={
                'name': f'分页物料-{i}',
                'code': f'TEST-PAGE-{i:02d}',
                'unit': '个',
                'category_code': '0101'
            })
            material_ids.append(resp.get_json()['id'])

        # 创建入库单 with 10 items
        items = [
            {
                'material_id': material_ids[i],
                'batch_no': f'BATCH-PAGE-{i:02d}',
                'quantity': 10 + i,
                'unit_price': 10.0
            }
            for i in range(10)
        ]
        resp = self.client.post('/api/in-orders', json={
            'supplier_id': supplier_id,
            'operator_id': 1,
            'receiver': '分页测试',
            'items': items
        })
        self.assertEqual(resp.status_code, 201)

        # 查询 page 1, per_page=5
        resp = self.client.get('/api/in-orders/detail?page=1&per_page=5')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()

        page1_item_count = sum(len(o['items']) for o in data['items'])
        self.assertEqual(page1_item_count, 5)

        # 查询 page 2
        resp = self.client.get('/api/in-orders/detail?page=2&per_page=5')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()

        page2_item_count = sum(len(o['items']) for o in data['items'])
        self.assertEqual(page2_item_count, 5)


class TestOutOrderAPI(TestBase):

    def setUp(self):
        self.client = app.test_client()
        self.client.post('/api/auth/login', json={
            'username': 'admin',
            'password': 'admin123'
        })

    def test_get_out_orders(self):
        """获取出库单列表"""
        resp = self.client.get('/api/out-orders')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('items', data)

    def test_create_out_order_requires_approved_in_order(self):
        """创建出库单需要先有审核通过的入库单"""
        # 先创建供应商
        resp = self.client.post('/api/suppliers', json={
            'name': '测试供应商-出',
            'contact': '李四',
            'phone': '13900139000'
        })
        supplier_id = resp.get_json()['id']

        # 创建物料
        resp = self.client.post('/api/materials', json={
            'name': '测试物料-OUT',
            'code': 'TEST-OUT-001',
            'unit': '个',
            'category_code': '0101'
        })
        material_id = resp.get_json()['id']

        # 创建入库单
        resp = self.client.post('/api/in-orders', json={
            'supplier_id': supplier_id,
            'operator_id': 1,
            'receiver': '李四',
            'items': [{
                'material_id': material_id,
                'batch_no': 'BATCH-OUT-001',
                'quantity': 100,
                'unit_price': 10.0
            }]
        })
        in_order_id = resp.get_json()['id']

        # 审核入库单
        resp = self.client.post(f'/api/in-orders/{in_order_id}/approve')
        self.assertEqual(resp.status_code, 200)

        # 创建出库单
        resp = self.client.post('/api/out-orders', json={
            'department': '测试部门',
            'receiver': '王五',
            'receiver_date': '2026-04-18',
            'operator_id': 1,
            'purpose': '生产用',
            'items': [{
                'material_id': material_id,
                'batch_no': 'BATCH-OUT-001',
                'actual_quantity': 50,
                'requested_quantity': 50
            }]
        })
        self.assertEqual(resp.status_code, 201)

    def test_out_order_detail_pagination_by_items(self):
        """出库台账按items分页，一个订单跨页"""
        # 先创建供应商
        resp = self.client.post('/api/suppliers', json={
            'name': '测试供应商-出分页',
            'contact': '测试',
            'phone': '13800138002'
        })
        supplier_id = resp.get_json()['id']

        # 创建10个物料
        material_ids = []
        for i in range(10):
            resp = self.client.post('/api/materials', json={
                'name': f'出库分页物料-{i}',
                'code': f'TEST-OUT-PAGE-{i:02d}',
                'unit': '个',
                'category_code': '0101'
            })
            material_ids.append(resp.get_json()['id'])

        # 创建入库单 with 10 items（审核通过）
        items = [
            {
                'material_id': material_ids[i],
                'batch_no': f'BATCH-OUT-PAGE-{i:02d}',
                'quantity': 100 + i,
                'unit_price': 10.0
            }
            for i in range(10)
        ]
        resp = self.client.post('/api/in-orders', json={
            'supplier_id': supplier_id,
            'operator_id': 1,
            'receiver': '出库分页测试',
            'items': items
        })
        in_order_id = resp.get_json()['id']
        resp = self.client.post(f'/api/in-orders/{in_order_id}/approve')
        self.assertEqual(resp.status_code, 200)

        # 创建出库单 with 10 items
        out_items = [
            {
                'material_id': material_ids[i],
                'batch_no': f'BATCH-OUT-PAGE-{i:02d}',
                'actual_quantity': 5 + i,
                'requested_quantity': 5 + i
            }
            for i in range(10)
        ]
        resp = self.client.post('/api/out-orders', json={
            'department': '出库分页测试部门',
            'receiver': '出库分页测试',
            'receiver_date': '2026-04-18',
            'operator_id': 1,
            'purpose': '出库分页测试用',
            'items': out_items
        })
        self.assertEqual(resp.status_code, 201)

        # 查询 page 1, per_page=5
        resp = self.client.get('/api/out-orders/detail?page=1&per_page=5')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()

        page1_item_count = sum(len(o['items']) for o in data['items'])
        self.assertEqual(page1_item_count, 5)

        # 查询 page 2
        resp = self.client.get('/api/out-orders/detail?page=2&per_page=5')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()

        page2_item_count = sum(len(o['items']) for o in data['items'])
        self.assertEqual(page2_item_count, 5)


class TestReportAPI(TestBase):

    def setUp(self):
        self.client = app.test_client()
        self.client.post('/api/auth/login', json={
            'username': 'admin',
            'password': 'admin123'
        })

    def test_inventory_report(self):
        """库存汇总报表"""
        resp = self.client.get('/api/reports/inventory')
        self.assertEqual(resp.status_code, 200)

    def test_in_detail_report(self):
        """入库明细报表"""
        resp = self.client.get('/api/reports/in-detail?start_date=2026-04-01&end_date=2026-04-30')
        self.assertEqual(resp.status_code, 200)

    def test_out_detail_report(self):
        """出库明细报表"""
        resp = self.client.get('/api/reports/out-detail?start_date=2026-04-01&end_date=2026-04-30')
        self.assertEqual(resp.status_code, 200)


class TestEmployeeAPI(TestBase):

    def setUp(self):
        self.client = app.test_client()
        self.client.post('/api/auth/login', json={
            'username': 'admin',
            'password': 'admin123'
        })

    def test_get_employees(self):
        """获取员工列表"""
        resp = self.client.get('/api/employees')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('items', data)


if __name__ == '__main__':
    unittest.main()
