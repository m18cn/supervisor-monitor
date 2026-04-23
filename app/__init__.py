"""Flask 应用工厂"""
from flask import Flask, render_template, request, jsonify
from flask_login import LoginManager
from pathlib import Path

from app.config import config
from app.utils.logger import setup_logger


def create_app(config_name=None):
    """创建 Flask 应用"""
    root_path = Path(__file__).resolve().parent.parent
    app = Flask(__name__,
                static_folder=str(root_path / 'static'),
                template_folder=str(root_path / 'templates'))
    cfg = config.get(config_name or 'default', config['default'])
    app.config.from_object(cfg)
    try:
        app.operations_logger = setup_logger(
            Path(app.config['LOG_DIR']),
            'operations.log'
        )
    except Exception:
        app.operations_logger = None
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.session_protection = 'strong'
    
    from app.models import User
    @login_manager.user_loader
    def load_user(user_id):
        return User.get(user_id)
    from app.routes.api import api_bp
    from app.routes.auth import auth_bp
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(auth_bp, url_prefix='/api')

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'message': '接口不存在', 'data': None}), 404
        return e.get_response() if hasattr(e, 'get_response') else ('Not Found', 404)
    
    @app.errorhandler(500)
    def server_error(e):
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'message': '服务器错误', 'data': None}), 500
        return e.get_response() if hasattr(e, 'get_response') else ('Server Error', 500)
    
    return app
