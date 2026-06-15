import logging
from flask import Blueprint, request, jsonify, session
from services.order_service import OrderService
from utils.pagination import get_per_page
from utils.decorators import require_permission, handle_service_errors

logger = logging.getLogger(__name__)

in_order_bp = Blueprint('in_order', __name__)


@in_order_bp.route('/in-orders', methods=['GET'])
@require_permission('in_order', 'view')
@handle_service_errors
def get_in_orders():
    page = request.args.get('page', 1, type=int)
    per_page = get_per_page()
    status = request.args.get('status')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    orders, total = OrderService.get_in_orders(
        page=page,
        per_page=per_page,
        status=status,
        start_date=start_date,
        end_date=end_date
    )
    return jsonify({
        'items': orders,
        'total': total,
        'page': page,
        'per_page': per_page
    })


@in_order_bp.route('/in-orders/<int:order_id>', methods=['GET'])
@require_permission('in_order', 'view')
@handle_service_errors
def get_in_order(order_id):
    order = OrderService.get_in_order_by_id(order_id)
    if order:
        return jsonify(order)
    return jsonify({'error': '入库单不存在'}), 404


@in_order_bp.route('/in-orders', methods=['POST'])
@require_permission('in_order', 'edit')
@handle_service_errors
def create_in_order():
    data = request.get_json(silent=True) or {}
    operator_id = session.get('user_id')

    if not data.get('items') or len(data.get('items', [])) == 0:
        return jsonify({'error': '请至少添加一条明细'}), 400

    if not data.get('receiver'):
        return jsonify({'error': '请填写经手人'}), 400

    order = OrderService.create_in_order(
        supplier_id=data.get('supplier_id'),
        operator_id=operator_id,
        remark=data.get('remark'),
        receiver=data.get('receiver'),
        purpose=data.get('purpose'),
        receiver_date=data.get('receiver_date'),
        items=data.get('items', [])
    )
    return jsonify(order), 201


@in_order_bp.route('/in-orders/<int:order_id>', methods=['PUT'])
@require_permission('in_order', 'edit')
@handle_service_errors
def update_in_order(order_id):
    data = request.get_json(silent=True) or {}

    if not data.get('items') or len(data.get('items', [])) == 0:
        return jsonify({'error': '请至少添加一条明细'}), 400

    if not data.get('receiver'):
        return jsonify({'error': '请填写经手人'}), 400

    order = OrderService.update_in_order(order_id, data)
    if order:
        return jsonify(order)
    return jsonify({'error': '入库单不存在'}), 404


@in_order_bp.route('/in-orders/<int:order_id>', methods=['DELETE'])
@require_permission('in_order', 'edit')
@handle_service_errors
def delete_in_order(order_id):
    success = OrderService.delete_in_order(order_id)
    if success:
        return jsonify({'message': '入库单已删除'})
    return jsonify({'error': '入库单不存在或无法删除'}), 404


@in_order_bp.route('/in-orders/<int:order_id>/approve', methods=['POST'])
@require_permission('in_order', 'approve')
@handle_service_errors
def approve_in_order(order_id):
    approved_by = session.get('user_id')
    result = OrderService.approve_in_order(order_id, approved_by)
    if result:
        return jsonify(result)
    return jsonify({'error': '入库单不存在或无法审核'}), 400


@in_order_bp.route('/in-orders/detail', methods=['GET'])
@require_permission('in_order', 'view')
@handle_service_errors
def get_in_orders_with_details():
    page = request.args.get('page', 1, type=int)
    per_page = get_per_page()
    status = request.args.get('status')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    keyword = request.args.get('keyword')

    orders, total = OrderService.get_in_orders_with_details(
        page=page,
        per_page=per_page,
        status=status,
        start_date=start_date,
        end_date=end_date,
        keyword=keyword
    )
    return jsonify({
        'items': orders,
        'total': total,
        'page': page,
        'per_page': per_page
    })
