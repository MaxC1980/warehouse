import logging
from flask import Blueprint, request, jsonify, session
from services.order_service import OrderService

logger = logging.getLogger(__name__)
from utils.pagination import get_per_page
from utils.decorators import require_permission

return_order_bp = Blueprint('return_order', __name__)

@return_order_bp.route('/return-orders', methods=['GET'])
def get_return_orders():
    page = request.args.get('page', 1, type=int)
    per_page = get_per_page()
    status = request.args.get('status')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    out_order_no = request.args.get('out_order_no')
    keyword = request.args.get('keyword')

    orders, total = OrderService.get_return_orders(
        page=page,
        per_page=per_page,
        status=status,
        start_date=start_date,
        end_date=end_date,
        out_order_no=out_order_no,
        keyword=keyword
    )
    return jsonify({
        'items': orders,
        'total': total,
        'page': page,
        'per_page': per_page
    })

@return_order_bp.route('/return-orders/<int:order_id>', methods=['GET'])
def get_return_order(order_id):
    order = OrderService.get_return_order_by_id(order_id)
    if order:
        return jsonify(order)
    return jsonify({'error': 'Order not found'}), 404

@return_order_bp.route('/return-orders', methods=['POST'])
@require_permission('return_order', 'edit')
def create_return_order():
    data = request.get_json()
    operator_id = session.get('user_id')

    if not data.get('items') or len(data.get('items', [])) == 0:
        return jsonify({'error': '请至少添加一条明细'}), 400

    if not data.get('department'):
        return jsonify({'error': '请填写部门'}), 400

    if not data.get('receiver'):
        return jsonify({'error': '请填写退库人'}), 400

    try:
        order = OrderService.create_return_order(
            related_out_order_id=data.get('related_out_order_id'),
            department=data.get('department'),
            receiver=data.get('receiver'),
            receiver_date=data.get('receiver_date'),
            operator_id=operator_id,
            remark=data.get('remark'),
            items=data.get('items', [])
        )
        return jsonify(order), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.exception('退库操作失败')
        return jsonify({'error': '服务器内部错误'}), 500

@return_order_bp.route('/return-orders/<int:order_id>', methods=['PUT'])
@require_permission('return_order', 'edit')
def update_return_order(order_id):
    data = request.get_json()

    if not data.get('items') or len(data.get('items', [])) == 0:
        return jsonify({'error': '请至少添加一条明细'}), 400

    if not data.get('department'):
        return jsonify({'error': '请填写部门'}), 400

    if not data.get('receiver'):
        return jsonify({'error': '请填写退库人'}), 400

    order = OrderService.update_return_order(order_id, data)
    if order:
        return jsonify(order)
    return jsonify({'error': 'Order not found'}), 404

@return_order_bp.route('/return-orders/<int:order_id>', methods=['DELETE'])
@require_permission('return_order', 'edit')
def delete_return_order(order_id):
    success = OrderService.delete_return_order(order_id)
    if success:
        return jsonify({'message': 'Order deleted'})
    return jsonify({'error': 'Order not found or cannot be deleted'}), 404

@return_order_bp.route('/return-orders/<int:order_id>/approve', methods=['POST'])
@require_permission('return_order', 'approve')
def approve_return_order(order_id):
    approved_by = session.get('user_id')
    data = request.get_json(silent=True) or {}
    weight_data = data.get('weight_data', [])  # [{out_order_item_id, return_gross_weight}, ...]

    try:
        result = OrderService.approve_return_order(order_id, approved_by, weight_data)
        if result is None:
            return jsonify({'error': 'Order not found or cannot be approved'}), 400
        if result is False:
            return jsonify({'error': '该出库单已有审核通过的退库单，不能重复审核'}), 400
        return jsonify(result)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.exception('退库操作失败')
        return jsonify({'error': '服务器内部错误'}), 500

@return_order_bp.route('/return-orders/by-out-order/<int:out_order_id>', methods=['GET'])
def get_return_orders_by_out_order(out_order_id):
    """获取指定出库单关联的退库单"""
    orders, total = OrderService.get_return_orders_by_out_order(out_order_id)
    return jsonify({
        'items': orders,
        'total': total
    })