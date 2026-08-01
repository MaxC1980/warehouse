from flask import Blueprint, request, jsonify
from services.inventory_service import InventoryService
from utils.pagination import get_per_page
from utils.decorators import require_permission, handle_service_errors

inventory_bp = Blueprint('inventory', __name__)

@inventory_bp.route('/inventory', methods=['GET'])
@require_permission('inventory', 'view')
@handle_service_errors
def get_inventory():
    page = request.args.get('page', 1, type=int)
    # all=true 返回全量 (打印/盘点用), 绕过 per_page 上限
    if request.args.get('all') == 'true':
        per_page = 1000000
    else:
        per_page = get_per_page()
    keyword = request.args.get('keyword')
    summary = request.args.get('summary', type=bool, default=False)
    category_code = request.args.get('category_code')
    status = request.args.get('status')

    inventory, total, total_quantity = InventoryService.get_inventory(
        page=page,
        per_page=per_page,
        keyword=keyword,
        summary=summary,
        category_code=category_code,
        status=status
    )
    return jsonify({
        'items': inventory,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_quantity': total_quantity
    })

@inventory_bp.route('/inventory/<int:material_id>', methods=['GET'])
@require_permission('inventory', 'view')
@handle_service_errors
def get_inventory_detail(material_id):
    inventory = InventoryService.get_inventory_by_material(material_id)
    if inventory:
        return jsonify(inventory)
    return jsonify({'error': '库存不存在'}), 404

@inventory_bp.route('/inventory/<int:material_id>/details', methods=['GET'])
@require_permission('inventory', 'view')
@handle_service_errors
def get_inventory_batch_details(material_id):
    details = InventoryService.get_inventory_details(material_id)
    return jsonify(details)

@inventory_bp.route('/inventory/select', methods=['GET'])
@require_permission('inventory', 'view')
@handle_service_errors
def get_inventory_for_select():
    """库存选择接口，支持按类别、关键词过滤和分页"""
    category_code = request.args.get('category_code')
    keyword = request.args.get('keyword')
    page = request.args.get('page', 1, type=int)
    per_page = get_per_page(default=50)

    items, total = InventoryService.get_inventory_for_select(
        category_code=category_code,
        keyword=keyword,
        page=page,
        per_page=per_page
    )
    return jsonify({'items': items, 'total': total, 'page': page, 'per_page': per_page})
