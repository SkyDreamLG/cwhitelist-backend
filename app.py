#!/usr/bin/env python3
"""
CWhitelist 后端管理系统
"""

import os
from pathlib import Path

from flask import Flask, g, request, jsonify
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
    return User.query.get(int(user_id))


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


# 应用启动时初始化配置
def before_first_request():
    """第一次请求前初始化配置"""
    # 初始化文件夹
    folders = [
        app.config['UPLOAD_FOLDER'],
        os.path.dirname(app.config['LOG_FILE']),
        app.instance_path
    ]

    for folder in folders:
        Path(folder).mkdir(parents=True, exist_ok=True)

    # 从数据库加载时区设置
    try:
        from models.setting import Setting
        from models.database import db

        # 检查数据库连接
        with app.app_context():
            # 确保表存在
            db.create_all()

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
        print(f"⚠ 加载数据库时区设置失败: {e}")
        print(f"  使用配置时区: {app.config['TIMEZONE']}")


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

if __name__ == '__main__':
    # 启动前初始化
    with app.app_context():
        db.create_all()
        print("数据库表已创建完成")

        # 检查是否需要OOBE
        from routes.web import is_oobe_required

        if is_oobe_required():
            print("\n⚠  系统需要初始设置")
            print("请访问: http://localhost:5000/oebe")
        else:
            print("✓ 系统已初始化")

        print(f"时区设置: {app.config.get('TIMEZONE', 'UTC')}")

    app.run(host='0.0.0.0', port=5000, debug=False)