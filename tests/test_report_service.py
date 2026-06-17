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


if __name__ == '__main__':
    unittest.main()