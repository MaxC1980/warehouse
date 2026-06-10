from flask import Blueprint, request, jsonify
from services.supplier_service import SupplierService
from utils.decorators import require_permission
from utils.pagination import get_per_page

supplier_bp = Blueprint('supplier', __name__)

@supplier_bp.route('/suppliers', methods=['GET'])
def get_suppliers():
    page = request.args.get('page', 1, type=int)
    per_page = get_per_page(max_value=1000)
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
@require_permission('supplier', 'edit')
def create_supplier():
    data = request.get_json(silent=True) or {}
    supplier = SupplierService.create_supplier(
        name=data.get('name'),
        contact=data.get('contact'),
        phone=data.get('phone'),
        address=data.get('address')
    )
    return jsonify(supplier), 201

@supplier_bp.route('/suppliers/<int:supplier_id>', methods=['PUT'])
@require_permission('supplier', 'edit')
def update_supplier(supplier_id):
    data = request.get_json(silent=True) or {}
    supplier = SupplierService.update_supplier(supplier_id, data)
    if supplier:
        return jsonify(supplier)
    return jsonify({'error': 'Supplier not found'}), 404

@supplier_bp.route('/suppliers/<int:supplier_id>', methods=['DELETE'])
@require_permission('supplier', 'edit')
def delete_supplier(supplier_id):
    success, msg = SupplierService.delete_supplier(supplier_id)
    if success:
        return jsonify({'message': 'Supplier deleted'})
    return jsonify({'error': msg}), 400
