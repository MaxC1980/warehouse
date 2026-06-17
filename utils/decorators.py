import logging
from functools import wraps
from flask import session, jsonify, redirect, url_for, request

logger = logging.getLogger(__name__)


def _is_api_request():
    """判断是否 API 请求: /api/* 路径或带 JSON Content-Type"""
    return request.path.startswith('/api/') or request.is_json


def _unauth_response():
    """未登录的统一处理: API 请求返 JSON 401, 页面请求跳 /login"""
    if _is_api_request():
        return jsonify({'error': '未登录'}), 401
    return redirect(url_for('pages.login'))


def require_permission(module, action):
    """检查当前用户是否有指定权限，无权限返回 403

    从 session.permissions 查 (登录时已缓存, 见 auth_service),
    不再走 DB, 避免每次 API 请求多一次连接和 3 表 JOIN。
    权限变更后需重新登录生效 (见 docs/代码质量改进记录.md §30)。

    同时支持 API 和页面路由: API 请求 (Content-Type: application/json)
    返 JSON 错误, 页面请求 (浏览器导航) 跳 /login。
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user_id' not in session:
                return _unauth_response()
            perms = {tuple(p) for p in session.get('permissions', [])}
            if (module, action) not in perms:
                if _is_api_request():
                    return jsonify({'error': '无权限'}), 403
                return redirect(url_for('pages.login'))
            return f(*args, **kwargs)
        return decorated
    return decorator


def login_required(f):
    """页面路由登录校验: 未登录跳 /login (API 请求返 401 JSON)"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json:
                return jsonify({'error': '未登录'}), 401
            return redirect(url_for('pages.login'))
        return f(*args, **kwargs)
    return decorated


def handle_service_errors(f):
    """API 路由统一错误处理: ValueError→400, Exception→500+logger

    替代每个端点手写 try/except, 减少重复, 统一风格。
    应放在 @require_permission 之后 (最内层装饰器优先执行)。
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception:
            logger.exception(f'{f.__name__} 失败')
            return jsonify({'error': '服务器内部错误'}), 500
    return decorated
