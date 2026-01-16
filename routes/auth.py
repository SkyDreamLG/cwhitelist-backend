from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_user, logout_user, login_required, current_user

from models.database import db
from models.user import User
from models.log import Log  # 添加这行

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """登录页面"""
    if request.method == 'GET':
        return render_template('auth/login.html')

    # POST请求处理
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    remember = request.form.get('remember', False)

    if not username or not password:
        flash('请输入用户名和密码', 'error')
        return render_template('auth/login.html')

    # 查找用户
    user = User.query.filter(
        (User.username == username) | (User.email == username)
    ).first()

    if not user or not user.check_password(password):
        # 记录登录失败日志
        log = Log(
            level='warning',
            message=f'登录失败: 用户名或密码错误 - {username}',
            source='web',
            ip_address=request.remote_addr,
            details=f'username: {username}'
        )
        db.session.add(log)
        db.session.commit()

        flash('用户名或密码错误', 'error')
        return render_template('auth/login.html')

    if not user.is_active:
        # 记录账户禁用日志
        log = Log(
            level='error',
            message=f'登录失败: 账户已被禁用 - {username}',
            source='web',
            ip_address=request.remote_addr,
            user_id=user.id,
            details=f'username: {username}, user_id: {user.id}'
        )
        db.session.add(log)
        db.session.commit()

        flash('账户已被禁用，请联系管理员', 'error')
        return render_template('auth/login.html')

    # 登录成功
    login_user(user, remember=remember)

    # 记录登录成功日志
    log = Log(
        level='login',
        message=f'用户登录成功: {username}',
        source='web',
        ip_address=request.remote_addr,
        user_id=user.id,
        details=f'username: {username}, user_id: {user.id}'
    )
    db.session.add(log)
    db.session.commit()

    next_page = request.args.get('next')
    if not next_page or not next_page.startswith('/'):
        next_page = url_for('web.dashboard')

    return redirect(next_page)


@auth_bp.route('/logout')
@login_required
def logout():
    """退出登录"""
    # 记录退出登录日志
    log = Log(
        level='info',
        message=f'用户退出登录: {current_user.username}',
        source='web',
        ip_address=request.remote_addr,
        user_id=current_user.id
    )
    db.session.add(log)
    db.session.commit()

    logout_user()
    flash('您已成功退出登录', 'success')
    return redirect(url_for('auth.login'))


@auth_bp.route('/profile')
@login_required
def profile():
    """用户资料页面"""
    return render_template('auth/profile.html', user=current_user)