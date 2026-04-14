import unittest
import sys
import os
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from database import get_db_connection, init_db


TEST_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'db', 'test')


def get_test_db_path():
    os.makedirs(TEST_DB_DIR, exist_ok=True)
    return os.path.join(TEST_DB_DIR, 'test_warehouse.db')


class TestBase(unittest.TestCase):
    """测试基类，每个测试使用独立数据库"""

    def setUp(self):
        self.old_db_path = Config.DATABASE_PATH
        self.test_db_path = get_test_db_path()
        Config.DATABASE_PATH = self.test_db_path
        init_db()

    def tearDown(self):
        Config.DATABASE_PATH = self.old_db_path
        # 关闭所有连接后删除测试数据库
        if os.path.exists(self.test_db_path):
            try:
                os.remove(self.test_db_path)
            except PermissionError:
                pass  # 如果文件被占用，下一次测试会覆盖


class TestDatabase(TestBase):

    def test_db_connection(self):
        conn = get_db_connection()
        self.assertIsNotNone(conn)
        conn.close()

    def test_user_table_exists(self):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user'")
        result = cursor.fetchone()
        self.assertIsNotNone(result)
        conn.close()

    def test_default_admin_user(self):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user WHERE username='admin'")
        user = cursor.fetchone()
        self.assertIsNotNone(user)
        self.assertEqual(user['username'], 'admin')
        conn.close()


class TestMaterialService(TestBase):

    def test_create_material(self):
        from services.material_service import MaterialService

        material = MaterialService.create_material(
            name='测试物料',
            spec='TEST-001',
            unit='个',
            category_code='0101'
        )

        self.assertIsNotNone(material)
        self.assertEqual(material['name'], '测试物料')
        self.assertEqual(material['spec'], 'TEST-001')
        self.assertEqual(material['unit'], '个')


class TestSupplierService(TestBase):

    def test_create_supplier(self):
        from services.supplier_service import SupplierService

        supplier = SupplierService.create_supplier(
            name='测试供应商',
            contact='张三',
            phone='13800138000',
            address='测试地址'
        )

        self.assertIsNotNone(supplier)
        self.assertEqual(supplier['name'], '测试供应商')
        self.assertEqual(supplier['contact'], '张三')


class TestOrderService(TestBase):

    def test_create_in_order(self):
        from services.order_service import OrderService
        from services.material_service import MaterialService
        from services.supplier_service import SupplierService

        # Create material first
        material = MaterialService.create_material(name='测试物料', unit='个')
        material_id = material['id']

        # Create supplier
        supplier = SupplierService.create_supplier(name='测试供应商')
        supplier_id = supplier['id']

        # Create in order
        order = OrderService.create_in_order(
            supplier_id=supplier_id,
            operator_id=1,
            remark='测试入库',
            items=[{
                'material_id': material_id,
                'batch_no': 'BATCH001',
                'quantity': 100,
                'unit_price': 10.0
            }]
        )

        self.assertIsNotNone(order)
        self.assertEqual(order['remark'], '测试入库')
        self.assertEqual(len(order['items']), 1)
        self.assertEqual(order['items'][0]['quantity'], 100)

    def test_approve_in_order_increases_inventory(self):
        """入库审核后库存应该增加"""
        from services.order_service import OrderService
        from services.material_service import MaterialService
        from services.supplier_service import SupplierService
        from services.inventory_service import InventoryService

        # 准备物料和供应商
        material = MaterialService.create_material(name='测试物料', unit='个')
        material_id = material['id']
        supplier = SupplierService.create_supplier(name='测试供应商')
        supplier_id = supplier['id']

        # 创建入库单
        order = OrderService.create_in_order(
            supplier_id=supplier_id,
            operator_id=1,
            items=[{
                'material_id': material_id,
                'batch_no': 'BATCH001',
                'quantity': 100,
                'unit_price': 10.0
            }]
        )
        order_id = order['id']

        # 审核前库存不存在（为None）
        inv = InventoryService.get_inventory_by_material(material_id)
        self.assertIsNone(inv)

        # 审核入库单
        result = OrderService.approve_in_order(order_id, approved_by=1)
        self.assertIsNotNone(result)

        # 审核后库存存在且数量为100
        inv = InventoryService.get_inventory_by_material(material_id)
        self.assertIsNotNone(inv)
        self.assertEqual(inv['quantity'], 100)

    def test_approve_in_order_without_items_fails(self):
        """入库单没有明细应该审核失败"""
        from services.order_service import OrderService
        from services.supplier_service import SupplierService

        supplier = SupplierService.create_supplier(name='测试供应商')

        # 创建空明细入库单
        order = OrderService.create_in_order(
            supplier_id=supplier['id'],
            operator_id=1,
            items=[]
        )

        result = OrderService.approve_in_order(order['id'], approved_by=1)
        self.assertIsNone(result)

    def test_approve_out_order_decreases_inventory(self):
        """出库审核后库存应该扣减"""
        from services.order_service import OrderService
        from services.material_service import MaterialService
        from services.supplier_service import SupplierService
        from services.inventory_service import InventoryService

        # 1. 先入库创建库存
        material = MaterialService.create_material(name='测试物料A', unit='个')
        supplier = SupplierService.create_supplier(name='测试供应商')

        in_order = OrderService.create_in_order(
            supplier_id=supplier['id'],
            operator_id=1,
            items=[{
                'material_id': material['id'],
                'batch_no': 'BATCH-A001',
                'quantity': 100,
                'unit_price': 10.0
            }]
        )
        OrderService.approve_in_order(in_order['id'], approved_by=1)

        # 验证入库后库存
        inv = InventoryService.get_inventory_by_material(material['id'])
        self.assertEqual(inv['quantity'], 100)

        # 2. 创建出库单
        out_order = OrderService.create_out_order(
            department='测试部门',
            receiver='张三',
            receiver_date='2026-04-14',
            operator_id=1,
            items=[{
                'material_id': material['id'],
                'batch_no': 'BATCH-A001',
                'actual_quantity': 30,
                'requested_quantity': 30
            }]
        )

        # 3. 审核出库
        result = OrderService.approve_out_order(out_order['id'], approved_by=1)
        self.assertIsNotNone(result)

        # 4. 验证库存扣减
        inv = InventoryService.get_inventory_by_material(material['id'])
        self.assertEqual(inv['quantity'], 70)


