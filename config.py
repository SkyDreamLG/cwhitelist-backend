# config.py
import os
from datetime import timedelta
from pathlib import Path


class Config:
    """基础配置类"""
    # 安全设置 - 提供默认值
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'

    # 时区配置
    TIMEZONE = os.environ.get('TIMEZONE', 'UTC')  # 默认UTC

    # 数据库配置
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
                              'sqlite:///' + os.path.join(Path(__file__).parent, 'instance', 'cwhitelist.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 会话配置
    SESSION_TYPE = 'filesystem'
    SESSION_PERMANENT = False
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=60)

    # API配置
    API_PREFIX = '/api'
    API_VERSION = 'v1'
    JSON_SORT_KEYS = False

    # 文件上传
    UPLOAD_FOLDER = os.path.join(Path(__file__).parent, 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB

    # 日志配置
    LOG_FILE = 'logs/app.log'
    LOG_LEVEL = 'INFO'

    # CORS配置
    CORS_ORIGINS = ['*']

    # 缓存配置
    CACHE_TYPE = 'simple'
    CACHE_DEFAULT_TIMEOUT = 300

    # 确保上传文件夹存在
    @staticmethod
    def init_app(app):
        # 创建必要的文件夹
        folders = [
            app.config['UPLOAD_FOLDER'],
            os.path.dirname(app.config['LOG_FILE']),
            app.instance_path
        ]

        for folder in folders:
            Path(folder).mkdir(parents=True, exist_ok=True)


class DevelopmentConfig(Config):
    """开发环境配置"""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(Path(__file__).parent, 'instance', 'cwhitelist_dev.db')
    SECRET_KEY = 'dev-secret-key-do-not-use-in-production'
    TIMEZONE = os.environ.get('TIMEZONE', 'Asia/Shanghai')  # 开发环境默认中国时区


class TestingConfig(Config):
    """测试环境配置"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SECRET_KEY = 'test-secret-key'
    WTF_CSRF_ENABLED = False


class ProductionConfig(Config):
    """生产环境配置"""
    DEBUG = False

    # 从环境变量获取密钥
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        # 修改这里：不要直接抛出异常，而是使用默认值或记录警告
        SECRET_KEY = 'dev-secret-key-for-production-use-strong-key'
        print("警告：SECRET_KEY未设置，使用默认值。生产环境请设置SECRET_KEY环境变量。")

    # 时区配置
    TIMEZONE = os.environ.get('TIMEZONE', 'UTC')

    # 数据库配置
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    if not SQLALCHEMY_DATABASE_URI:
        SQLALCHEMY_DATABASE_URI = Config.SQLALCHEMY_DATABASE_URI

    # 安全设置
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # 缓存配置
    CACHE_TYPE = 'redis'
    CACHE_REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

    # 速率限制
    RATELIMIT_STORAGE_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/1')


# 配置映射
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}