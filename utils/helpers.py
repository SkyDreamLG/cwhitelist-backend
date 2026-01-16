import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

from models.database import db
from models.user import User
from models.setting import Setting


def is_oobe_required():
    """检查是否需要OOBE设置"""
    # 检查是否有管理员用户
    admin_exists = User.query.filter_by(role='admin').first() is not None

    # 检查必要设置是否存在
    required_settings = ['app_name', 'site_title', 'admin_email']
    settings_exist = all(
        Setting.query.filter_by(key=key).first() is not None
        for key in required_settings
    )

    return not (admin_exists and settings_exist)


def setup_oobe(admin_email, admin_password, site_title, database_type='sqlite', database_url=None):
    """执行OOBE设置"""
    try:
        # 创建管理员用户（如果不存在）
        admin = User.query.filter_by(email=admin_email).first()
        if not admin:
            admin = User(
                username='admin',
                email=admin_email,
                role='admin',
                is_active=True
            )
            admin.set_password(admin_password)
            db.session.add(admin)

        # 保存设置
        Setting.set_value('admin_email', admin_email, '管理员邮箱', 'system')
        Setting.set_value('site_title', site_title, '站点标题', 'system')
        Setting.set_value('app_name', 'CWhitelist', '应用名称', 'system')
        Setting.set_value('database_type', database_type, '数据库类型', 'system')

        if database_url:
            Setting.set_value('database_url', database_url, '数据库连接URL', 'system')

        # 设置默认值
        default_settings = [
            ('registration_enabled', 'false', '允许用户注册', 'security'),
            ('require_auth', 'true', 'API需要认证', 'security'),
            ('log_retention_days', '30', '日志保留天数', 'logging'),
            ('sync_interval', '5', '同步间隔（分钟）', 'sync'),
            ('max_login_attempts', '5', '最大登录尝试次数', 'security'),
            ('session_timeout', '60', '会话超时（分钟）', 'security'),
        ]

        for key, value, description, category in default_settings:
            Setting.set_value(key, value, description, category)

        db.session.commit()

        return {
            'success': True,
            'message': 'OOBE setup completed'
        }

    except Exception as e:
        db.session.rollback()
        return {
            'success': False,
            'message': str(e)
        }


def get_pagination(page, per_page, total):
    """生成分页信息"""
    return {
        'page': page,
        'per_page': per_page,
        'total': total,
        'pages': (total + per_page - 1) // per_page,
        'has_prev': page > 1,
        'has_next': page * per_page < total
    }


def format_datetime(dt, format_str='%Y-%m-%d %H:%M:%S'):
    """格式化日期时间"""
    if not dt:
        return ''
    return dt.strftime(format_str)


def human_readable_size(size_bytes):
    """将字节数转换为人类可读的大小"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def generate_hash(data):
    """生成数据的哈希值"""
    if isinstance(data, dict):
        data = json.dumps(data, sort_keys=True)

    return hashlib.sha256(data.encode()).hexdigest()


def sanitize_filename(filename):
    """清理文件名，移除不安全字符"""
    import re
    # 移除不安全的字符
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # 限制长度
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:255 - len(ext)] + ext
    return filename