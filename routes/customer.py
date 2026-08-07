from flask import Blueprint, request, jsonify
from services.customer_service import CustomerService
from utils.decorators import require_permission, handle_service_errors
from utils.pagination import get_per_page

customer_bp = Blueprint('customer', __name__)


@customer_bp.route('/customers', methods=['GET'])
@require_permission('customer', 'view')
@handle_service_errors
def get_customers():
    page = request.args.get('page', 1, type=int)
    per_page = get_per_page(max_value=1000)
    keyword = request.args.get('keyword')

    items, total = CustomerService.get_customers(
        page=page,
        per_page=per_page,
        keyword=keyword
    )
    return jsonify({
        'items': items,
        'total': total,
        'page': page,
        'per_page': per_page
    })


@customer_bp.route('/customers/<int:customer_id>', methods=['GET'])
@require_permission('customer', 'view')
@handle_service_errors
def get_customer(customer_id):
    customer = CustomerService.get_customer_by_id(customer_id)
    if customer:
        return jsonify(customer)
    return jsonify({'error': '客户不存在'}), 404


@customer_bp.route('/customers', methods=['POST'])
@require_permission('customer', 'edit')
@handle_service_errors
def create_customer():
    data = request.get_json(silent=True) or {}
    customer = CustomerService.create_customer(
        name=data.get('name'),
        short_name=data.get('short_name'),
        contact=data.get('contact'),
        phone=data.get('phone'),
        address=data.get('address'),
        remark=data.get('remark'),
    )
    return jsonify(customer), 201


@customer_bp.route('/customers/<int:customer_id>', methods=['PUT'])
@require_permission('customer', 'edit')
@handle_service_errors
def update_customer(customer_id):
    data = request.get_json(silent=True) or {}
    customer = CustomerService.update_customer(customer_id, data)
    if customer:
        return jsonify(customer)
    return jsonify({'error': '客户不存在'}), 404


@customer_bp.route('/customers/<int:customer_id>', methods=['DELETE'])
@require_permission('customer', 'edit')
@handle_service_errors
def delete_customer(customer_id):
    ok, msg = CustomerService.delete_customer(customer_id)
    if ok:
        return jsonify({'message': '客户已删除'})
    return jsonify({'error': msg}), 400
