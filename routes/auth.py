from collections import OrderedDict
from flask import Blueprint, request, jsonify, session
from services.auth_service import AuthService
from services.permission_service import PermissionService
from datetime import datetime, timedelta

auth_bp = Blueprint('auth', __name__)


class LRUDict:
    """带容量上限的 LRU 字典, 防止限流场景下长期运行内存累积"""

    def __init__(self, maxsize):
        self.data = OrderedDict()
        self.maxsize = maxsize

    def get(self, key, default=None):
        if key not in self.data:
            return default
        self.data.move_to_end(key)
        return self.data[key]

    def __getitem__(self, key):
        if key not in self.data:
            raise KeyError(key)
        self.data.move_to_end(key)
        return self.data[key]

    def __setitem__(self, key, value):
        if key in self.data:
            self.data.move_to_end(key)
        self.data[key] = value
        if len(self.data) > self.maxsize:
            self.data.popitem(last=False)

    def pop(self, key, default=None):
        return self.data.pop(key, default)

    def __contains__(self, key):
        return key in self.data

    def __len__(self):
        return len(self.data)


# Rate limiting: LRUDict 防止不同 IP/账号扫描累积
RATE_LIMIT_MAXSIZE = 10000
_login_attempts = LRUDict(RATE_LIMIT_MAXSIZE)
_account_attempts = LRUDict(RATE_LIMIT_MAXSIZE)
MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

def _check_rate_limit(ip):
    now = datetime.now()
    if ip in _login_attempts:
        count, lockout_until = _login_attempts[ip]
        if lockout_until and now < lockout_until:
            return False, int((lockout_until - now).total_seconds())
        if lockout_until and now >= lockout_until:
            _login_attempts[ip] = [0, None]
    return True, 0

def _check_account_lock(username):
    now = datetime.now()
    if username in _account_attempts:
        count, lockout_until = _account_attempts[username]
        if lockout_until and now < lockout_until:
            return False, int((lockout_until - now).total_seconds())
        if lockout_until and now >= lockout_until:
            _account_attempts[username] = [0, None]
    return True, 0

def _record_failure(ip, username):
    now = datetime.now()
    # IP
    if ip not in _login_attempts:
        _login_attempts[ip] = [1, None]
    else:
        count, _ = _login_attempts[ip]
        count += 1
        if count >= MAX_ATTEMPTS:
            _login_attempts[ip] = [count, now + timedelta(minutes=LOCKOUT_MINUTES)]
        else:
            _login_attempts[ip] = [count, None]
    # Account
    if username not in _account_attempts:
        _account_attempts[username] = [1, None]
    else:
        count, _ = _account_attempts[username]
        count += 1
        if count >= MAX_ATTEMPTS:
            _account_attempts[username] = [count, now + timedelta(minutes=LOCKOUT_MINUTES)]
        else:
            _account_attempts[username] = [count, None]

def _clear_failures(ip, username):
    _login_attempts.pop(ip, None)
    _account_attempts.pop(username, None)

@auth_bp.route('/login', methods=['POST'])
def login():
    ip = request.remote_addr
    allowed, wait_seconds = _check_rate_limit(ip)
    if not allowed:
        return jsonify({'error': f'登录失败次数过多，请 {wait_seconds} 秒后重试'}), 429

    data = request.get_json(silent=True) or {}
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400

    allowed, wait_seconds = _check_account_lock(username)
    if not allowed:
        return jsonify({'error': f'该账号已锁定，请 {wait_seconds} 秒后重试'}), 429

    user = AuthService.authenticate(username, password)
    if user:
        _clear_failures(ip, username)
        session['user_id'] = user['id']
        session['username'] = user['username']
        perms = PermissionService.get_user_permissions(user['id'])
        session['permissions'] = [list(p) for p in perms]
        return jsonify({
            'id': user['id'],
            'username': user['username'],
            'permissions': session['permissions']
        })
    _record_failure(ip, username)
    return jsonify({'error': '用户名或密码错误'}), 401

@auth_bp.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': '退出成功'})

@auth_bp.route('/current_user', methods=['GET'])
def current_user():
    if 'user_id' in session:
        return jsonify({
            'id': session['user_id'],
            'username': session['username'],
            'permissions': session.get('permissions', [])
        })
    return jsonify({'error': '未登录'}), 401

@auth_bp.route('/change_password', methods=['POST'])
def change_password():
    if 'user_id' not in session:
        return jsonify({'error': '未登录'}), 401

    data = request.get_json(silent=True) or {}
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
