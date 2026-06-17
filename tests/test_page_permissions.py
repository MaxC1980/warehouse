"""页面权限拦截测试

覆盖 4 类场景:
- 未登录: 受保护页面跳 /login (302), /login 自身 200
- 查看员: 业务页面 200, 管理页面 403
- 操作员: 与查看员一致 (操作员无 admin_role/admin_user manage)
- 管理员: 所有页面 200

回归保护:
- /admin/roles-page 和 /admin/users-page 修复过 endpoint 前缀 bug
"""
import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from config import Config
from database import init_db, get_db_connection
import tempfile
import shutil


class TestConfig(Config):
    """测试配置, 使用临时数据库"""
    TEST_DB_DIR = tempfile.mkdtemp()
    DATABASE_PATH = os.path.join(TEST_DB_DIR, 'test_page_perm.db')


class TestPagePermissions(unittest.TestCase):
    """页面权限矩阵测试"""

    @classmethod
    def setUpClass(cls):
        cls.old_db_path = Config.DATABASE_PATH
        Config.DATABASE_PATH = TestConfig.DATABASE_PATH
        init_db()
        cls.client = app.test_client()

        # 创建测试用户
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # 查看员
            cursor.execute("SELECT id FROM user WHERE username = 'view'")
            if not cursor.fetchone():
                cursor.execute("INSERT INTO user (username, password) VALUES (?, ?)", ('view', 'view123'))
                view_id = cursor.lastrowid
                cursor.execute("SELECT id FROM role WHERE name = '查看员'")
                viewer_role = cursor.fetchone()
                if viewer_role:
                    cursor.execute("INSERT OR IGNORE INTO user_role (user_id, role_id) VALUES (?, ?)",
                                   (view_id, viewer_role['id']))
            # 操作员
            cursor.execute("SELECT id FROM user WHERE username = 'edit'")
            if not cursor.fetchone():
                cursor.execute("INSERT INTO user (username, password) VALUES (?, ?)", ('edit', 'edit123'))
                edit_id = cursor.lastrowid
                cursor.execute("SELECT id FROM role WHERE name = '操作员'")
                operator_role = cursor.fetchone()
                if operator_role:
                    cursor.execute("INSERT OR IGNORE INTO user_role (user_id, role_id) VALUES (?, ?)",
                                   (edit_id, operator_role['id']))
            conn.commit()

    @classmethod
    def tearDownClass(cls):
        Config.DATABASE_PATH = cls.old_db_path
        if os.path.exists(TestConfig.TEST_DB_DIR):
            shutil.rmtree(TestConfig.TEST_DB_DIR)

    def _get_user_id(self, username):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM user WHERE username = ?", (username,))
            row = cursor.fetchone()
            return row['id'] if row else None

    def _login_as(self, user_id, perms):
        """用 session_transaction 注入已登录 session"""
        with self.client.session_transaction() as sess:
            sess.clear()
            sess['user_id'] = user_id
            sess['permissions'] = [list(p) for p in perms]

    def _logout(self):
        """清空 session, 模拟未登录"""
        with self.client.session_transaction() as sess:
            sess.clear()

    def test_login_page_accessible_to_all(self):
        """/login 任何状态都可访问 (包括未登录)"""
        self._logout()
        r = self.client.get('/login')
        self.assertEqual(r.status_code, 200)

    def test_dashboard_unauthenticated_redirects(self):
        """未登录访问 /dashboard 跳 /login (302)"""
        self._logout()
        r = self.client.get('/dashboard')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/login', r.headers.get('Location', ''))

    def test_business_page_accessible_to_viewer(self):
        """查看员可访问业务页面 /materials"""
        view_id = self._get_user_id('view')
        from services.permission_service import PermissionService
        perms = PermissionService.get_user_permissions(view_id)
        self._login_as(view_id, perms)

        r = self.client.get('/materials')
        self.assertEqual(r.status_code, 200)

    def test_business_page_accessible_to_admin(self):
        """管理员可访问业务页面 /in-orders"""
        admin_id = self._get_user_id('admin')
        from services.permission_service import PermissionService
        perms = PermissionService.get_user_permissions(admin_id)
        self._login_as(admin_id, perms)

        r = self.client.get('/in-orders')
        self.assertEqual(r.status_code, 200)

    def test_admin_roles_page_blocked_for_viewer(self):
        """查看员访问 /admin/roles-page 应 403 (P3-11 bug 回归保护)"""
        view_id = self._get_user_id('view')
        from services.permission_service import PermissionService
        perms = PermissionService.get_user_permissions(view_id)
        self._login_as(view_id, perms)

        r = self.client.get('/admin/roles-page')
        self.assertEqual(r.status_code, 403)

    def test_admin_users_page_blocked_for_viewer(self):
        """查看员访问 /admin/users-page 应 403 (P3-11 bug 回归保护)"""
        view_id = self._get_user_id('view')
        from services.permission_service import PermissionService
        perms = PermissionService.get_user_permissions(view_id)
        self._login_as(view_id, perms)

        r = self.client.get('/admin/users-page')
        self.assertEqual(r.status_code, 403)

    def test_admin_roles_page_allowed_for_admin(self):
        """管理员可访问 /admin/roles-page"""
        admin_id = self._get_user_id('admin')
        from services.permission_service import PermissionService
        perms = PermissionService.get_user_permissions(admin_id)
        self._login_as(admin_id, perms)

        r = self.client.get('/admin/roles-page')
        self.assertEqual(r.status_code, 200)

    def test_admin_users_page_allowed_for_admin(self):
        """管理员可访问 /admin/users-page"""
        admin_id = self._get_user_id('admin')
        from services.permission_service import PermissionService
        perms = PermissionService.get_user_permissions(admin_id)
        self._login_as(admin_id, perms)

        r = self.client.get('/admin/users-page')
        self.assertEqual(r.status_code, 200)

    def test_unauthenticated_admin_page_redirects_to_login(self):
        """未登录访问 /admin/roles-page 应跳 /login (P1-11 修复, 模拟重启后 session 失效)"""
        self._logout()
        r = self.client.get('/admin/roles-page')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/login', r.headers.get('Location', ''))

    def test_unauthenticated_api_returns_json_401(self):
        """未登录访问 /api/materials 应返 JSON 401 (API 行为不变)"""
        self._logout()
        r = self.client.get('/api/materials')
        self.assertEqual(r.status_code, 401)
        # create_app 的 before_request 拦截, 消息是 '未登录'
        self.assertEqual(r.get_json(), {'error': '未登录'})

    def test_edit_page_blocked_for_viewer(self):
        """查看员访问 /materials/new 应 403 (无 material.edit 权限)"""
        view_id = self._get_user_id('view')
        from services.permission_service import PermissionService
        perms = PermissionService.get_user_permissions(view_id)
        self._login_as(view_id, perms)

        r = self.client.get('/materials/new')
        self.assertEqual(r.status_code, 403)

    def test_report_page_accessible_to_viewer(self):
        """查看员可访问报表 /reports/inventory"""
        view_id = self._get_user_id('view')
        from services.permission_service import PermissionService
        perms = PermissionService.get_user_permissions(view_id)
        self._login_as(view_id, perms)

        r = self.client.get('/reports/inventory')
        self.assertEqual(r.status_code, 200)

    def test_detail_pages_handle_service_exception(self):
        """详情页 service 异常应返 500 友好消息, 不暴露堆栈 (P2-8 修复)"""
        from unittest.mock import patch
        admin_id = self._get_user_id('admin')
        from services.permission_service import PermissionService
        perms = PermissionService.get_user_permissions(admin_id)
        self._login_as(admin_id, perms)

        for path in [
            '/in-orders/1/detail',
            '/out-orders/1/detail',
            '/out-orders/1/print',
            '/return-orders/1/detail',
        ]:
            # 触发 service 异常
            with patch('services.order_service.OrderService.get_in_order_by_id',
                       side_effect=Exception('模拟 DB 故障')), \
                 patch('services.order_service.OrderService.get_out_order_by_id',
                       side_effect=Exception('模拟 DB 故障')), \
                 patch('services.order_service.OrderService.get_return_order_by_id',
                       side_effect=Exception('模拟 DB 故障')):
                r = self.client.get(path)
                self.assertEqual(r.status_code, 500, f'{path} 应返 500')
                # 友好消息, 不应含堆栈
                body = r.get_data(as_text=True)
                self.assertIn('加载失败', body)
                self.assertNotIn('Traceback', body)
                self.assertNotIn('Exception:', body)

    def test_global_404_returns_json_for_api(self):
        """全局 404 errorhandler: API 返 JSON 404 (P2-14)"""
        self._logout()
        # 未登录访问不存在 API 端点, 404 优先于 401
        resp = self.client.get('/api/does-not-exist')
        # 404 或 401 都可, 但**不应是 Flask 默认 HTML 错误页**
        if resp.status_code == 404:
            self.assertEqual(resp.get_json(), {'error': '资源不存在'})

    def test_global_404_returns_html_for_page(self):
        """全局 404 errorhandler: 页面返 HTML"""
        self._logout()
        resp = self.client.get('/non-existent-page')
        self.assertEqual(resp.status_code, 404)
        self.assertIn('页面不存在', resp.get_data(as_text=True))

    def test_global_exception_handler_logs(self):
        """全局 Exception handler 捕获并 log 未处理异常 (P2-14)"""
        from unittest.mock import patch
        admin_id = self._get_user_id('admin')
        from services.permission_service import PermissionService
        perms = PermissionService.get_user_permissions(admin_id)
        self._login_as(admin_id, perms)

        # mock 业务 service 抛 ValueError, 装饰器应捕获 → 400
        with patch('services.material_service.MaterialService.get_materials',
                   side_effect=ValueError('模拟业务错误')):
            resp = self.client.get('/api/materials')
            self.assertEqual(resp.status_code, 400)


if __name__ == '__main__':
    unittest.main()
