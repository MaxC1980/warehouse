from flask import Blueprint, request, jsonify
from services.employee_service import EmployeeService

employee_bp = Blueprint('employee', __name__)

@employee_bp.route('/employees', methods=['GET'])
def get_employees():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
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
def get_employee(employee_id):
    employee = EmployeeService.get_employee_by_id(employee_id)
    if employee:
        return jsonify(employee)
    return jsonify({'error': 'Employee not found'}), 404

@employee_bp.route('/employees', methods=['POST'])
def create_employee():
    data = request.get_json()
    employee = EmployeeService.create_employee(
        name=data.get('name'),
        department=data.get('department'),
        phone=data.get('phone'),
        remark=data.get('remark')
    )
    return jsonify(employee), 201

@employee_bp.route('/employees/<int:employee_id>', methods=['PUT'])
def update_employee(employee_id):
    data = request.get_json()
    employee = EmployeeService.update_employee(
        employee_id,
        name=data.get('name'),
        department=data.get('department'),
        phone=data.get('phone'),
        remark=data.get('remark')
    )
    if employee:
        return jsonify(employee)
    return jsonify({'error': 'Employee not found'}), 404

@employee_bp.route('/employees/<int:employee_id>', methods=['DELETE'])
def delete_employee(employee_id):
    success = EmployeeService.delete_employee(employee_id)
    if success:
        return jsonify({'message': 'Employee deleted'})
    return jsonify({'error': 'Employee not found'}), 404
