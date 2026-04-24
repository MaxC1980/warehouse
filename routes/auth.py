from flask import Blueprint, request, jsonify, session
from services.auth_service import AuthService

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400

    user = AuthService.authenticate(username, password)
    if user:
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['permission_level'] = user.get('permission_level', 1)
        return jsonify({
            'id': user['id'],
            'username': user['username'],
            'permission_level': user.get('permission_level', 1)
        })
    return jsonify({'error': 'Invalid credentials'}), 401

@auth_bp.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Logged out successfully'})

@auth_bp.route('/current_user', methods=['GET'])
def current_user():
    if 'user_id' in session:
        return jsonify({
            'id': session['user_id'],
            'username': session['username'],
            'permission_level': session.get('permission_level', 1)
        })
    return jsonify({'error': 'Not logged in'}), 401

@auth_bp.route('/change_password', methods=['POST'])
def change_password():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.get_json()
    old_password = data.get('old_password')
    new_password = data.get('new_password')

    if not old_password or not new_password:
        return jsonify({'error': '旧密码和新密码都不能为空'}), 400

    if len(new_password) < 6:
        return jsonify({'error': '新密码长度不能少于6位'}), 400

    success, error = AuthService.change_password(session['user_id'], old_password, new_password)
    if success:
        return jsonify({'message': '密码修改成功'})
    else:
        return jsonify({'error': error}), 400
