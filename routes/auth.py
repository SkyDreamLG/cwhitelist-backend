from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import login_user, logout_user, login_required, current_user
from flask_babel import _
import time
import threading

from models.database import db
from models.user import User
from models.log import Log

auth_bp = Blueprint('auth', __name__)

# 登录限流：{ip: [(timestamp, success), ...]}
_login_attempts = {}
_login_lock = threading.Lock()

MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 60


def _check_login_rate_limit(ip):
    """检查登录频率限制，返回(是否允许, 剩余秒数)"""
    now = time.time()
    with _login_lock:
        attempts = _login_attempts.get(ip, [])
        # 清理窗口外的记录
        attempts = [a for a in attempts if now - a[0] < LOGIN_WINDOW_SECONDS]
        _login_attempts[ip] = attempts

        # 只统计失败尝试
        failures = [a for a in attempts if not a[1]]
        if len(failures) >= MAX_LOGIN_ATTEMPTS:
            oldest_failure = min(a[0] for a in failures)
            wait = int(LOGIN_WINDOW_SECONDS - (now - oldest_failure))
            return False, max(wait, 1)

        return True, 0


def _record_login_attempt(ip, success):
    """记录登录尝试"""
    with _login_lock:
        if ip not in _login_attempts:
            _login_attempts[ip] = []
        _login_attempts[ip].append((time.time(), success))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """登录页面"""
    if request.method == 'GET':
        return render_template('auth/login.html')

    # 速率限制检查
    ip = request.remote_addr or '127.0.0.1'
    allowed, wait = _check_login_rate_limit(ip)
    if not allowed:
        flash(_('登录尝试过于频繁，请在 %(seconds)s 秒后再试') % {'seconds': wait}, 'error')
        return render_template('auth/login.html')

    # POST请求处理
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    remember = request.form.get('remember', False)

    if not username or not password:
        flash(_('请输入用户名和密码'), 'error')
        return render_template('auth/login.html')

    # 查找用户
    user = User.query.filter(
        (User.username == username) | (User.email == username)
    ).first()

    if not user or not user.check_password(password):
        _record_login_attempt(ip, False)

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

        flash(_('用户名或密码错误'), 'error')
        return render_template('auth/login.html')

    if not user.is_active:
        _record_login_attempt(ip, False)

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

        flash(_('账户已被禁用，请联系管理员'), 'error')
        return render_template('auth/login.html')

    # 登录成功
    _record_login_attempt(ip, True)
    login_user(user, remember=remember)

    # 记录登录成功日志
    log = Log(
        level='info',
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
    flash(_('您已成功退出登录'), 'success')
    return redirect(url_for('auth.login'))


@auth_bp.route('/profile')
@login_required
def profile():
    """用户资料页面"""
    return render_template('auth/profile.html', user=current_user)
