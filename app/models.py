"""数据模型"""
from flask_login import UserMixin


class User(UserMixin):
    """用户模型（用于 Flask-Login）"""
    def __init__(self, user_id, username):
        self.id = user_id
        self.username = username
    
    @staticmethod
    def get(user_id):
        """根据 ID 获取用户"""
        from flask import current_app
        admin_user = current_app.config.get('ADMIN_USER')
        if user_id == admin_user:
            return User(admin_user, admin_user)
        return None
    
    @staticmethod
    def authenticate(username, password):
        """验证用户名密码"""
        from flask import current_app
        admin_user = current_app.config.get('ADMIN_USER')
        admin_pass = current_app.config.get('ADMIN_PASSWORD')
        if username == admin_user and password == admin_pass:
            return User(admin_user, admin_user)
        return None
