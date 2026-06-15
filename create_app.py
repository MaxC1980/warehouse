import logging
from flask import Flask, jsonify, request, session
from werkzeug.exceptions import HTTPException
from database import init_db

logger = logging.getLogger(__name__)


def _is_api_request():
    """判断是否 API 请求: /api/* 路径或带 JSON Content-Type"""
    return request.path.startswith('/api/') or request.is_json


def create_app(config_class):
    app = Flask(__name__)
    app.config.from_object(config_class)

    init_db()

    # Register blueprints
    from routes.auth import auth_bp
    from routes.material import material_bp
    from routes.supplier import supplier_bp
    from routes.inventory import inventory_bp
    from routes.in_order import in_order_bp
    from routes.out_order import out_order_bp
    from routes.report import report_bp
    from routes.excel_import import import_bp
    from routes.return_order import return_order_bp
    from routes.employee import employee_bp
    from routes.admin import admin_bp, admin_page_bp
    from routes.pages import pages_bp

    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(admin_bp, url_prefix='/api')
    app.register_blueprint(admin_page_bp)
    app.register_blueprint(material_bp, url_prefix='/api')
    app.register_blueprint(supplier_bp, url_prefix='/api')
    app.register_blueprint(inventory_bp, url_prefix='/api')
    app.register_blueprint(in_order_bp, url_prefix='/api')
    app.register_blueprint(out_order_bp, url_prefix='/api')
    app.register_blueprint(report_bp, url_prefix='/api')
    app.register_blueprint(import_bp, url_prefix='/api')
    app.register_blueprint(return_order_bp, url_prefix='/api')
    app.register_blueprint(employee_bp, url_prefix='/api')
    app.register_blueprint(pages_bp)

    @app.before_request
    def require_login_for_api():
        if request.path.startswith('/api/') and request.path != '/api/auth/login':
            if 'user_id' not in session:
                return jsonify({'error': 'Unauthorized'}), 401
            if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
                if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
                    return jsonify({'error': 'Invalid request'}), 403

    @app.before_request
    def check_page_permission():
        from utils.page_permissions import PAGE_ENDPOINT_PERMISSIONS
        if request.path.startswith('/api/') or request.path in ('/login', '/'):
            return
        if 'user_id' not in session:
            return
        required = PAGE_ENDPOINT_PERMISSIONS.get(request.endpoint)
        if not required:
            return
        perms = set(tuple(p) for p in session.get('permissions', []))
        if required not in perms:
            return '无权限访问', 403

    @app.errorhandler(404)
    def handle_404(e):
        if _is_api_request():
            return jsonify({'error': '资源不存在'}), 404
        return '页面不存在', 404

    @app.errorhandler(500)
    def handle_500(e):
        logger.exception('500 错误')
        if _is_api_request():
            return jsonify({'error': '服务器内部错误'}), 500
        return '服务器内部错误', 500

    @app.errorhandler(Exception)
    def handle_exception(e):
        # 跳过 HTTPException (404/405 等, 走 Flask 默认)
        if isinstance(e, HTTPException):
            return e
        logger.exception('未捕获异常')
        if _is_api_request():
            return jsonify({'error': '服务器内部错误'}), 500
        return '服务器内部错误', 500

    @app.context_processor
    def inject_permissions():
        """将用户权限注入所有模板"""
        if 'user_id' in session:
            perms = [tuple(p) for p in session.get('permissions', [])]
            perm_set = set(perms)
            return {
                'user_permissions': perms,
                'has_perm': lambda m, a: (m, a) in perm_set
            }
        return {'user_permissions': [], 'has_perm': lambda m, a: False}

    @app.context_processor
    def inject_version():
        """将版本信息注入所有模板"""
        from utils.version import get_version_info
        return {'app_version': get_version_info()}

    return app
