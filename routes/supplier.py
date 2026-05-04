from flask import Blueprint, request, jsonify, session
from services.supplier_service import SupplierService

supplier_bp = Blueprint('supplier', __name__)

@supplier_bp.route('/suppliers', methods=['GET'])
def get_suppliers():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    keyword = request.args.get('keyword')

    suppliers, total = SupplierService.get_suppliers(
        page=page,
        per_page=per_page,
        keyword=keyword
    )
    return jsonify({
        'items': suppliers,
        'total': total,
        'page': page,
        'per_page': per_page
    })

@supplier_bp.route('/suppliers/<int:supplier_id>', methods=['GET'])
def get_supplier(supplier_id):
    supplier = SupplierService.get_supplier_by_id(supplier_id)
    if supplier:
        return jsonify(supplier)
    return jsonify({'error': 'Supplier not found'}), 404

@supplier_bp.route('/suppliers', methods=['POST'])
def create_supplier():
    permission_level = session.get('permission_level', 0)
    if permission_level < 2:
        return jsonify({'error': '无创建权限'}), 403

    data = request.get_json()
    supplier = SupplierService.create_supplier(
        name=data.get('name'),
        contact=data.get('contact'),
        phone=data.get('phone'),
        address=data.get('address')
    )
    return jsonify(supplier), 201

@supplier_bp.route('/suppliers/<int:supplier_id>', methods=['PUT'])
def update_supplier(supplier_id):
    permission_level = session.get('permission_level', 0)
    if permission_level < 2:
        return jsonify({'error': '无编辑权限'}), 403

    data = request.get_json()
    supplier = SupplierService.update_supplier(supplier_id, data)
    if supplier:
        return jsonify(supplier)
    return jsonify({'error': 'Supplier not found'}), 404

@supplier_bp.route('/suppliers/<int:supplier_id>', methods=['DELETE'])
def delete_supplier(supplier_id):
    permission_level = session.get('permission_level', 0)
    if permission_level < 2:
        return jsonify({'error': '无删除权限'}), 403

    success, msg = SupplierService.delete_supplier(supplier_id)
    if success:
        return jsonify({'message': 'Supplier deleted'})
    return jsonify({'error': msg}), 400
