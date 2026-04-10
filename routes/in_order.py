from flask import Blueprint, request, jsonify, session
from services.order_service import OrderService
from services.auth_service import AuthService

in_order_bp = Blueprint('in_order', __name__)

@in_order_bp.route('/in-orders', methods=['GET'])
def get_in_orders():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status')

    orders, total = OrderService.get_in_orders(
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

@in_order_bp.route('/in-orders/<int:order_id>', methods=['GET'])
def get_in_order(order_id):
    order = OrderService.get_in_order_by_id(order_id)
    if order:
        return jsonify(order)
    return jsonify({'error': 'Order not found'}), 404

@in_order_bp.route('/in-orders', methods=['POST'])
def create_in_order():
    permission_level = session.get('permission_level', 0)
    if permission_level < 2:
        return jsonify({'error': '无创建权限'}), 403

    data = request.get_json()
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
def update_in_order(order_id):
    permission_level = session.get('permission_level', 0)
    if permission_level < 2:
        return jsonify({'error': '无编辑权限'}), 403

    data = request.get_json()

    if not data.get('items') or len(data.get('items', [])) == 0:
        return jsonify({'error': '请至少添加一条明细'}), 400

    if not data.get('receiver'):
        return jsonify({'error': '请填写经手人'}), 400

    order = OrderService.update_in_order(
        order_id,
        supplier_id=data.get('supplier_id'),
        remark=data.get('remark'),
        receiver=data.get('receiver'),
        purpose=data.get('purpose'),
        receiver_date=data.get('receiver_date'),
        items=data.get('items', [])
    )
    if order:
        return jsonify(order)
    return jsonify({'error': 'Order not found'}), 404

@in_order_bp.route('/in-orders/<int:order_id>', methods=['DELETE'])
def delete_in_order(order_id):
    permission_level = session.get('permission_level', 0)
    if permission_level < 2:
        return jsonify({'error': '无删除权限'}), 403

    success = OrderService.delete_in_order(order_id)
    if success:
        return jsonify({'message': 'Order deleted'})
    return jsonify({'error': 'Order not found or cannot be deleted'}), 404

@in_order_bp.route('/in-orders/<int:order_id>/approve', methods=['POST'])
def approve_in_order(order_id):
    permission_level = session.get('permission_level', 0)
    if permission_level < 3:
        return jsonify({'error': '无审核权限'}), 403

    approved_by = session.get('user_id')
    result = OrderService.approve_in_order(order_id, approved_by)
    if result:
        return jsonify(result)
    return jsonify({'error': 'Order not found or cannot be approved'}), 400

@in_order_bp.route('/in-orders/<int:order_id>/reject', methods=['POST'])
def reject_in_order(order_id):
    result = OrderService.reject_in_order(order_id)
    if result:
        return jsonify(result)
    return jsonify({'error': 'Order not found or cannot be rejected'}), 400

@in_order_bp.route('/in-orders/detail', methods=['GET'])
def get_in_orders_with_details():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    material_code = request.args.get('material_code')
    material_name = request.args.get('material_name')
    material_spec = request.args.get('material_spec')

    orders, total = OrderService.get_in_orders_with_details(
        page=page,
        per_page=per_page,
        status=status,
        start_date=start_date,
        end_date=end_date,
        material_code=material_code,
        material_name=material_name,
        material_spec=material_spec
    )
    return jsonify({
        'items': orders,
        'total': total,
        'page': page,
        'per_page': per_page
    })