class TestInventoryService(TestBase):

    def test_update_inventory(self):
        from services.material_service import MaterialService
        from services.inventory_service import InventoryService

        # Create material
        material = MaterialService.create_material(name='测试物料', unit='个')
        material_id = material['id']

        # Update inventory
        result = InventoryService.update_inventory(
            material_id=material_id,
            quantity_change=100,
            batch_no='BATCH001'
        )

        self.assertTrue(result)

        # Check inventory
        inventory = InventoryService.get_inventory_by_material(material_id)
        self.assertIsNotNone(inventory)
        self.assertEqual(inventory['quantity'], 100)


class TestReusableMaterial(TestBase):
    """可回用物料出库审核测试"""

    def test_approve_out_order_for_reusable_material(self):
        """可回用物料出库审核不扣库存，记录毛重"""
        from services.order_service import OrderService
        from services.material_service import MaterialService
        from services.supplier_service import SupplierService
        from services.inventory_service import InventoryService

        # 创建可回用物料（名称含"胶水"会自动识别为可回用）
        material = MaterialService.create_material(name='测试胶水', unit='kg', is_reusable=1)
        material_id = material['id']

        # 先入库创建库存
        supplier = SupplierService.create_supplier(name='测试供应商')
        in_order = OrderService.create_in_order(
            supplier_id=supplier['id'],
            operator_id=1,
            items=[{
                'material_id': material_id,
                'batch_no': 'BATCH-GLUE-001',
                'quantity': 50,
                'unit_price': 100.0
            }]
        )
        OrderService.approve_in_order(in_order['id'], approved_by=1)

        # 验证入库后库存
        inv = InventoryService.get_inventory_by_material(material_id)
        self.assertEqual(inv['quantity'], 50)

        # 创建出库单，传入毛重
        out_order = OrderService.create_out_order(
            department='生产车间',
            receiver='张三',
            receiver_date='2026-04-14',
            operator_id=1,
            items=[{
                'material_id': material_id,
                'batch_no': 'BATCH-GLUE-001',
                'quantity': 50,
                'actual_quantity': 30,
                'requested_quantity': 30,
                'initial_gross_weight': 35.5
            }]
        )

        # 审核出库（带毛重数据）
        result = OrderService.approve_out_order(
            out_order['id'],
            approved_by=1,
            weight_data=[{'out_order_item_id': out_order['items'][0]['id'], 'initial_gross_weight': 35.5}]
        )
        self.assertIsNotNone(result)

        # 可回用物料审核后库存不变（不扣减）
        inv = InventoryService.get_inventory_by_material(material_id)
        self.assertEqual(inv['quantity'], 50)

        # 检查reusable_material_weight表有记录
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM reusable_material_weight WHERE material_id = ?", (material_id,))
        weight_record = cursor.fetchone()
        conn.close()
        self.assertIsNotNone(weight_record)
        self.assertEqual(weight_record['initial_gross_weight'], 35.5)
        self.assertEqual(weight_record['status'], 'checked_out')


