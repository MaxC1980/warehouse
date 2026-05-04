from flask import Blueprint, request, jsonify, session, make_response
from services.order_service import OrderService
from services.auth_service import AuthService
from utils.excel_utils import export_to_excel

out_order_bp = Blueprint('out_order', __name__)

@out_order_bp.route('/out-orders', methods=['GET'])
def get_out_orders():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    orders, total = OrderService.get_out_orders(
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

@out_order_bp.route('/out-orders/<int:order_id>', methods=['GET'])
def get_out_order(order_id):
    order = OrderService.get_out_order_by_id(order_id)
    if order:
        return jsonify(order)
    return jsonify({'error': 'Order not found'}), 404

@out_order_bp.route('/out-orders', methods=['POST'])
def create_out_order():
    permission_level = session.get('permission_level', 0)
    if permission_level < 2:
        return jsonify({'error': '无创建权限'}), 403

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
    permission_level = session.get('permission_level', 0)
    if permission_level < 2:
        return jsonify({'error': '无编辑权限'}), 403

    data = request.get_json()

    if not data.get('items') or len(data.get('items', [])) == 0:
        return jsonify({'error': '请至少添加一条明细'}), 400

    if not data.get('receiver'):
        return jsonify({'error': '请填写领用人'}), 400

    if not data.get('purpose'):
        return jsonify({'error': '请填写用途'}), 400

    order = OrderService.update_out_order(order_id, data)
    if order:
        return jsonify(order)
    return jsonify({'error': 'Order not found'}), 404

@out_order_bp.route('/out-orders/<int:order_id>', methods=['DELETE'])
def delete_out_order(order_id):
    permission_level = session.get('permission_level', 0)
    if permission_level < 2:
        return jsonify({'error': '无删除权限'}), 403

    success = OrderService.delete_out_order(order_id)
    if success:
        return jsonify({'message': 'Order deleted'})
    return jsonify({'error': 'Order not found or cannot be deleted'}), 404

@out_order_bp.route('/out-orders/<int:order_id>/approve', methods=['POST'])
def approve_out_order(order_id):
    permission_level = session.get('permission_level', 0)
    if permission_level < 3:
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
    keyword = request.args.get('keyword')
    has_reusable = request.args.get('has_reusable', type=bool)

    orders, total = OrderService.get_out_orders_with_details(
        page=page,
        per_page=per_page,
        status=status,
        start_date=start_date,
        end_date=end_date,
        keyword=keyword,
        has_reusable=has_reusable
    )
    return jsonify({
        'items': orders,
        'total': total,
        'page': page,
        'per_page': per_page
    })

@out_order_bp.route('/out-orders/detail/export', methods=['GET'])
def export_out_orders_detail():
    """导出出库台账明细（所有数据，不受分页限制）"""
    status = request.args.get('status')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    keyword = request.args.get('keyword')

    orders, _ = OrderService.get_out_orders_with_details(
        page=1,
        per_page=10000,
        status=status,
        start_date=start_date,
        end_date=end_date,
        keyword=keyword
    )

    columns = ['出库单号', '部门', '领用人', '用途', '日期', '物料编码', '物料名称', '规格型号', '单位', '批次', '申请用量', '实际用量', '领用毛重', '状态']
    data = []
    for o in orders:
        if not o.get('items') or len(o['items']) == 0:
            data.append([
                o.get('order_no', ''),
                o.get('department', ''),
                o.get('receiver', ''),
                o.get('purpose', ''),
                o.get('receiver_date', ''),
                '', '', '', '', '', '', '', '',
                {'pending': '待审核', 'approved': '已审核', 'completed': '已完成'}.get(o.get('status', ''), o.get('status', ''))
            ])
        else:
            for i, item in enumerate(o['items']):
                data.append([
                    o.get('order_no', ''),
                    o.get('department', ''),
                    o.get('receiver', ''),
                    o.get('purpose', ''),
                    o.get('receiver_date', ''),
                    item.get('material_code', ''),
                    item.get('material_name', ''),
                    item.get('spec', ''),
                    item.get('unit', ''),
                    item.get('batch_no', ''),
                    item.get('requested_quantity', 0),
                    item.get('actual_quantity', 0),
                    item.get('initial_gross_weight', ''),
                    {'pending': '待审核', 'approved': '已审核', 'completed': '已完成'}.get(o.get('status', ''), o.get('status', ''))
                ])

    excel_data = export_to_excel(columns, data, '出库台账')
    response = make_response(excel_data)
    response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    response.headers['Content-Disposition'] = 'attachment; filename=out_order_detail.xlsx'
    return response

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
