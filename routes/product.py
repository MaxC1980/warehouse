"""产品 + BOM + 计算 API"""
from flask import Blueprint, request, jsonify
from services.product_service import ProductService
from utils.pagination import get_per_page
from utils.decorators import require_permission, handle_service_errors

product_bp = Blueprint('product', __name__)


@product_bp.route('/products', methods=['GET'])
@require_permission('product', 'view')
@handle_service_errors
def list_products():
    page = request.args.get('page', 1, type=int)
    per_page = get_per_page(max_value=1000)
    keyword = request.args.get('keyword')
    items, total = ProductService.get_products(page=page, per_page=per_page, keyword=keyword)
    return jsonify({'items': items, 'total': total, 'page': page, 'per_page': per_page})


@product_bp.route('/products/active', methods=['GET'])
@require_permission('product', 'view')
@handle_service_errors
def list_active_products():
    items = ProductService.get_active_products()
    return jsonify({'items': items})


@product_bp.route('/products/<int:product_id>/toggle-disable', methods=['POST'])
@require_permission('product', 'edit')
@handle_service_errors
def toggle_disable(product_id):
    p = ProductService.get_product_by_id(product_id)
    if not p:
        return jsonify({'error': '产品不存在'}), 404
    new_val = 0 if p.get('disabled') else 1
    ProductService.update_product(product_id, {'disabled': new_val})
    return jsonify({'disabled': bool(new_val)})


@product_bp.route('/products/<int:product_id>', methods=['GET'])
@require_permission('product', 'view')
@handle_service_errors
def get_product(product_id):
    product = ProductService.get_product_by_id(product_id)
    if not product:
        return jsonify({'error': '产品不存在'}), 404
    return jsonify(product)


@product_bp.route('/products/next-code', methods=['GET'])
@require_permission('product', 'view')
@handle_service_errors
def next_code():
    prefix = request.args.get('prefix')
    code = ProductService.get_next_code(prefix=prefix)
    return jsonify({'code': code})


@product_bp.route('/products', methods=['POST'])
@require_permission('product', 'edit')
@handle_service_errors
def create_product():
    data = request.get_json(silent=True) or {}
    product = ProductService.create_product(
        code=data.get('code'),
        name=data.get('name'),
        spec=data.get('spec'),
        unit=data.get('unit', '个'),
        remark=data.get('remark'),
    )
    return jsonify(product), 201


@product_bp.route('/products/<int:product_id>', methods=['PUT'])
@require_permission('product', 'edit')
@handle_service_errors
def update_product(product_id):
    data = request.get_json(silent=True) or {}
    product = ProductService.update_product(product_id, data)
    if product:
        return jsonify(product)
    return jsonify({'error': '产品不存在'}), 404


@product_bp.route('/products/<int:product_id>/duplicate', methods=['POST'])
@require_permission('product', 'edit')
@handle_service_errors
def duplicate_product(product_id):
    ok, result = ProductService.duplicate_product(product_id)
    if ok:
        return jsonify(result), 201
    return jsonify({'error': result}), 400


@product_bp.route('/products/<int:product_id>', methods=['DELETE'])
@require_permission('product', 'edit')
@handle_service_errors
def delete_product(product_id):
    ok, msg = ProductService.delete_product(product_id)
    if ok:
        return jsonify({'message': msg})
    return jsonify({'error': msg}), 400


@product_bp.route('/products/<int:product_id>/bom', methods=['GET'])
@require_permission('product', 'view')
@handle_service_errors
def get_bom(product_id):
    items = ProductService.get_bom(product_id)
    return jsonify({'items': items})


@product_bp.route('/products/<int:product_id>/bom', methods=['PUT'])
@require_permission('product', 'edit')
@handle_service_errors
def replace_bom(product_id):
    data = request.get_json(silent=True) or {}
    items = ProductService.replace_bom(product_id, data.get('items', []))
    return jsonify({'items': items})


@product_bp.route('/bom/check', methods=['POST'])
@require_permission('product', 'view')
@handle_service_errors
def check_requirements():
    data = request.get_json(silent=True) or {}
    exclude_expired = bool(data.get('exclude_expired', True))
    result = ProductService.calculate_requirements(
        data.get('items', []),
        exclude_expired=exclude_expired,
    )
    return jsonify(result)


@product_bp.route('/bom/max-producible', methods=['POST'])
@require_permission('product', 'view')
@handle_service_errors
def max_producible():
    data = request.get_json(silent=True) or {}
    product_id = data.get('product_id')
    if not product_id:
        return jsonify({'error': '缺少 product_id'}), 400
    exclude_expired = bool(data.get('exclude_expired', True))
    result = ProductService.calculate_max_producible(product_id, exclude_expired=exclude_expired)
    return jsonify(result)
