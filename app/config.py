import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_local_config():
    env_file = BASE_DIR / 'config_local.env'
    if not env_file.exists():
        return
    try:
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, value = line.partition('=')
                    key, value = key.strip(), value.strip()
                    if key and key not in os.environ:
                        os.environ[key] = value
    except Exception:
        pass


_load_local_config()


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'supervisor-monitor-secret-key-change-in-production'
    
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    ADMIN_USER = os.environ.get('ADMIN_USER') or 'admin'
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD') or 'admin123'
    
    SUPERVISOR_RPC_URL = os.environ.get('SUPERVISOR_RPC_URL') or 'http://127.0.0.1:9001/RPC2'
    SUPERVISOR_SOCKET_PATH = os.environ.get('SUPERVISOR_SOCKET_PATH') or None
    SUPERVISOR_CONF_DIR = os.environ.get('SUPERVISOR_CONF_DIR') or '/etc/supervisor/conf.d'
    SUPERVISOR_CONF_EXT = os.environ.get('SUPERVISOR_CONF_EXT') or 'conf'
    SUPERVISOR_USE_SUDO_RM = os.environ.get('SUPERVISOR_USE_SUDO_RM', '').lower() in ('1', 'true', 'yes')
    SUPERVISOR_USE_SUDO_WRITE = os.environ.get('SUPERVISOR_USE_SUDO_WRITE', '').lower() in ('1', 'true', 'yes')
    SUPERVISOR_START_CMD = os.environ.get('SUPERVISOR_START_CMD') or 'sudo systemctl start supervisord'
    SUPERVISOR_STOP_CMD = os.environ.get('SUPERVISOR_STOP_CMD') or 'sudo systemctl stop supervisord'
    SUPERVISOR_RESTART_CMD = os.environ.get('SUPERVISOR_RESTART_CMD') or 'sudo systemctl restart supervisord'
    SUPERVISOR_AUTO_RESTART_ON_FAIL = os.environ.get('SUPERVISOR_AUTO_RESTART_ON_FAIL', '1').lower() in ('1', 'true', 'yes')
    LOG_DIR = BASE_DIR / 'logs'
    LOG_FILE = LOG_DIR / 'operations.log'
    STATUS_POLL_INTERVAL = 4


class DevelopmentConfig(Config):
    """开发环境配置"""
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
