# app.py - 修改数据库初始化部分

# !/usr/bin/env python3
"""
CWhitelist 后端管理系统
"""

import os
from pathlib import Path

from flask import Flask, g, request, jsonify, redirect
from flask_login import LoginManager

# 创建应用实例
app = Flask(__name__)

# 加载配置
config_class = os.environ.get('FLASK_CONFIG', 'config.DevelopmentConfig')
app.config.from_object(config_class)

# 确保实例文件夹存在
instance_path = Path(app.instance_path)
instance_path.mkdir(exist_ok=True)

# 初始化数据库
from models.database import db

db.init_app(app)

# 初始化数据库迁移
from flask_migrate import Migrate

migrate = Migrate(app, db)

# 初始化登录管理器
login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = '请先登录以访问此页面'


# 用户加载函数
@login_manager.user_loader
def load_user(user_id):
    from models.user import User
    # 如果表不存在，返回None
    try:
        return User.query.get(int(user_id))
    except:
        return None


# 注册上下文处理器，使时区函数在模板中可用
@app.context_processor
def inject_timezone():
    from utils.timezone import (
        format_datetime,
        get_timezone_info,
        get_common_timezones,
        get_app_timezone,
        now_utc
    )
    return dict(
        format_datetime=format_datetime,
        timezone_info=get_timezone_info(),
        common_timezones=get_common_timezones(),
        current_timezone=str(get_app_timezone()),
        now_utc=now_utc
    )


# 在请求前设置时区
@app.before_request
def before_request():
    from utils.timezone import get_app_timezone
    g.timezone = get_app_timezone()
    g.timezone_str = str(g.timezone)


# 修复OOBE检查函数
@app.context_processor
def inject_oobe_status():
    """注入OOBE状态到所有模板"""

    def check_oobe_required():
        """检查是否需要OOBE设置"""
        try:
            from models.user import User
            from models.setting import Setting
            from models.database import db

            # 检查表是否存在
            from sqlalchemy import inspect
            inspector = inspect(db.engine)

            # 如果users表不存在，需要OOBE
            if 'users' not in inspector.get_table_names():
                return True

            # 检查是否有管理员用户
            admin_exists = User.query.filter_by(role='admin').first() is not None

            # 如果users表存在但没有管理员，需要OOBE
            if not admin_exists:
                return True

            # 检查必要设置是否存在
            required_settings = ['site_title', 'admin_email']
            settings_exist = True
            for key in required_settings:
                if not Setting.query.filter_by(key=key).first():
                    settings_exist = False
                    break

            return not settings_exist

        except Exception as e:
            # 如果查询出错，说明数据库可能还没初始化，需要OOBE
            print(f"OOBE检查出错: {e}")
            return True

    return dict(is_oobe_required=check_oobe_required)


# 应用启动时初始化配置
def initialize_database():
    """初始化数据库"""
    with app.app_context():
        try:
            # 创建所有表
            db.create_all()
            print("✓ 数据库表已创建完成")

            # 从数据库加载时区设置
            from models.setting import Setting

            # 检查数据库连接
            # 从数据库获取时区设置，如果存在则覆盖配置
            timezone_setting = Setting.query.filter_by(key='timezone').first()
            if timezone_setting and timezone_setting.value:
                app.config['TIMEZONE'] = timezone_setting.value
                print(f"✓ 已从数据库加载时区设置: {timezone_setting.value}")
            else:
                # 保存默认时区到数据库
                Setting.set_value('timezone', app.config['TIMEZONE'], '系统时区设置', 'system')
                print(f"✓ 已保存默认时区到数据库: {app.config['TIMEZONE']}")

        except Exception as e:
            print(f"⚠ 数据库初始化失败: {e}")
            print(f"  请手动运行数据库迁移命令")


# 添加时区刷新端点（用于AJAX更新）
@app.route('/api/timezone/refresh')
def refresh_timezone():
    """刷新时区设置"""
    from utils.timezone import get_timezone_info
    try:
        info = get_timezone_info()
        return jsonify({
            'success': True,
            'timezone_info': info
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


# 注册蓝图
from routes.auth import auth_bp
from routes.api import api_bp
from routes.web import web_bp

# 确保只注册一次
app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(api_bp, url_prefix='/api')
app.register_blueprint(web_bp, url_prefix='/')


@app.route('/')
def index():
    """首页"""
    # 使用注入的函数检查OOBE状态
    try:
        from sqlalchemy import inspect
        inspector = inspect(db.engine)

        # 如果users表不存在，重定向到OOBE
        if 'users' not in inspector.get_table_names():
            print("检测到数据库未初始化，重定向到OOBE")
            return redirect('/oobe')
    except:
        pass

    return redirect('/auth/login')


if __name__ == '__main__':
    # 启动前初始化
    initialize_database()

    print(f"\n=== CWhitelist 后端管理系统 ===")
    print(f"时区设置: {app.config.get('TIMEZONE', 'UTC')}")
    print(f"访问地址: http://127.0.0.1:5000")
    print(f"================================\n")

    app.run(host='0.0.0.0', port=5000, debug=True)