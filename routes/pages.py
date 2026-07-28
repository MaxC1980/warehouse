"""页面路由: 渲染 HTML 模板, 不处理业务数据 (业务由对应 API Blueprint 处理)"""
import logging
from flask import Blueprint, render_template, redirect, url_for, session
from services.order_service import OrderService
from utils.decorators import login_required

logger = logging.getLogger(__name__)

pages_bp = Blueprint('pages', __name__)


@pages_bp.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('pages.login'))
    return redirect(url_for('pages.dashboard'))


@pages_bp.route('/login')
def login():
    if 'user_id' in session:
        return redirect(url_for('pages.dashboard'))
    return render_template('login.html')


@pages_bp.route('/dashboard', strict_slashes=False)
@login_required
def dashboard():
    return render_template('dashboard.html')


# 物料
@pages_bp.route('/materials')
@login_required
def materials():
    return render_template('material_list.html')

@pages_bp.route('/materials/new')
@login_required
def material_new():
    return render_template('material_form.html')

@pages_bp.route('/materials/<int:material_id>/edit')
@login_required
def material_edit(material_id):
    return render_template('material_form.html', material_id=material_id)


# 库存
@pages_bp.route('/inventory')
@login_required
def inventory():
    return render_template('inventory_list.html')


# 入库单
@pages_bp.route('/in-orders')
@login_required
def in_orders():
    return render_template('in_order_list.html')

@pages_bp.route('/in-orders/new')
@login_required
def in_order_new():
    return render_template('in_order_form.html')

@pages_bp.route('/in-orders/<int:order_id>/edit')
@login_required
def in_order_edit(order_id):
    return render_template('in_order_form.html', order_id=order_id)

@pages_bp.route('/in-orders/<int:order_id>/detail')
@login_required
def in_order_detail(order_id):
    try:
        order = OrderService.get_in_order_by_id(order_id)
    except Exception:
        logger.exception('加载入库单详情失败: order_id=%s', order_id)
        return '订单加载失败，请稍后重试', 500
    if not order:
        return '订单不存在', 404
    return render_template('in_order_detail.html', order=order)

@pages_bp.route('/in-order-details')
@login_required
def in_order_details():
    return render_template('in_order_detail_list.html')


# 出库单
@pages_bp.route('/out-orders')
@login_required
def out_orders():
    return render_template('out_order_list.html')

@pages_bp.route('/out-orders/new')
@login_required
def out_order_new():
    return render_template('out_order_form.html')

@pages_bp.route('/out-orders/<int:order_id>/edit')
@login_required
def out_order_edit(order_id):
    return render_template('out_order_form.html', order_id=order_id)

@pages_bp.route('/out-orders/<int:order_id>/detail')
@login_required
def out_order_detail(order_id):
    try:
        order = OrderService.get_out_order_by_id(order_id)
        if not order:
            return '订单不存在', 404
        related_returns, _ = OrderService.get_return_orders_by_out_order(order_id)
    except Exception:
        logger.exception('加载出库单详情失败: order_id=%s', order_id)
        return '订单加载失败，请稍后重试', 500
    return render_template('out_order_detail.html', order=order, related_returns=related_returns)

@pages_bp.route('/out-orders/<int:order_id>/print')
@login_required
def out_order_print(order_id):
    try:
        order = OrderService.get_out_order_by_id(order_id)
    except Exception:
        logger.exception('加载出库单打印页失败: order_id=%s', order_id)
        return '订单加载失败，请稍后重试', 500
    if not order:
        return '订单不存在', 404
    return render_template('out_order_print.html', order=order)

@pages_bp.route('/out-order-details')
@login_required
def out_order_details():
    return render_template('out_order_detail_list.html')


# 供应商
@pages_bp.route('/suppliers')
@login_required
def suppliers():
    return render_template('supplier_list.html')

@pages_bp.route('/suppliers/new')
@login_required
def supplier_new():
    return render_template('supplier_form.html')

@pages_bp.route('/suppliers/<int:supplier_id>/edit')
@login_required
def supplier_edit(supplier_id):
    return render_template('supplier_form.html', supplier_id=supplier_id)


# 员工
@pages_bp.route('/employees')
@login_required
def employees():
    return render_template('employee_list.html')

@pages_bp.route('/employees/new')
@login_required
def employee_new():
    return render_template('employee_form.html')

@pages_bp.route('/employees/<int:employee_id>/edit')
@login_required
def employee_edit(employee_id):
    return render_template('employee_form.html', employee_id=employee_id)


# 报表
@pages_bp.route('/reports/inventory')
@login_required
def report_inventory():
    return render_template('report_inventory.html')

@pages_bp.route('/reports/in-detail')
@login_required
def report_in_detail():
    return render_template('report_in_detail.html')

@pages_bp.route('/reports/out-detail')
@login_required
def report_out_detail():
    return render_template('report_out_detail.html')

@pages_bp.route('/reports/summary')
@login_required
def report_summary():
    return render_template('report_summary.html')

@pages_bp.route('/reports/stock-flow')
@login_required
def report_stock_flow():
    return render_template('report_stock_flow.html')


# 大小类
@pages_bp.route('/category-major')
@login_required
def category_major():
    return render_template('category_major_list.html')

@pages_bp.route('/category-major/new')
@login_required
def category_major_new():
    return render_template('category_major_form.html')

@pages_bp.route('/category-major/<int:category_id>/edit')
@login_required
def category_major_edit(category_id):
    return render_template('category_major_form.html', category_id=category_id)

@pages_bp.route('/category-minor')
@login_required
def category_minor():
    return render_template('category_minor_list.html')

@pages_bp.route('/category-minor/new')
@login_required
def category_minor_new():
    return render_template('category_minor_form.html')

@pages_bp.route('/category-minor/<int:category_id>/edit')
@login_required
def category_minor_edit(category_id):
    return render_template('category_minor_form.html', category_id=category_id)


# 退库单
@pages_bp.route('/return-orders')
@login_required
def return_orders():
    return render_template('return_order_list.html')

@pages_bp.route('/return-orders/new')
@login_required
def return_order_new():
    return render_template('return_order_form.html')

@pages_bp.route('/return-orders/<int:order_id>/edit')
@login_required
def return_order_edit(order_id):
    return render_template('return_order_form.html', order_id=order_id)

@pages_bp.route('/return-orders/<int:order_id>/detail')
@login_required
def return_order_detail(order_id):
    try:
        order = OrderService.get_return_order_by_id(order_id)
    except Exception:
        logger.exception('加载退库单详情失败: order_id=%s', order_id)
        return '订单加载失败，请稍后重试', 500
    if not order:
        return '订单不存在', 404
    return render_template('return_order_detail.html', order=order)

@pages_bp.route('/return-order-details')
@login_required
def return_order_details():
    return render_template('return_order_detail_list.html')


# 称重记录
@pages_bp.route('/weight-records')
@login_required
def weight_records():
    return render_template('weight_record_list.html')


# 产品 + BOM
@pages_bp.route('/products')
@login_required
def product_list():
    return render_template('product_list.html')

@pages_bp.route('/products/new')
@login_required
def product_new():
    return render_template('product_form.html')

@pages_bp.route('/products/<int:product_id>/edit')
@login_required
def product_edit(product_id):
    return render_template('product_form.html', product_id=product_id)

@pages_bp.route('/products/<int:product_id>/bom')
@login_required
def product_bom(product_id):
    return render_template('bom_manage.html', product_id=product_id)

@pages_bp.route('/bom-calc')
@login_required
def bom_calc():
    return render_template('bom_calc.html')
