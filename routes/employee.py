from flask import Blueprint, request, jsonify
from services.employee_service import EmployeeService
from utils.decorators import require_permission, handle_service_errors
from utils.pagination import get_per_page

employee_bp = Blueprint('employee', __name__)

@employee_bp.route('/employees', methods=['GET'])
@require_permission('employee', 'view')
@handle_service_errors
def get_employees():
    page = request.args.get('page', 1, type=int)
    per_page = get_per_page()
    keyword = request.args.get('keyword')

    employees, total = EmployeeService.get_all_employees(
        page=page,
        per_page=per_page,
        keyword=keyword
    )
    return jsonify({
        'items': employees,
        'total': total,
        'page': page,
        'per_page': per_page
    })

@employee_bp.route('/employees/<int:employee_id>', methods=['GET'])
@require_permission('employee', 'view')
@handle_service_errors
def get_employee(employee_id):
    employee = EmployeeService.get_employee_by_id(employee_id)
    if employee:
        return jsonify(employee)
    return jsonify({'error': '员工不存在'}), 404

@employee_bp.route('/employees', methods=['POST'])
@require_permission('employee', 'edit')
@handle_service_errors
def create_employee():
    data = request.get_json(silent=True) or {}
    employee = EmployeeService.create_employee(
        name=data.get('name'),
        department=data.get('department'),
        phone=data.get('phone'),
        remark=data.get('remark')
    )
    return jsonify(employee), 201

@employee_bp.route('/employees/<int:employee_id>', methods=['PUT'])
@require_permission('employee', 'edit')
@handle_service_errors
def update_employee(employee_id):
    data = request.get_json(silent=True) or {}
    employee = EmployeeService.update_employee(employee_id, data)
    if employee:
        return jsonify(employee)
    return jsonify({'error': '员工不存在'}), 404

@employee_bp.route('/employees/<int:employee_id>', methods=['DELETE'])
@require_permission('employee', 'edit')
@handle_service_errors
def delete_employee(employee_id):
    success = EmployeeService.delete_employee(employee_id)
    if success:
        return jsonify({'message': '员工已删除'})
    return jsonify({'error': '员工不存在'}), 404
