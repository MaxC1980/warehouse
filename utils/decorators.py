from functools import wraps
from flask import session, jsonify
from services.permission_service import PermissionService


def require_permission(module, action):
    """检查当前用户是否有指定权限，无权限返回 403"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': '未登录'}), 401
            if not PermissionService.has_permission(user_id, module, action):
                return jsonify({'error': '无权限'}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator
