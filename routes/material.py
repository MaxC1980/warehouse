from flask import Blueprint, request, jsonify, session
from services.material_service import MaterialService

material_bp = Blueprint('material', __name__)

@material_bp.route('/categories', methods=['GET'])
def get_categories():
    categories = MaterialService.get_all_categories()
    return jsonify(categories)

@material_bp.route('/categories', methods=['POST'])
def create_category():
    permission_level = session.get('permission_level', 0)
    if permission_level < 2:
        return jsonify({'error': '无创建权限'}), 403

    data = request.get_json()
    category = MaterialService.create_category(
        code=data.get('code'),
        name=data.get('name'),
        parent_code=data.get('parent_code'),
        level=data.get('level', 1)
    )
    return jsonify(category), 201

@material_bp.route('/categories/<int:category_id>', methods=['PUT'])
def update_category(category_id):
    permission_level = session.get('permission_level', 0)
    if permission_level < 2:
        return jsonify({'error': '无编辑权限'}), 403

    data = request.get_json()
    category = MaterialService.update_category(
        category_id,
        code=data.get('code'),
        name=data.get('name')
    )
    if category:
        return jsonify(category)
    return jsonify({'error': 'Category not found'}), 404

@material_bp.route('/categories/<int:category_id>', methods=['DELETE'])
def delete_category(category_id):
    permission_level = session.get('permission_level', 0)
    if permission_level < 2:
        return jsonify({'error': '无删除权限'}), 403

    success = MaterialService.delete_category(category_id)
    if success:
        return jsonify({'message': 'Category deleted'})
    return jsonify({'error': 'Category not found or has children'}), 404

@material_bp.route('/materials', methods=['GET'])
def get_materials():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    category_code = request.args.get('category_code')
    keyword = request.args.get('keyword')
    # Additional filters for material selection modal
    major_category = request.args.get('major_category')  # 大类 (2-digit)
    minor_category = request.args.get('minor_category')  # 小类 (4-digit)
    material_code = request.args.get('material_code')
    material_name = request.args.get('material_name')
    material_spec = request.args.get('material_spec')

    materials, total = MaterialService.get_materials(
        page=page,
        per_page=per_page,
        category_code=category_code,
        keyword=keyword,
        major_category=major_category,
        minor_category=minor_category,
        material_code=material_code,
        material_name=material_name,
        material_spec=material_spec
    )
    return jsonify({
        'items': materials,
        'total': total,
        'page': page,
        'per_page': per_page
    })

@material_bp.route('/materials/<int:material_id>', methods=['GET'])
def get_material(material_id):
    material = MaterialService.get_material_by_id(material_id)
    if material:
        return jsonify(material)
    return jsonify({'error': 'Material not found'}), 404

@material_bp.route('/materials', methods=['POST'])
def create_material():
    permission_level = session.get('permission_level', 0)
    if permission_level < 2:
        return jsonify({'error': '无创建权限'}), 403

    data = request.get_json()
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
def update_material(material_id):
    permission_level = session.get('permission_level', 0)
    if permission_level < 2:
        return jsonify({'error': '无编辑权限'}), 403

    data = request.get_json()
    material = MaterialService.update_material(
        material_id,
        name=data.get('name'),
        spec=data.get('spec'),
        unit=data.get('unit'),
        category_code=data.get('category_code'),
        manufacturer=data.get('manufacturer'),
        storage_condition=data.get('storage_condition'),
        shelf_life=data.get('shelf_life'),
        remark=data.get('remark'),
        is_reusable=data.get('is_reusable', 0),
        safety_stock=data.get('safety_stock')
    )
    if material:
        return jsonify(material)
    return jsonify({'error': 'Material not found'}), 404

@material_bp.route('/materials/<int:material_id>', methods=['DELETE'])
def delete_material(material_id):
    permission_level = session.get('permission_level', 0)
    if permission_level < 2:
        return jsonify({'error': '无删除权限'}), 403

    result = MaterialService.delete_material(material_id)
    if result[0]:
        return jsonify({'message': result[1]})
    return jsonify({'error': result[1]}), 400
