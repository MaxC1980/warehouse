from flask import Blueprint, request, jsonify, session
from services.permission_service import PermissionService
from utils.decorators import require_permission
from database import get_db_connection

admin_bp = Blueprint('admin', __name__)
admin_page_bp = Blueprint('admin_page', __name__)


@admin_bp.route('/admin/roles', methods=['GET'])
@require_permission('admin_role', 'manage')
def get_roles():
    roles = PermissionService.get_all_roles()
    for role in roles:
        role['permissions'] = PermissionService.get_role_permissions(role['id'])
    return jsonify(roles)


@admin_bp.route('/admin/roles', methods=['POST'])
@require_permission('admin_role', 'manage')
def create_role():
    data = request.get_json()
    name = data.get('name')
    description = data.get('description', '')
    permission_ids = data.get('permission_ids', [])

    if not name:
        return jsonify({'error': '请填写角色名称'}), 400

    try:
        role_id = PermissionService.create_role(name, description, permission_ids)
        return jsonify({'id': role_id, 'message': '角色创建成功'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@admin_bp.route('/admin/roles/<int:role_id>', methods=['PUT'])
@require_permission('admin_role', 'manage')
def update_role(role_id):
    data = request.get_json()
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
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400
    if len(password) < 6:
        return jsonify({'error': '密码长度不能少于6位'}), 400

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM user WHERE username = ?", (username,))
        if cursor.fetchone():
            return jsonify({'error': '用户名已存在'}), 400

        cursor.execute(
            "INSERT INTO user (username, password) VALUES (?, ?)",
            (username, password)
        )
        user_id = cursor.lastrowid

        # 默认分配查看员角色
        cursor.execute("SELECT id FROM role WHERE name = '查看员'")
        viewer_role = cursor.fetchone()
        if viewer_role:
            cursor.execute(
                "INSERT INTO user_role (user_id, role_id) VALUES (?, ?)",
                (user_id, viewer_role['id'])
            )
        conn.commit()

    return jsonify({'id': user_id, 'message': '用户创建成功'}), 201


@admin_bp.route('/admin/users/<int:user_id>', methods=['DELETE'])
@require_permission('admin_user', 'manage')
def delete_user(user_id):
    # 不能删除自己
    if session.get('user_id') == user_id:
        return jsonify({'error': '不能删除当前登录用户'}), 400

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username FROM user WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            return jsonify({'error': '用户不存在'}), 404
        if user['username'] == 'admin':
            return jsonify({'error': '不能删除管理员账号'}), 400

        cursor.execute("DELETE FROM user_role WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM user WHERE id = ?", (user_id,))
        conn.commit()

    return jsonify({'message': '用户删除成功'})


@admin_bp.route('/admin/users/<int:user_id>/password', methods=['PUT'])
@require_permission('admin_user', 'manage')
def reset_user_password(user_id):
    data = request.get_json()
    new_password = data.get('new_password', '').strip()

    if not new_password:
        return jsonify({'error': '新密码不能为空'}), 400
    if len(new_password) < 6:
        return jsonify({'error': '密码长度不能少于6位'}), 400

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM user WHERE id = ?", (user_id,))
        if not cursor.fetchone():
            return jsonify({'error': '用户不存在'}), 404

        cursor.execute("UPDATE user SET password = ? WHERE id = ?", (new_password, user_id))
        conn.commit()

    return jsonify({'message': '密码重置成功'})


@admin_bp.route('/admin/users/<int:user_id>/roles', methods=['PUT'])
@require_permission('admin_user', 'manage')
def update_user_roles(user_id):
    data = request.get_json()
    role_ids = data.get('role_ids', [])

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM user WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if user and user['username'] == 'admin':
            return jsonify({'error': '不能修改管理员角色'}), 400

        cursor.execute("DELETE FROM user_role WHERE user_id = ?", (user_id,))
        for role_id in role_ids:
            cursor.execute(
                "INSERT INTO user_role (user_id, role_id) VALUES (?, ?)",
                (user_id, role_id)
            )
        conn.commit()

    # 更新 session 中的权限（如果是当前用户）
    if session.get('user_id') == user_id:
        perms = PermissionService.get_user_permissions(user_id)
        session['permissions'] = [list(p) for p in perms]

    return jsonify({'message': '用户角色更新成功'})


@admin_page_bp.route('/admin/roles-page')
@require_permission('admin_role', 'manage')
def roles_page():
    from flask import render_template
    return render_template('admin_roles.html')


@admin_page_bp.route('/admin/users-page')
@require_permission('admin_user', 'manage')
def users_page():
    from flask import render_template
    return render_template('admin_users.html')
