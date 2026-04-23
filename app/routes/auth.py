"""认证路由"""
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_user, logout_user, current_user

from app.models import User
from app.utils.logger import log_operation
from app.utils.decorators import login_required_api
from app.utils.response import from_service_result, api_error

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET'])
def check_login():
    """检查登录状态"""
    if current_user.is_authenticated:
        return from_service_result({
            'success': True,
            'message': 'ok',
            'data': {'username': current_user.username}
        })
    return api_error('未登录', 401)


@auth_bp.route('/login', methods=['POST'])
def login():
    """登录"""
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return api_error('用户名和密码不能为空', 400)

    user = User.authenticate(username, password)
    if user:
        login_user(user, remember=True)
        if current_app.operations_logger:
            log_operation(current_app.operations_logger, 'LOGIN', username, '登录成功', '成功')
        return from_service_result({
            'success': True,
            'message': 'ok',
            'data': {'username': user.username}
        })

    if current_app.operations_logger:
        log_operation(current_app.operations_logger, 'LOGIN_FAIL', username, '登录失败', '失败')
    return api_error('用户名或密码错误', 401)


@auth_bp.route('/logout', methods=['POST'])
@login_required_api
def logout():
    """登出"""
    username = current_user.username if current_user.is_authenticated else 'unknown'
    logout_user()
    if current_app.operations_logger:
        log_operation(current_app.operations_logger, 'LOGOUT', username, '登出', '成功')
    return from_service_result({
        'success': True,
        'message': 'ok',
        'data': None
    })
