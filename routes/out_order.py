from flask import Blueprint, request, jsonify, session
from services.order_service import OrderService
from services.auth_service import AuthService

out_order_bp = Blueprint('out_order', __name__)

@out_order_bp.route('/out-orders', methods=['GET'])
def get_out_orders():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status')

    orders, total = OrderService.get_out_orders(
        page=page,
        per_page=per_page,
        status=status
    )
    return jsonify({
        'items': orders,
        'total': total,
        'page': page,
        'per_page': per_page
    })

@out_order_bp.route('/out-orders/<int:order_id>', methods=['GET'])
def get_out_order(order_id):
    order = OrderService.get_out_order_by_id(order_id)
    if order:
        return jsonify(order)
    return jsonify({'error': 'Order not found'}), 404

@out_order_bp.route('/out-orders', methods=['POST'])
def create_out_order():
    data = request.get_json()
    operator_id = session.get('user_id')

    if not data.get('items') or len(data.get('items', [])) == 0:
        return jsonify({'error': '请至少添加一条明细'}), 400

    if not data.get('receiver'):
        return jsonify({'error': '请填写领用人'}), 400

    if not data.get('purpose'):
        return jsonify({'error': '请填写用途'}), 400

    order = OrderService.create_out_order(
        department=data.get('department'),
        receiver=data.get('receiver'),
        receiver_date=data.get('receiver_date'),
        operator_id=operator_id,
        remark=data.get('remark'),
        purpose=data.get('purpose'),
        items=data.get('items', [])
    )
    return jsonify(order), 201

@out_order_bp.route('/out-orders/<int:order_id>', methods=['PUT'])
def update_out_order(order_id):
    data = request.get_json()

    if not data.get('items') or len(data.get('items', [])) == 0:
        return jsonify({'error': '请至少添加一条明细'}), 400

    if not data.get('receiver'):
        return jsonify({'error': '请填写领用人'}), 400

    if not data.get('purpose'):
        return jsonify({'error': '请填写用途'}), 400

    order = OrderService.update_out_order(
        order_id,
        department=data.get('department'),
        receiver=data.get('receiver'),
        receiver_date=data.get('receiver_date'),
        remark=data.get('remark'),
        purpose=data.get('purpose'),
        items=data.get('items', [])
    )
    if order:
        return jsonify(order)
    return jsonify({'error': 'Order not found'}), 404

@out_order_bp.route('/out-orders/<int:order_id>', methods=['DELETE'])
def delete_out_order(order_id):
    success = OrderService.delete_out_order(order_id)
    if success:
        return jsonify({'message': 'Order deleted'})
    return jsonify({'error': 'Order not found or cannot be deleted'}), 404

@out_order_bp.route('/out-orders/<int:order_id>/approve', methods=['POST'])
def approve_out_order(order_id):
    if not AuthService.check_can_approve(session.get('user_id')):
        return jsonify({'error': '无审核权限'}), 403

    approved_by = session.get('user_id')
    data = request.get_json(silent=True) or {}
    weight_data = data.get('weight_data', [])  # [{out_order_item_id, initial_gross_weight}, ...]

    try:
        result = OrderService.approve_out_order(order_id, approved_by, weight_data)
        if result:
            return jsonify(result)
        return jsonify({'error': 'Order not found or cannot be approved'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@out_order_bp.route('/out-orders/detail', methods=['GET'])
def get_out_orders_with_details():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    material_code = request.args.get('material_code')
    material_name = request.args.get('material_name')
    material_spec = request.args.get('material_spec')
    has_reusable = request.args.get('has_reusable', type=bool)

    orders, total = OrderService.get_out_orders_with_details(
        page=page,
        per_page=per_page,
        status=status,
        start_date=start_date,
        end_date=end_date,
        material_code=material_code,
        material_name=material_name,
        material_spec=material_spec,
        has_reusable=has_reusable
    )
    return jsonify({
        'items': orders,
        'total': total,
        'page': page,
        'per_page': per_page
    })

@out_order_bp.route('/out-orders/<int:order_id>/items/<int:item_id>/weight', methods=['GET'])
def get_out_order_item_weight(order_id, item_id):
    """获取出库单明细的称重记录"""
    weight = OrderService.get_weight_record_by_out_order_item(item_id)
    if weight:
        return jsonify(weight)
    return jsonify(None)

@out_order_bp.route('/weight-records', methods=['GET'])
def get_weight_records():
    """获取所有称重记录"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status')
    material_code = request.args.get('material_code')
    material_name = request.args.get('material_name')

    records, total = OrderService.get_all_weight_records(
        page=page,
        per_page=per_page,
        status=status,
        material_code=material_code,
        material_name=material_name
    )
    return jsonify({
        'items': records,
        'total': total,
        'page': page,
        'per_page': per_page
    })
