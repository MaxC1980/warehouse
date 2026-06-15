import logging
from flask import Blueprint, request, jsonify, session, render_template
from services.permission_service import PermissionService
from services.user_service import UserService
from utils.decorators import require_permission
from database import get_db_connection

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__)
admin_page_bp = Blueprint('admin_page', __name__)


@admin_bp.route('/admin/roles', methods=['GET'])
@require_permission('admin_role', 'manage')
def get_roles():
    return jsonify(PermissionService.get_all_roles_with_permissions())


@admin_bp.route('/admin/roles', methods=['POST'])
@require_permission('admin_role', 'manage')
def create_role():
    data = request.get_json(silent=True) or {}
    name = data.get('name')
    description = data.get('description', '')
    permission_ids = data.get('permission_ids', [])

    if not name:
        return jsonify({'error': '请填写角色名称'}), 400

    try:
        role_id = PermissionService.create_role(name, description, permission_ids)
        return jsonify({'id': role_id, 'message': '角色创建成功'}), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception:
        logger.exception('创建角色失败')
        return jsonify({'error': '创建角色失败'}), 500


@admin_bp.route('/admin/roles/<int:role_id>', methods=['PUT'])
@require_permission('admin_role', 'manage')
def update_role(role_id):
    data = request.get_json(silent=True) or {}
    name = data.get('name')
    description = data.get('description', '')
    permission_ids = data.get('permission_ids', [])

    if not name:
        return jsonify({'error': '请填写角色名称'}), 400

    try:
        PermissionService.update_role(role_id, name, description, permission_ids)
        return jsonify({'message': '角色更新成功'})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@admin_bp.route('/admin/roles/<int:role_id>', methods=['DELETE'])
@require_permission('admin_role', 'manage')
def delete_role(role_id):
    try:
        PermissionService.delete_role(role_id)
        return jsonify({'message': '角色删除成功'})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@admin_bp.route('/admin/permissions', methods=['GET'])
@require_permission('admin_role', 'manage')
def get_permissions():
    perms = PermissionService.get_all_permissions()
    return jsonify(perms)


@admin_bp.route('/admin/users', methods=['GET'])
@require_permission('admin_user', 'manage')
def get_users():
    users = PermissionService.get_users_with_roles()
    return jsonify(users)


@admin_bp.route('/admin/users', methods=['POST'])
@require_permission('admin_user', 'manage')
def create_user():
    data = request.get_json(silent=True) or {}
    username = data.get('username')
    password = data.get('password')
    try:
        user_id = UserService.create_user(username, password)
        return jsonify({'id': user_id, 'message': '用户创建成功'}), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception:
        logger.exception('创建用户失败')
        return jsonify({'error': '创建用户失败'}), 500


@admin_bp.route('/admin/users/<int:user_id>', methods=['DELETE'])
@require_permission('admin_user', 'manage')
def delete_user(user_id):
    try:
        UserService.delete_user(user_id, session.get('user_id'))
        return jsonify({'message': '用户删除成功'})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception:
        logger.exception('删除用户失败')
        return jsonify({'error': '删除用户失败'}), 500


@admin_bp.route('/admin/users/<int:user_id>/password', methods=['PUT'])
@require_permission('admin_user', 'manage')
def reset_user_password(user_id):
    data = request.get_json(silent=True) or {}
    new_password = data.get('new_password')
    try:
        UserService.reset_password(user_id, new_password)
        return jsonify({'message': '密码重置成功'})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception:
        logger.exception('重置密码失败')
        return jsonify({'error': '重置密码失败'}), 500


@admin_bp.route('/admin/users/<int:user_id>/roles', methods=['PUT'])
@require_permission('admin_user', 'manage')
def update_user_roles(user_id):
    data = request.get_json(silent=True) or {}
    role_ids = data.get('role_ids', [])
    try:
        UserService.update_user_roles(user_id, role_ids)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception:
        logger.exception('更新用户角色失败')
        return jsonify({'error': '更新用户角色失败'}), 500

    # 更新 session 中的权限（如果是当前用户）
    if session.get('user_id') == user_id:
        perms = PermissionService.get_user_permissions(user_id)
        session['permissions'] = [list(p) for p in perms]

    return jsonify({'message': '用户角色更新成功'})


@admin_page_bp.route('/admin/roles-page')
@require_permission('admin_role', 'manage')
def roles_page():
    return render_template('admin_roles.html')


@admin_page_bp.route('/admin/users-page')
@require_permission('admin_user', 'manage')
def users_page():
    return render_template('admin_users.html')