class TestReturnOrder(TestBase):
    """退库审核测试"""

    def test_return_order_approve_restores_inventory(self):
        """退库审核后回冲库存"""
        from services.order_service import OrderService
        from services.material_service import MaterialService
        from services.supplier_service import SupplierService
        from services.inventory_service import InventoryService

        # 1. 创建普通物料并入库
        material = MaterialService.create_material(name='测试物料B', unit='个')
        supplier = SupplierService.create_supplier(name='测试供应商B')

        in_order = OrderService.create_in_order(
            supplier_id=supplier['id'],
            operator_id=1,
            items=[{
                'material_id': material['id'],
                'batch_no': 'BATCH-B001',
                'quantity': 100,
                'unit_price': 20.0
            }]
        )
        OrderService.approve_in_order(in_order['id'], approved_by=1)

        inv = InventoryService.get_inventory_by_material(material['id'])
        self.assertEqual(inv['quantity'], 100)

        # 2. 创建并审核出库单
        out_order = OrderService.create_out_order(
            department='部门B',
            receiver='李四',
            receiver_date='2026-04-14',
            operator_id=1,
            items=[{
                'material_id': material['id'],
                'batch_no': 'BATCH-B001',
                'actual_quantity': 80,
                'requested_quantity': 80
            }]
        )
        OrderService.approve_out_order(out_order['id'], approved_by=1)

        # 出库后库存为20
        inv = InventoryService.get_inventory_by_material(material['id'])
        self.assertEqual(inv['quantity'], 20)

        # 3. 创建退库单
        return_order = OrderService.create_return_order(
            related_out_order_id=out_order['id'],
            department='部门B',
            receiver='李四',
            receiver_date='2026-04-14',
            operator_id=1,
            items=[{
                'out_order_item_id': out_order['items'][0]['id'],
                'material_id': material['id'],
                'batch_no': 'BATCH-B001',
                'return_quantity': 30
            }]
        )

        # 4. 审核退库单
        result = OrderService.approve_return_order(return_order['id'], approved_by=1)
        self.assertIsNotNone(result)

        # 退库后库存回冲为50（20 + 30）
        inv = InventoryService.get_inventory_by_material(material['id'])
        self.assertEqual(inv['quantity'], 50)

    def test_approve_out_order_insufficient_inventory(self):
        """出库审核时库存不足应报错"""
        from services.order_service import OrderService
        from services.material_service import MaterialService
        from services.supplier_service import SupplierService

        # 创建物料和供应商
        material = MaterialService.create_material(name='测试物料C', unit='个')
        supplier = SupplierService.create_supplier(name='测试供应商C')

        # 入库50个
        in_order = OrderService.create_in_order(
            supplier_id=supplier['id'],
            operator_id=1,
            items=[{
                'material_id': material['id'],
                'batch_no': 'BATCH-C001',
                'quantity': 50,
                'unit_price': 10.0
            }]
        )
        OrderService.approve_in_order(in_order['id'], approved_by=1)

        # 创建出库单，要出100个（库存只有50）
        out_order = OrderService.create_out_order(
            department='部门C',
            receiver='王五',
            receiver_date='2026-04-14',
            operator_id=1,
            items=[{
                'material_id': material['id'],
                'batch_no': 'BATCH-C001',
                'actual_quantity': 100,  # 超过库存
                'requested_quantity': 100
            }]
        )

        # 审核应失败并抛出异常
        with self.assertRaises(Exception) as context:
            OrderService.approve_out_order(out_order['id'], approved_by=1)
        self.assertIn('库存不足', str(context.exception))

    def test_approve_return_order_duplicate_prevention(self):
        """同一出库单不能重复审核退库"""
        from services.order_service import OrderService
        from services.material_service import MaterialService
        from services.supplier_service import SupplierService

        # 1. 创建物料并完成一次出库
        material = MaterialService.create_material(name='测试物料D', unit='个')
        supplier = SupplierService.create_supplier(name='测试供应商D')

        in_order = OrderService.create_in_order(
            supplier_id=supplier['id'],
            operator_id=1,
            items=[{
                'material_id': material['id'],
                'batch_no': 'BATCH-D001',
                'quantity': 100,
                'unit_price': 10.0
            }]
        )
        OrderService.approve_in_order(in_order['id'], approved_by=1)

        out_order = OrderService.create_out_order(
            department='部门D',
            receiver='赵六',
            receiver_date='2026-04-14',
            operator_id=1,
            items=[{
                'material_id': material['id'],
                'batch_no': 'BATCH-D001',
                'actual_quantity': 100,
                'requested_quantity': 100
            }]
        )
        out_order_id = out_order['id']
        out_order_item_id = out_order['items'][0]['id']
        OrderService.approve_out_order(out_order_id, approved_by=1)

        # 2. 创建并审核第一个退库单
        return_order1 = OrderService.create_return_order(
            related_out_order_id=out_order_id,
            department='部门D',
            receiver='赵六',
            receiver_date='2026-04-14',
            operator_id=1,
            items=[{
                'out_order_item_id': out_order_item_id,
                'material_id': material['id'],
                'batch_no': 'BATCH-D001',
                'return_quantity': 50
            }]
        )
        OrderService.approve_return_order(return_order1['id'], approved_by=1)

        # 3. 尝试再创建一个退库单关联同一出库单 - 创建时就应失败
        with self.assertRaises(Exception) as context:
            OrderService.create_return_order(
                related_out_order_id=out_order_id,
                department='部门D',
                receiver='赵六',
                receiver_date='2026-04-14',
                operator_id=1,
                items=[{
                    'out_order_item_id': out_order_item_id,
                    'material_id': material['id'],
                    'batch_no': 'BATCH-D001',
                    'return_quantity': 30
                }]
            )
        self.assertIn('已有审核通过的退库单', str(context.exception))


if __name__ == '__main__':
    unittest.main()
