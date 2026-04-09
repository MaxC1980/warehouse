import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db_connection, init_db
from models import User, Material, Supplier, InOrder, OutOrder, Inventory


class TestDatabase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

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


class TestMaterialService(unittest.TestCase):
    def setUp(self):
        init_db()

    def test_create_material(self):
        from services.material_service import MaterialService

        material = MaterialService.create_material(
            name='测试物料',
            spec='TEST-001',
            unit='个',
            category_code='0101',
            location='A-01-01',
            safety_stock=100
        )

        self.assertIsNotNone(material)
        self.assertEqual(material['name'], '测试物料')
        self.assertEqual(material['spec'], 'TEST-001')
        self.assertEqual(material['unit'], '个')


class TestSupplierService(unittest.TestCase):
    def setUp(self):
        init_db()

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


class TestOrderService(unittest.TestCase):
    def setUp(self):
        init_db()

    def test_create_in_order(self):
        from services.order_service import OrderService
        from services.material_service import MaterialService

        # Create material first
        material = MaterialService.create_material(name='测试物料', unit='个')
        material_id = material['id']

        # Create supplier
        from services.supplier_service import SupplierService
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


class TestInventoryService(unittest.TestCase):
    def setUp(self):
        init_db()

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


if __name__ == '__main__':
    unittest.main()
