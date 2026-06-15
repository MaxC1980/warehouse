import logging
from flask import Blueprint, request, jsonify, session
from services.order_service import OrderService
from utils.pagination import get_per_page
from utils.decorators import require_permission

logger = logging.getLogger(__name__)

in_order_bp = Blueprint('in_order', __name__)


@in_order_bp.route('/in-orders', methods=['GET'])
@require_permission('in_order', 'view')
def get_in_orders():
    try:
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
    except Exception:
        logger.exception('查询入库单列表失败')
        return jsonify({'error': '服务器内部错误'}), 500


@in_order_bp.route('/in-orders/<int:order_id>', methods=['GET'])
@require_permission('in_order', 'view')
def get_in_order(order_id):
    try:
        order = OrderService.get_in_order_by_id(order_id)
        if order:
            return jsonify(order)
        return jsonify({'error': '入库单不存在'}), 404
    except Exception:
        logger.exception('查询入库单失败: order_id=%s', order_id)
        return jsonify({'error': '服务器内部错误'}), 500


@in_order_bp.route('/in-orders', methods=['POST'])
@require_permission('in_order', 'edit')
def create_in_order():
    data = request.get_json(silent=True) or {}
    operator_id = session.get('user_id')

    if not data.get('items') or len(data.get('items', [])) == 0:
        return jsonify({'error': '请至少添加一条明细'}), 400

    if not data.get('receiver'):
        return jsonify({'error': '请填写经手人'}), 400

    try:
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
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception:
        logger.exception('创建入库单失败')
        return jsonify({'error': '服务器内部错误'}), 500


@in_order_bp.route('/in-orders/<int:order_id>', methods=['PUT'])
@require_permission('in_order', 'edit')
def update_in_order(order_id):
    data = request.get_json(silent=True) or {}

    if not data.get('items') or len(data.get('items', [])) == 0:
        return jsonify({'error': '请至少添加一条明细'}), 400

    if not data.get('receiver'):
        return jsonify({'error': '请填写经手人'}), 400

    try:
        order = OrderService.update_in_order(order_id, data)
        if order:
            return jsonify(order)
        return jsonify({'error': '入库单不存在'}), 404
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception:
        logger.exception('更新入库单失败: order_id=%s', order_id)
        return jsonify({'error': '服务器内部错误'}), 500


@in_order_bp.route('/in-orders/<int:order_id>', methods=['DELETE'])
@require_permission('in_order', 'edit')
def delete_in_order(order_id):
    try:
        success = OrderService.delete_in_order(order_id)
        if success:
            return jsonify({'message': '入库单已删除'})
        return jsonify({'error': '入库单不存在或无法删除'}), 404
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception:
        logger.exception('删除入库单失败: order_id=%s', order_id)
        return jsonify({'error': '服务器内部错误'}), 500


@in_order_bp.route('/in-orders/<int:order_id>/approve', methods=['POST'])
@require_permission('in_order', 'approve')
def approve_in_order(order_id):
    approved_by = session.get('user_id')
    try:
        result = OrderService.approve_in_order(order_id, approved_by)
        if result:
            return jsonify(result)
        return jsonify({'error': '入库单不存在或无法审核'}), 400
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception:
        logger.exception('审核入库单失败: order_id=%s', order_id)
        return jsonify({'error': '服务器内部错误'}), 500


@in_order_bp.route('/in-orders/detail', methods=['GET'])
@require_permission('in_order', 'view')
def get_in_orders_with_details():
    try:
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
    except Exception:
        logger.exception('查询入库单明细失败')
        return jsonify({'error': '服务器内部错误'}), 500
