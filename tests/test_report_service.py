"""ReportService 单元测试

直接调 Service 方法, 不走 HTTP。验证 SQL 路径不崩 + 返回结构。
"""
import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from config import Config
from database import init_db
import tempfile
import shutil

from services.report_service import ReportService


class TestConfig(Config):
    TEST_DB_DIR = tempfile.mkdtemp()
    DATABASE_PATH = os.path.join(TEST_DB_DIR, 'test_report.db')


class TestReportService(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.old_db_path = Config.DATABASE_PATH
        Config.DATABASE_PATH = TestConfig.DATABASE_PATH
        init_db()

    @classmethod
    def tearDownClass(cls):
        Config.DATABASE_PATH = cls.old_db_path
        if os.path.exists(TestConfig.TEST_DB_DIR):
            shutil.rmtree(TestConfig.TEST_DB_DIR)

    # --- get_inventory_report ---

    def test_inventory_report_empty(self):
        """空库: 返回空列表 + 0 total"""
        items, total = ReportService.get_inventory_report()
        self.assertEqual(items, [])
        self.assertEqual(total, 0)

    def test_inventory_report_with_keyword(self):
        """keyword 路径: 走 build_like_clause (防 LIKE ESCAPE 回归)"""
        items, total = ReportService.get_inventory_report(keyword='钢')
        self.assertIsInstance(items, list)
        self.assertIsInstance(total, int)

    def test_inventory_report_with_categories(self):
        """major_category / minor_category 前缀匹配"""
        items, total = ReportService.get_inventory_report(major_category='01', minor_category='0103')
        self.assertIsInstance(items, list)

    # --- get_in_detail_report ---

    def test_in_detail_report_empty(self):
        """入库明细空库"""
        items, total = ReportService.get_in_detail_report()
        self.assertEqual(items, [])
        self.assertEqual(total, 0)

    def test_in_detail_report_with_date_range(self):
        items, total = ReportService.get_in_detail_report(date_from='2026-01-01', date_to='2026-12-31')
        self.assertIsInstance(items, list)
        self.assertIsInstance(total, int)

    # --- get_out_detail_report ---

    def test_out_detail_report_empty(self):
        items, total = ReportService.get_out_detail_report()
        self.assertEqual(items, [])
        self.assertEqual(total, 0)

    def test_out_detail_report_with_date_range(self):
        items, total = ReportService.get_out_detail_report(date_from='2026-01-01', date_to='2026-12-31')
        self.assertIsInstance(items, list)
        self.assertIsInstance(total, int)

    # --- get_summary_report (含 strftime 路径, 防 INSTR/SUBSTR 回归) ---

    def test_summary_report_empty(self):
        """空库: 验证 strftime 路径不崩"""
        result = ReportService.get_summary_report()
        self.assertIsInstance(result, dict)

    def test_summary_report_with_date_range(self):
        result = ReportService.get_summary_report(date_from='2026-01-01', date_to='2026-12-31')
        self.assertIsInstance(result, dict)

    # --- get_stock_flow_report ---

    def test_stock_flow_report_empty(self):
        items, total = ReportService.get_stock_flow_report(date_from='2026-01-01', date_to='2026-12-31')
        self.assertEqual(items, [])
        self.assertEqual(total, 0)

    def test_stock_flow_report_with_keyword(self):
        """keyword 路径: 走 build_like_clause"""
        items, total = ReportService.get_stock_flow_report(
            date_from='2026-01-01', date_to='2026-12-31', keyword='钢',
        )
        self.assertIsInstance(items, list)
        self.assertIsInstance(total, int)

    def test_stock_flow_report_with_filters(self):
        items, total = ReportService.get_stock_flow_report(
            date_from='2026-01-01', date_to='2026-12-31',
            major_category='01', hide_zero=True, hide_no_change=True,
        )
        self.assertIsInstance(items, list)

    # --- get_stock_flow_detail ---

    def test_stock_flow_detail_empty(self):
        items = ReportService.get_stock_flow_detail(
            material_id=1, date_from='2026-01-01', date_to='2026-12-31',
        )
        self.assertEqual(items, [])

    def test_stock_flow_detail_requires_material_id(self):
        with self.assertRaises(ValueError):
            ReportService.get_stock_flow_detail(
                material_id=None, date_from='2026-01-01', date_to='2026-12-31',
            )

    def test_stock_flow_detail_requires_dates(self):
        with self.assertRaises(ValueError):
            ReportService.get_stock_flow_detail(material_id=1)

    def test_stock_flow_detail_running_balance(self):
        """实时库存 = 该物料操作当时的库存, 跨批次累计。

        同一入库单内 B1 入库 100 + B2 入库 50 (合并为一行 150)
        → 出库 30 → 退库 5, 每行实时库存依次 150 / 120 / 125。
        """
        from database import get_db_connection
        import time
        suffix = str(int(time.time() * 1000) % 1000000)

        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO material (code, name, unit) VALUES (?, ?, ?)",
                (f'FLOW{suffix}', 'flow test', 'kg')
            )
            mid = c.lastrowid

            c.execute(
                "INSERT INTO in_order (order_no, status, receiver, receiver_date, created_at)"
                " VALUES (?, 'approved', '张三', '2099-03-01', '2099-03-01 09:00:00')",
                (f'RK-T{suffix}',)
            )
            in_order_id = c.lastrowid
            c.execute(
                "INSERT INTO in_order_item (order_id, material_id, batch_no, quantity)"
                " VALUES (?, ?, 'B1', 100)", (in_order_id, mid)
            )
            c.execute(
                "INSERT INTO in_order_item (order_id, material_id, batch_no, quantity)"
                " VALUES (?, ?, 'B2', 50)", (in_order_id, mid)
            )

            c.execute(
                "INSERT INTO out_order (order_no, status, receiver, receiver_date, created_at)"
                " VALUES (?, 'approved', '李四', '2099-03-02', '2099-03-02 09:00:00')",
                (f'CK-T{suffix}',)
            )
            out_order_id = c.lastrowid
            c.execute(
                "INSERT INTO out_order_item (order_id, material_id, batch_no, actual_quantity)"
                " VALUES (?, ?, 'B1', 30)", (out_order_id, mid)
            )
            out_item_id = c.lastrowid

            c.execute(
                "INSERT INTO return_order (order_no, status, receiver, receiver_date, created_at)"
                " VALUES (?, 'approved', '王五', '2099-03-03', '2099-03-03 09:00:00')",
                (f'TK-T{suffix}',)
            )
            return_order_id = c.lastrowid
            c.execute(
                "INSERT INTO return_order_item"
                " (return_order_id, out_order_item_id, material_id, batch_no, quantity)"
                " VALUES (?, ?, ?, 'B1', 5)", (return_order_id, out_item_id, mid)
            )
            conn.commit()

        try:
            items = ReportService.get_stock_flow_detail(
                material_id=mid, date_from='2099-03-01', date_to='2099-03-31',
            )

            self.assertEqual([i['type'] for i in items], ['退库', '出库', '入库'])
            self.assertEqual([i['quantity'] for i in items], [5, 30, 150])
            self.assertEqual([i['current_stock'] for i in items], [125, 120, 150])
            self.assertNotIn('batch_no', items[0])
        finally:
            with get_db_connection() as conn:
                c = conn.cursor()
                c.execute("DELETE FROM return_order_item WHERE return_order_id = ?", (return_order_id,))
                c.execute("DELETE FROM return_order WHERE id = ?", (return_order_id,))
                c.execute("DELETE FROM out_order_item WHERE id = ?", (out_item_id,))
                c.execute("DELETE FROM out_order WHERE id = ?", (out_order_id,))
                c.execute("DELETE FROM in_order_item WHERE material_id = ?", (mid,))
                c.execute("DELETE FROM in_order WHERE order_no LIKE ?", (f'%-T{suffix}',))
                c.execute("DELETE FROM material WHERE id = ?", (mid,))
                conn.commit()


if __name__ == '__main__':
    unittest.main()