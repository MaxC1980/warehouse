"""AttachmentService 单元测试

直接调 Service, 不走 HTTP。覆盖: 扩展名白名单 / 魔数 / 大小 / 数量上限 /
保存-查询-删除 / 级联清理。使用临时库与临时附件目录。
"""
import io
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from werkzeug.datastructures import FileStorage

from app import app  # noqa: F401  确保应用工厂可导入
from config import Config
from database import init_db, get_db_connection
from services.attachment_service import AttachmentService

PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32
PDF = b'%PDF-1.4\n' + b'\x00' * 32
JPG = b'\xff\xd8\xff\xe0' + b'\x00' * 32


def make_file(filename, data):
    return FileStorage(stream=io.BytesIO(data), filename=filename)


class TestAttachmentService(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.old_db_path = Config.DATABASE_PATH
        cls.old_folder = Config.ATTACHMENT_FOLDER
        cls.tmp_dir = tempfile.mkdtemp()
        cls.tmp_files = tempfile.mkdtemp()
        Config.DATABASE_PATH = os.path.join(cls.tmp_dir, 'test_attachment.db')
        Config.ATTACHMENT_FOLDER = cls.tmp_files
        init_db()

    @classmethod
    def tearDownClass(cls):
        Config.DATABASE_PATH = cls.old_db_path
        Config.ATTACHMENT_FOLDER = cls.old_folder
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)
        shutil.rmtree(cls.tmp_files, ignore_errors=True)

    def tearDown(self):
        with get_db_connection() as conn:
            conn.execute("DELETE FROM attachment")
            conn.commit()

    # --- 校验 ---

    def test_reject_disallowed_extension(self):
        with self.assertRaises(ValueError) as ctx:
            AttachmentService.save_attachment('in_order', 1, make_file('a.exe', PNG))
        self.assertIn('只允许上传', str(ctx.exception))

    def test_reject_svg(self):
        """svg 可内嵌脚本, 不在白名单"""
        with self.assertRaises(ValueError):
            AttachmentService.save_attachment('in_order', 1, make_file('a.svg', b'<svg/>'))

    def test_reject_magic_mismatch(self):
        """扩展名是 png 但内容是 PDF"""
        with self.assertRaises(ValueError) as ctx:
            AttachmentService.save_attachment('in_order', 1, make_file('a.png', PDF))
        self.assertIn('不匹配', str(ctx.exception))

    def test_reject_empty_file(self):
        with self.assertRaises(ValueError) as ctx:
            AttachmentService.save_attachment('in_order', 1, make_file('a.png', b''))
        self.assertIn('空', str(ctx.exception))

    def test_reject_oversize(self):
        old = Config.ATTACHMENT_MAX_SIZE
        Config.ATTACHMENT_MAX_SIZE = 16
        try:
            with self.assertRaises(ValueError) as ctx:
                AttachmentService.save_attachment('in_order', 1, make_file('a.png', PNG))
            self.assertIn('不能超过', str(ctx.exception))
        finally:
            Config.ATTACHMENT_MAX_SIZE = old

    def test_reject_missing_file(self):
        with self.assertRaises(ValueError):
            AttachmentService.save_attachment('in_order', 1, make_file('', b''))

    # --- 保存/查询/删除 ---

    def test_save_and_get(self):
        result = AttachmentService.save_attachment(
            'in_order', 1, make_file('凭证.png', PNG), uploaded_by=None
        )
        items = AttachmentService.get_attachments('in_order', 1)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['file_name'], '凭证.png')
        self.assertEqual(items[0]['mime_type'], 'image/png')
        self.assertIsNone(items[0]['row_key'])

        detail = AttachmentService.get_attachment(result['id'])
        self.assertTrue(detail['stored_name'].endswith('.png'))
        # 文件名与磁盘名无关, 防目录穿越
        self.assertNotIn('凭证', detail['stored_name'])
        self.assertTrue(os.path.exists(os.path.join(Config.ATTACHMENT_FOLDER, detail['stored_name'])))

    def test_save_with_row_key(self):
        AttachmentService.save_attachment('in_order', 2, make_file('a.png', PNG), row_key='rk-1')
        AttachmentService.save_attachment('in_order', 2, make_file('b.pdf', PDF))
        items = AttachmentService.get_attachments('in_order', 2)
        self.assertEqual([i['row_key'] for i in items], [None, 'rk-1'])

    def test_delete_removes_file(self):
        result = AttachmentService.save_attachment('in_order', 3, make_file('a.png', PNG))
        stored = AttachmentService.get_attachment(result['id'])['stored_name']
        path = os.path.join(Config.ATTACHMENT_FOLDER, stored)
        self.assertTrue(os.path.exists(path))

        self.assertTrue(AttachmentService.delete_attachment(result['id']))
        self.assertFalse(os.path.exists(path))
        self.assertEqual(AttachmentService.get_attachments('in_order', 3), [])

    def test_delete_missing_returns_false(self):
        self.assertFalse(AttachmentService.delete_attachment(999999))

    def test_max_per_order(self):
        old = Config.ATTACHMENT_MAX_PER_ORDER
        Config.ATTACHMENT_MAX_PER_ORDER = 2
        try:
            for i in range(2):
                AttachmentService.save_attachment('in_order', 4, make_file(f'{i}.png', PNG))
            with self.assertRaises(ValueError) as ctx:
                AttachmentService.save_attachment('in_order', 4, make_file('c.png', PNG))
            self.assertIn('上限', str(ctx.exception))
        finally:
            Config.ATTACHMENT_MAX_PER_ORDER = old

    def test_max_per_item_is_separate(self):
        """主表附件与明细行附件的上限互不影响"""
        old_order, old_item = Config.ATTACHMENT_MAX_PER_ORDER, Config.ATTACHMENT_MAX_PER_ITEM
        Config.ATTACHMENT_MAX_PER_ORDER = 1
        Config.ATTACHMENT_MAX_PER_ITEM = 1
        try:
            AttachmentService.save_attachment('in_order', 5, make_file('m.png', PNG))
            AttachmentService.save_attachment('in_order', 5, make_file('i.png', PNG), row_key='rk-1')
            with self.assertRaises(ValueError):
                AttachmentService.save_attachment('in_order', 5, make_file('m2.png', PNG))
            with self.assertRaises(ValueError):
                AttachmentService.save_attachment('in_order', 5, make_file('i2.png', PNG), row_key='rk-1')
        finally:
            Config.ATTACHMENT_MAX_PER_ORDER = old_order
            Config.ATTACHMENT_MAX_PER_ITEM = old_item

    # --- 级联清理 ---

    def test_delete_by_biz_removes_records_and_files(self):
        r1 = AttachmentService.save_attachment('in_order', 6, make_file('a.png', PNG))
        AttachmentService.save_attachment('in_order', 6, make_file('b.pdf', PDF), row_key='rk-1')
        AttachmentService.save_attachment('in_order', 7, make_file('other.png', PNG))

        AttachmentService.delete_by_biz('in_order', 6)

        self.assertEqual(AttachmentService.get_attachments('in_order', 6), [])
        self.assertEqual(len(AttachmentService.get_attachments('in_order', 7)), 1)
        stored = AttachmentService.get_attachment(r1['id'])
        self.assertIsNone(stored)

    def test_delete_by_row_keys_removes_orphans(self):
        AttachmentService.save_attachment('in_order', 8, make_file('keep.png', PNG), row_key='rk-keep')
        AttachmentService.save_attachment('in_order', 8, make_file('drop.png', PNG), row_key='rk-drop')
        AttachmentService.save_attachment('in_order', 8, make_file('main.png', PNG))

        AttachmentService.delete_by_row_keys('in_order', 8, {'rk-keep'})

        items = AttachmentService.get_attachments('in_order', 8)
        self.assertEqual([i['row_key'] for i in items], [None, 'rk-keep'])


if __name__ == '__main__':
    unittest.main()
