#!/usr/bin/env python3
"""
CWhitelist 后端管理系统
"""

import os
from pathlib import Path

from flask import Flask
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

# 注册蓝图
from routes.auth import auth_bp
from routes.api import api_bp
from routes.web import web_bp

# 确保只注册一次
app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(api_bp, url_prefix='/api')
app.register_blueprint(web_bp, url_prefix='/')

# 创建数据库表（但不创建默认数据）
with app.app_context():
    db.create_all()
    print("数据库表已创建完成")
    print("请访问 http://localhost:5000/oobe 完成系统初始设置")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)