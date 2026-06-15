from flask import Flask, jsonify, request, session
from database import init_db


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

    return app
