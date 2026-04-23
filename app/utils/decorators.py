"""认证装饰器"""
from functools import wraps
from flask import jsonify
from flask_login import current_user


def login_required_api(f):
    """API 接口登录验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({
                'success': False,
                'message': '未登录或登录已过期',
                'data': None
            }), 401
        return f(*args, **kwargs)
    return decorated_function
