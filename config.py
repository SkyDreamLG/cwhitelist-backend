# config.py
import os
import secrets
from datetime import timedelta
from pathlib import Path

# 开关：True=开发环境，False=生产环境
DEV_MODE = False

# PyInstaller 打包后使用 exe 所在目录作为基准路径，确保数据持久化
import sys as _sys
if getattr(_sys, 'frozen', False):
    _BASE_DIR = Path(_sys.executable).parent
else:
    _BASE_DIR = Path(__file__).parent
_INSTANCE_DIR = _BASE_DIR / 'instance'
_KEY_FILE = _INSTANCE_DIR / 'secret_key'


def _load_secret_key():
    """加载 SECRET_KEY：环境变量 > 持久化文件 > 自动生成并持久化"""
    env_key = os.environ.get('SECRET_KEY')
    if env_key:
        return env_key

    if _KEY_FILE.exists():
        return _KEY_FILE.read_text().strip()

    _INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    new_key = secrets.token_hex(32)
    _KEY_FILE.write_text(new_key)
    return new_key


class Config:
    """基础配置"""
    SECRET_KEY = _load_secret_key()
    DEV_MODE = DEV_MODE

    # 时区
    TIMEZONE = os.environ.get('TIMEZONE', 'Asia/Shanghai')

    # 多语言
    LANGUAGES = {
        'zh_CN': '简体中文',
        'en': 'English',
    }
    BABEL_DEFAULT_LOCALE = 'zh_CN'
    BABEL_TRANSLATION_DIRECTORIES = 'translations'

    # 数据库
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + str(_INSTANCE_DIR / 'cwhitelist.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 调试
    DEBUG = DEV_MODE

    # 会话
    SESSION_TYPE = 'filesystem'
    SESSION_PERMANENT = False
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=60)

    # API
    API_PREFIX = '/api'
    API_VERSION = 'v1'
    APP_VERSION = '2.3.0'
    JSON_SORT_KEYS = False

    # 文件上传
    UPLOAD_FOLDER = str(_BASE_DIR / 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    # 日志
    LOG_FILE = 'logs/app.log'
    LOG_LEVEL = 'INFO'

    # CORS - 从环境变量读取，逗号分隔，默认仅同源
    _cors_env = os.environ.get('CORS_ORIGINS', '')
    CORS_ORIGINS = [o.strip() for o in _cors_env.split(',') if o.strip()] if _cors_env else []

    # 缓存
    CACHE_TYPE = 'simple'
    CACHE_DEFAULT_TIMEOUT = 300

    # JWT
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or SECRET_KEY
    JWT_ALGORITHM = 'HS256'
    JWT_EXPIRATION_HOURS = 24

    # API 速率限制
    API_RATE_LIMIT = '1000/hour'

    # Cookie 安全 - 生产环境启用
    SESSION_COOKIE_SECURE = not DEV_MODE
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # 速率限制存储
    RATELIMIT_STORAGE_URL = 'memory://'


class DevelopmentConfig(Config):
    pass


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False


class ProductionConfig(Config):
    pass


config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
