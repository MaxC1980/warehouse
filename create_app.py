from flask import Flask, jsonify, request, session, redirect, url_for, render_template
from functools import wraps
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

    # Login required decorator
    def login_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                if request.is_json:
                    return jsonify({'error': 'Unauthorized'}), 401
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function

    # 页面权限映射：endpoint → (module, action)
    PAGE_ENDPOINT_PERMISSIONS = {
        'dashboard': ('dashboard', 'view'),
        'materials': ('material', 'view'),
        'material_new': ('material', 'edit'),
        'material_edit': ('material', 'edit'),
        'inventory': ('inventory', 'view'),
        'in_orders': ('in_order', 'view'),
        'in_order_new': ('in_order', 'edit'),
        'in_order_edit': ('in_order', 'edit'),
        'in_order_detail': ('in_order', 'view'),
        'in_order_details': ('in_order', 'view'),
        'out_orders': ('out_order', 'view'),
        'out_order_new': ('out_order', 'edit'),
        'out_order_edit': ('out_order', 'edit'),
        'out_order_detail': ('out_order', 'view'),
        'out_order_print': ('out_order', 'view'),
        'out_order_details': ('out_order', 'view'),
        'suppliers': ('supplier', 'view'),
        'supplier_new': ('supplier', 'edit'),
        'supplier_edit': ('supplier', 'edit'),
        'employees': ('employee', 'view'),
        'employee_new': ('employee', 'edit'),
        'employee_edit': ('employee', 'edit'),
        'report_inventory': ('report_inventory', 'view'),
        'report_in_detail': ('report_in_detail', 'view'),
        'report_out_detail': ('report_out_detail', 'view'),
        'report_summary': ('report_summary', 'view'),
        'report_stock_flow': ('report_stock_flow', 'view'),
        'category_major': ('category_major', 'view'),
        'category_major_new': ('category_major', 'edit'),
        'category_major_edit': ('category_major', 'edit'),
        'category_minor': ('category_minor', 'view'),
        'category_minor_new': ('category_minor', 'edit'),
        'category_minor_edit': ('category_minor', 'edit'),
        'return_orders': ('return_order', 'view'),
        'return_order_new': ('return_order', 'edit'),
        'return_order_edit': ('return_order', 'edit'),
        'return_order_detail': ('return_order', 'view'),
        'return_order_details': ('return_order', 'view'),
        'weight_records': ('weight_record', 'view'),
        'roles_page': ('admin_role', 'manage'),
        'users_page': ('admin_user', 'manage'),
    }

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

    # Page routes
    @app.route('/')
    def index():
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return redirect(url_for('dashboard'))

    @app.route('/login')
    def login():
        if 'user_id' in session:
            return redirect(url_for('dashboard'))
        return render_template('login.html')

    @app.route('/dashboard', strict_slashes=False)
    @login_required
    def dashboard():
        return render_template('dashboard.html')

    @app.route('/materials')
    @login_required
    def materials():
        return render_template('material_list.html')

    @app.route('/materials/new')
    @login_required
    def material_new():
        return render_template('material_form.html')

    @app.route('/materials/<int:material_id>/edit')
    @login_required
    def material_edit(material_id):
        return render_template('material_form.html', material_id=material_id)

    @app.route('/inventory')
    @login_required
    def inventory():
        return render_template('inventory_list.html')

    @app.route('/in-orders')
    @login_required
    def in_orders():
        return render_template('in_order_list.html')

    @app.route('/in-orders/new')
    @login_required
    def in_order_new():
        return render_template('in_order_form.html')

    @app.route('/in-orders/<int:order_id>/edit')
    @login_required
    def in_order_edit(order_id):
        return render_template('in_order_form.html', order_id=order_id)

    @app.route('/in-orders/<int:order_id>/detail')
    @login_required
    def in_order_detail(order_id):
        from services.order_service import OrderService
        order = OrderService.get_in_order_by_id(order_id)
        if not order:
            return '订单不存在', 404
        return render_template('in_order_detail.html', order=order)

    @app.route('/in-order-details')
    @login_required
    def in_order_details():
        return render_template('in_order_detail_list.html')

    @app.route('/out-orders')
    @login_required
    def out_orders():
        return render_template('out_order_list.html')

    @app.route('/out-orders/new')
    @login_required
    def out_order_new():
        return render_template('out_order_form.html')

    @app.route('/out-orders/<int:order_id>/edit')
    @login_required
    def out_order_edit(order_id):
        return render_template('out_order_form.html', order_id=order_id)

    @app.route('/out-orders/<int:order_id>/detail')
    @login_required
    def out_order_detail(order_id):
        from services.order_service import OrderService
        order = OrderService.get_out_order_by_id(order_id)
        if not order:
            return '订单不存在', 404
        related_returns, _ = OrderService.get_return_orders_by_out_order(order_id)
        return render_template('out_order_detail.html', order=order, related_returns=related_returns)

    @app.route('/out-orders/<int:order_id>/print')
    @login_required
    def out_order_print(order_id):
        from services.order_service import OrderService
        order = OrderService.get_out_order_by_id(order_id)
        if not order:
            return '订单不存在', 404
        return render_template('out_order_print.html', order=order)

    @app.route('/out-order-details')
    @login_required
    def out_order_details():
        return render_template('out_order_detail_list.html')

    @app.route('/suppliers')
    @login_required
    def suppliers():
        return render_template('supplier_list.html')

    @app.route('/suppliers/new')
    @login_required
    def supplier_new():
        return render_template('supplier_form.html')

    @app.route('/suppliers/<int:supplier_id>/edit')
    @login_required
    def supplier_edit(supplier_id):
        return render_template('supplier_form.html', supplier_id=supplier_id)

    @app.route('/employees')
    @login_required
    def employees():
        return render_template('employee_list.html')

    @app.route('/employees/new')
    @login_required
    def employee_new():
        return render_template('employee_form.html')

    @app.route('/employees/<int:employee_id>/edit')
    @login_required
    def employee_edit(employee_id):
        return render_template('employee_form.html', employee_id=employee_id)

    @app.route('/reports/inventory')
    @login_required
    def report_inventory():
        return render_template('report_inventory.html')

    @app.route('/reports/in-detail')
    @login_required
    def report_in_detail():
        return render_template('report_in_detail.html')

    @app.route('/reports/out-detail')
    @login_required
    def report_out_detail():
        return render_template('report_out_detail.html')

    @app.route('/reports/summary')
    @login_required
    def report_summary():
        return render_template('report_summary.html')

    @app.route('/reports/stock-flow')
    @login_required
    def report_stock_flow():
        return render_template('report_stock_flow.html')

    @app.route('/category-major')
    @login_required
    def category_major():
        return render_template('category_major_list.html')

    @app.route('/category-major/new')
    @login_required
    def category_major_new():
        return render_template('category_major_form.html')

    @app.route('/category-major/<int:category_id>/edit')
    @login_required
    def category_major_edit(category_id):
        return render_template('category_major_form.html', category_id=category_id)

    @app.route('/category-minor')
    @login_required
    def category_minor():
        return render_template('category_minor_list.html')

    @app.route('/category-minor/new')
    @login_required
    def category_minor_new():
        return render_template('category_minor_form.html')

    @app.route('/category-minor/<int:category_id>/edit')
    @login_required
    def category_minor_edit(category_id):
        return render_template('category_minor_form.html', category_id=category_id)

    @app.route('/return-orders')
    @login_required
    def return_orders():
        return render_template('return_order_list.html')

    @app.route('/return-orders/new')
    @login_required
    def return_order_new():
        return render_template('return_order_form.html')

    @app.route('/return-orders/<int:order_id>/edit')
    @login_required
    def return_order_edit(order_id):
        return render_template('return_order_form.html', order_id=order_id)

    @app.route('/return-orders/<int:order_id>/detail')
    @login_required
    def return_order_detail(order_id):
        from services.order_service import OrderService
        order = OrderService.get_return_order_by_id(order_id)
        if not order:
            return '订单不存在', 404
        return render_template('return_order_detail.html', order=order)

    @app.route('/return-order-details')
    @login_required
    def return_order_details():
        return render_template('return_order_detail_list.html')

    @app.route('/weight-records')
    @login_required
    def weight_records():
        return render_template('weight_record_list.html')

    return app
