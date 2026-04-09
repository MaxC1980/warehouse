from flask import Blueprint, request, jsonify
from services.inventory_service import InventoryService

inventory_bp = Blueprint('inventory', __name__)

@inventory_bp.route('/inventory', methods=['GET'])
def get_inventory():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    keyword = request.args.get('keyword')
    summary = request.args.get('summary', type=bool, default=False)
    category_code = request.args.get('category_code')

    inventory, total = InventoryService.get_inventory(
        page=page,
        per_page=per_page,
        keyword=keyword,
        summary=summary,
        category_code=category_code
    )
    return jsonify({
        'items': inventory,
        'total': total,
        'page': page,
        'per_page': per_page
    })

@inventory_bp.route('/inventory/<int:material_id>', methods=['GET'])
def get_inventory_detail(material_id):
    inventory = InventoryService.get_inventory_by_material(material_id)
    if inventory:
        return jsonify(inventory)
    return jsonify({'error': 'Inventory not found'}), 404

@inventory_bp.route('/inventory/<int:material_id>/details', methods=['GET'])
def get_inventory_batch_details(material_id):
    details = InventoryService.get_inventory_details(material_id)
    return jsonify(details)

@inventory_bp.route('/inventory/select', methods=['GET'])
def get_inventory_for_select():
    """库存选择接口，支持按类别、物料编码、名称、规格过滤和分页"""
    category_code = request.args.get('category_code')
    material_code = request.args.get('material_code')
    material_name = request.args.get('material_name')
    material_spec = request.args.get('material_spec')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    items, total = InventoryService.get_inventory_for_select(
        category_code=category_code,
        material_code=material_code,
        material_name=material_name,
        material_spec=material_spec,
        page=page,
        per_page=per_page
    )
    return jsonify({'items': items, 'total': total, 'page': page, 'per_page': per_page})
