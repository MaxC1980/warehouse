from flask import Blueprint, request, jsonify
from services.material_service import MaterialService
from utils.pagination import get_per_page
from utils.decorators import require_permission, handle_service_errors

material_bp = Blueprint('material', __name__)

@material_bp.route('/categories', methods=['GET'])
@require_permission('material', 'view')
@handle_service_errors
def get_categories():
    categories = MaterialService.get_all_categories()
    return jsonify(categories)

@material_bp.route('/categories', methods=['POST'])
@require_permission('category_major', 'edit')
@handle_service_errors
def create_category():
    data = request.get_json(silent=True) or {}
    category = MaterialService.create_category(
        code=data.get('code'),
        name=data.get('name'),
        parent_code=data.get('parent_code'),
        level=data.get('level', 1)
    )
    return jsonify(category), 201

@material_bp.route('/categories/<int:category_id>', methods=['PUT'])
@require_permission('category_major', 'edit')
@handle_service_errors
def update_category(category_id):
    data = request.get_json(silent=True) or {}
    ok, category = MaterialService.update_category(
        category_id,
        code=data.get('code'),
        name=data.get('name'),
        parent_code=data.get('parent_code')
    )
    if ok:
        return jsonify(category)
    if category == 'has_materials':
        return jsonify({'error': '该分类已被物料引用，无法修改代码或所属大类'}), 400
    return jsonify({'error': '分类不存在'}), 404

@material_bp.route('/categories/<int:category_id>', methods=['DELETE'])
@require_permission('category_major', 'edit')
@handle_service_errors
def delete_category(category_id):
    result = MaterialService.delete_category(category_id)
    if result == 'ok':
        return jsonify({'message': '分类已删除'})
    if result == 'has_children':
        return jsonify({'error': '该分类下存在子分类，无法删除'}), 400
    if result == 'has_materials':
        return jsonify({'error': '该分类已被物料引用，无法删除'}), 400
    return jsonify({'error': '分类不存在'}), 404

@material_bp.route('/materials', methods=['GET'])
@require_permission('material', 'view')
@handle_service_errors
def get_materials():
    page = request.args.get('page', 1, type=int)
    per_page = get_per_page(max_value=1000)
    category_code = request.args.get('category_code')
    keyword = request.args.get('keyword')
    major_category = request.args.get('major_category')
    minor_category = request.args.get('minor_category')

    materials, total = MaterialService.get_materials(
        page=page,
        per_page=per_page,
        category_code=category_code,
        keyword=keyword,
        major_category=major_category,
        minor_category=minor_category
    )
    return jsonify({
        'items': materials,
        'total': total,
        'page': page,
        'per_page': per_page
    })

@material_bp.route('/materials/<int:material_id>', methods=['GET'])
@require_permission('material', 'view')
@handle_service_errors
def get_material(material_id):
    material = MaterialService.get_material_by_id(material_id)
    if material:
        return jsonify(material)
    return jsonify({'error': '物料不存在'}), 404

@material_bp.route('/materials', methods=['POST'])
@require_permission('material', 'edit')
@handle_service_errors
def create_material():
    data = request.get_json(silent=True) or {}
    material = MaterialService.create_material(
        name=data.get('name'),
        spec=data.get('spec'),
        unit=data.get('unit'),
        category_code=data.get('category_code'),
        manufacturer=data.get('manufacturer'),
        storage_condition=data.get('storage_condition', '常温'),
        shelf_life=data.get('shelf_life'),
        remark=data.get('remark'),
        is_reusable=data.get('is_reusable', 0),
        safety_stock=data.get('safety_stock', 0)
    )
    return jsonify(material), 201

@material_bp.route('/materials/<int:material_id>', methods=['PUT'])
@require_permission('material', 'edit')
@handle_service_errors
def update_material(material_id):
    data = request.get_json(silent=True) or {}
    material = MaterialService.update_material(material_id, data)
    if material:
        return jsonify(material)
    return jsonify({'error': '物料不存在'}), 404

@material_bp.route('/materials/<int:material_id>', methods=['DELETE'])
@require_permission('material', 'edit')
@handle_service_errors
def delete_material(material_id):
    result = MaterialService.delete_material(material_id)
    if result[0]:
        return jsonify({'message': result[1]})
    return jsonify({'error': result[1]}), 400
