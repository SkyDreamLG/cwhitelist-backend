# routes/web.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, session, current_app
from flask_login import login_required, current_user
from flask_babel import _
from sqlalchemy import desc, or_, inspect, func
from datetime import datetime, timedelta
import traceback

import json
from werkzeug.utils import secure_filename
import os

from config import config
from models.database import db
from models.token import Token
from models.whitelist import WhitelistEntry
from models.setting import Setting
from models.log import Log
from utils.helpers import log_msg


def cleanup_old_logs():
    """清理超过保留时间的日志"""
    from datetime import timedelta

    try:
        # 获取系统日志保留天数
        system_retention_str = Setting.get_value('system_log_retention_days', '0')
        system_retention_days = int(system_retention_str) if system_retention_str else 0

        # 获取登陆日志保留天数
        login_retention_str = Setting.get_value('login_log_retention_days', '0')
        login_retention_days = int(login_retention_str) if login_retention_str else 0

        deleted_system = 0
        deleted_login = 0

        # 清理系统日志（非login级别）
        if system_retention_days > 0:
            cutoff = datetime.utcnow() - timedelta(days=system_retention_days)
            old_system_logs = Log.query.filter(
                Log.level != 'login',
                Log.created_at < cutoff
            )
            deleted_system = old_system_logs.count()
            old_system_logs.delete()
            db.session.commit()

        # 清理登陆日志（login级别）
        if login_retention_days > 0:
            cutoff = datetime.utcnow() - timedelta(days=login_retention_days)
            old_login_logs = Log.query.filter(
                Log.level == 'login',
                Log.created_at < cutoff
            )
            deleted_login = old_login_logs.count()
            old_login_logs.delete()
            db.session.commit()

        if deleted_system > 0 or deleted_login > 0:
            print(f"[日志清理] 系统日志: {deleted_system}条, 登陆日志: {deleted_login}条")

    except Exception as e:
        db.session.rollback()
        print(f"[日志清理] 清理失败: {e}")

web_bp = Blueprint('web', __name__)


def is_whitelist_user(player_name=None, player_uuid=None, player_ip=None):
    """检查玩家是否为白名单用户（name/UUID/IP任意匹配）"""
    if player_name:
        entry = WhitelistEntry.query.filter_by(type='name', value=player_name, is_active=True).first()
        if entry:
            return True
    if player_uuid:
        entry = WhitelistEntry.query.filter_by(type='uuid', value=player_uuid, is_active=True).first()
        if entry:
            return True
    if player_ip:
        entry = WhitelistEntry.query.filter_by(type='ip', value=player_ip, is_active=True).first()
        if entry:
            return True
    return False


# OOBE 检查函数 - 简化版本
def is_oobe_required():
    """检查是否需要OOBE设置"""
    try:
        # 首先检查数据库表是否存在
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        table_names = inspector.get_table_names()

        # 如果users表不存在，需要OOBE
        if 'users' not in table_names:
            return True

        # 如果表存在，检查是否有管理员用户
        from models.user import User
        admin_exists = User.query.filter_by(role='admin').first() is not None

        # 如果没有管理员用户，也需要OOBE
        if not admin_exists:
            return True

        return False
    except Exception as e:
        # 任何异常都认为需要OOBE
        print(f"OOBE检查异常: {e}")
        return True


@web_bp.route('/')
def index():
    """首页"""
    if is_oobe_required():
        return redirect(url_for('web.oobe'))
    return redirect(url_for('auth.login'))


@web_bp.route('/set-language', methods=['POST'])
def set_language():
    """设置界面语言"""
    lang = request.form.get('lang', '')
    if lang in current_app.config.get('LANGUAGES', {}):
        session['lang'] = lang
        return jsonify({'success': True, 'lang': lang})
    return jsonify({'success': False, 'error': 'Invalid language'})


@web_bp.route('/dashboard')
@login_required
def dashboard():
    """仪表板"""

    # 白名单统计
    total_entries = WhitelistEntry.query.count()
    active_entries = WhitelistEntry.query.filter_by(is_active=True).count()
    inactive_entries = total_entries - active_entries

    # 过期条目
    expired_count = WhitelistEntry.query.filter(
        WhitelistEntry.expires_at.isnot(None),
        WhitelistEntry.expires_at < datetime.utcnow()
    ).count()

    # 在线服务器数及每服务器在线人数
    from models.server_status import ServerStatus
    from models.session import LoginSession
    all_statuses = ServerStatus.query.all()
    online_server_count = 0
    server_online_counts = []
    for st in all_statuses:
        if ServerStatus.is_server_online(st.server_id):
            online_server_count += 1
        count = LoginSession.query.filter_by(server_id=st.server_id, logout_time=None).count()
        server_online_counts.append((st.server_id, count, ServerStatus.is_server_online(st.server_id)))
    server_online_counts.sort(key=lambda x: x[1], reverse=True)

    # 登陆日志统计（仅玩家数据，排除网页登录）
    total_logins = Log.query.filter_by(level='login', source='api').count()
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_logins = Log.query.filter(Log.level == 'login', Log.source == 'api', Log.created_at >= today).count()

    # 登陆趋势（最近7天）- 区分白名单/游客
    from collections import defaultdict
    login_trend = defaultdict(int)
    login_trend_wl = defaultdict(int)
    login_trend_guest = defaultdict(int)
    for i in range(6, -1, -1):
        day_start = today - timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        day_logs = Log.query.filter(
            Log.level == 'login',
            Log.source == 'api',
            Log.created_at >= day_start,
            Log.created_at < day_end
        ).all()
        day_key = day_start.strftime('%m-%d')
        login_trend[day_key] = len(day_logs)
        login_trend_wl[day_key] = 0
        login_trend_guest[day_key] = 0
        for log_entry in day_logs:
            if is_whitelist_user(player_name=log_entry.player_name, player_uuid=log_entry.player_uuid):
                login_trend_wl[day_key] += 1
            else:
                login_trend_guest[day_key] += 1

    # 允许/拒绝统计
    allowed_logins = Log.query.filter(
        Log.level == 'login',
        Log.source == 'api',
        Log.details.like('%allowed: True%')
    ).count()
    denied_logins = total_logins - allowed_logins

    # 日志统计
    log_stats = {
        'total': Log.query.count(),
        'info': Log.query.filter_by(level='info').count(),
        'warning': Log.query.filter_by(level='warning').count(),
        'error': Log.query.filter_by(level='error').count(),
        'login': total_logins,
    }

    # 用户统计
    from models.user import User
    user_count = User.query.count()

    # 各服务器条目数
    server_entry_counts = db.session.query(
        WhitelistEntry.server_id,
        func.count(WhitelistEntry.id)
    ).group_by(WhitelistEntry.server_id).all()

    # 最近添加的白名单条目
    recent_entries = WhitelistEntry.query.order_by(desc(WhitelistEntry.created_at)).limit(10).all()

    return render_template('dashboard.html',
                           total_entries=total_entries,
                           active_entries=active_entries,
                           inactive_entries=inactive_entries,
                           expired_count=expired_count,
                           online_server_count=online_server_count,
                           server_online_counts=server_online_counts,
                           total_logins=total_logins,
                           today_logins=today_logins,
                           allowed_logins=allowed_logins,
                           denied_logins=denied_logins,
                           login_trend=login_trend,
                           login_trend_wl=login_trend_wl,
                           login_trend_guest=login_trend_guest,
                           log_stats=log_stats,
                           user_count=user_count,
                           recent_entries=recent_entries)


@web_bp.route('/whitelist')
@login_required
def whitelist():
    """白名单管理"""
    # 获取查询参数
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    entry_type = request.args.get('type', '')
    search = request.args.get('search', '')
    active_only = request.args.get('active_only', 'false')
    server_id = request.args.get('server_id', '')

    # 将字符串转换为布尔值
    active_only_bool = active_only == 'true'

    # 构建查询
    query = WhitelistEntry.query

    if server_id:
        query = query.filter_by(server_id=server_id)

    if entry_type:
        query = query.filter_by(type=entry_type)

    if search:
        query = query.filter(
            (WhitelistEntry.value.ilike(f'%{search}%')) |
            (WhitelistEntry.description.ilike(f'%{search}%'))
        )

    if active_only_bool:
        query = query.filter_by(is_active=True)
        # 排除过期的条目
        query = query.filter(or_(
            WhitelistEntry.expires_at.is_(None),
            WhitelistEntry.expires_at > datetime.utcnow()
        ))

    # 分页
    pagination = query.order_by(desc(WhitelistEntry.created_at)).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # 为每个条目获取最后登录信息
    entries_with_login_info = []
    for entry in pagination.items:
        entry_dict = {
            'entry': entry,
            'last_login': None
        }

        # 如果是name或uuid类型，获取最后登录信息
        if entry.type in ['name', 'uuid']:
            last_login = Log.get_last_login_info(entry.type, entry.value)
            if last_login:
                entry_dict['last_login'] = last_login

        entries_with_login_info.append(entry_dict)

    # 确保传递正确的值到模板
    filters_dict = {
        'type': entry_type,
        'search': search,
        'active_only': active_only_bool,
        'server_id': server_id
    }

    # 获取所有唯一的server_id用于下拉菜单
    server_ids = [row[0] for row in db.session.query(WhitelistEntry.server_id).distinct().order_by(WhitelistEntry.server_id).all()]

    return render_template('whitelist.html',
                           entries=entries_with_login_info,
                           pagination=pagination,
                           filters=filters_dict,
                           server_ids=server_ids)


@web_bp.route('/whitelist/add', methods=['POST'])
@login_required
def add_whitelist():
    """添加白名单条目"""
    from utils.timezone import parse_datetime, local_to_utc

    entry_type = request.form.get('type', '').strip().lower()
    value = request.form.get('value', '').strip()
    server_id = request.form.get('server_id', '').strip()
    description = request.form.get('description', '').strip()
    expires_at = request.form.get('expires_at')

    if not entry_type or not value:
        flash(_('请填写类型和值'), 'error')
        return redirect(url_for('web.whitelist'))

    if not server_id:
        flash(_('请填写服务器ID'), 'error')
        return redirect(url_for('web.whitelist'))

    if entry_type not in ['name', 'uuid', 'ip']:
        flash(_('类型必须为: name, uuid 或 ip'), 'error')
        return redirect(url_for('web.whitelist'))

    # 检查是否已存在（相同server_id下）
    existing = WhitelistEntry.query.filter_by(
        type=entry_type,
        value=value,
        server_id=server_id
    ).first()

    if existing:
        flash(_('条目已存在'), 'error')
        return redirect(url_for('web.whitelist'))

    # 创建条目
    entry = WhitelistEntry(
        type=entry_type,
        value=value,
        server_id=server_id,
        description=description,
        created_by=current_user.username,
        is_active=True
    )

    if expires_at:
        try:
            # 解析本地时间并转换为UTC存储
            local_dt = parse_datetime(expires_at)
            if local_dt:
                entry.expires_at = local_to_utc(local_dt)
        except Exception as e:
            flash(_('过期时间格式错误: %(error)s') % {'error': str(e)}, 'error')
            return redirect(url_for('web.whitelist'))

    db.session.add(entry)
    db.session.commit()

    # 记录操作日志
    log = Log(
        level='info',
        message=log_msg(
            f'添加白名单条目: {entry_type}={value}',
            f'Add Whitelist Entry: {entry_type}={value}'
        ),
        source='web',
        ip_address=request.remote_addr,
        user_id=current_user.id,
        details=f'entry_id: {entry.id}, description: {description}'
    )
    db.session.add(log)
    db.session.commit()

    flash(_('白名单条目添加成功'), 'success')
    return redirect(url_for('web.whitelist'))


@web_bp.route('/whitelist/<entry_id>/toggle', methods=['POST'])
@login_required
def toggle_whitelist(entry_id):
    """切换白名单条目状态"""
    entry = WhitelistEntry.query.get(entry_id)
    if not entry:
        flash(_('条目不存在'), 'error')
        return redirect(url_for('web.whitelist'))

    entry.is_active = not entry.is_active
    db.session.commit()

    # 记录操作日志
    log = Log(
        level='info',
        message=log_msg(
            f'切换白名单条目状态: {entry.type}={entry.value} -> {entry.is_active}',
            f'Toggle Whitelist Entry Status: {entry.type}={entry.value} -> {entry.is_active}'
        ),
        source='web',
        ip_address=request.remote_addr,
        user_id=current_user.id,
        details=f'entry_id: {entry.id}, new_status: {entry.is_active}'
    )
    db.session.add(log)
    db.session.commit()

    status = _('启用') if entry.is_active else _('禁用')
    flash(_('条目已%(status)s') % {'status': status}, 'success')
    return redirect(url_for('web.whitelist'))


@web_bp.route('/whitelist/<entry_id>/edit', methods=['POST'])
@login_required
def edit_whitelist(entry_id):
    """编辑白名单条目"""
    from utils.timezone import parse_datetime, local_to_utc

    entry = WhitelistEntry.query.get(entry_id)
    if not entry:
        flash(_('条目不存在'), 'error')
        return redirect(url_for('web.whitelist'))

    entry_type = request.form.get('type', '').strip().lower()
    value = request.form.get('value', '').strip()
    server_id = request.form.get('server_id', '').strip()
    description = request.form.get('description', '').strip()
    expires_at = request.form.get('expires_at', '')

    if not entry_type or not value:
        flash(_('请填写类型和值'), 'error')
        return redirect(url_for('web.whitelist'))

    if not server_id:
        flash(_('请填写服务器ID'), 'error')
        return redirect(url_for('web.whitelist'))

    if entry_type not in ['name', 'uuid', 'ip']:
        flash(_('类型必须为: name, uuid 或 ip'), 'error')
        return redirect(url_for('web.whitelist'))

    # 检查是否与其他条目重复（排除自身）
    existing = WhitelistEntry.query.filter_by(
        type=entry_type,
        value=value,
        server_id=server_id
    ).filter(WhitelistEntry.id != entry_id).first()

    if existing:
        flash(_('已存在相同类型、值和服务器ID的条目'), 'error')
        return redirect(url_for('web.whitelist'))

    # 记录变更前的值用于日志
    old_data = f'type={entry.type}, value={entry.value}, server_id={entry.server_id}, description={entry.description}'

    # 更新字段
    entry.type = entry_type
    entry.value = value
    entry.server_id = server_id
    entry.description = description

    if expires_at:
        try:
            local_dt = parse_datetime(expires_at)
            if local_dt:
                entry.expires_at = local_to_utc(local_dt)
        except Exception as e:
            flash(_('过期时间格式错误: %(error)s') % {'error': str(e)}, 'error')
            return redirect(url_for('web.whitelist'))
    else:
        entry.expires_at = None

    db.session.commit()

    # 记录操作日志
    log = Log(
        level='info',
        message=log_msg(
            f'编辑白名单条目: {entry.type}={entry.value}',
            f'Edit Whitelist Entry: {entry.type}={entry.value}'
        ),
        source='web',
        ip_address=request.remote_addr,
        user_id=current_user.id,
        details=f'entry_id: {entry.id}, old: ({old_data}), new: type={entry.type}, value={entry.value}, server_id={entry.server_id}, description={entry.description}'
    )
    db.session.add(log)
    db.session.commit()

    flash(_('白名单条目已更新'), 'success')
    return redirect(url_for('web.whitelist'))


@web_bp.route('/whitelist/<entry_id>/delete', methods=['POST'])
@login_required
def delete_whitelist(entry_id):
    """删除白名单条目"""
    entry = WhitelistEntry.query.get(entry_id)
    if not entry:
        flash(_('条目不存在'), 'error')
        return redirect(url_for('web.whitelist'))

    # 记录操作日志
    log = Log(
        level='warning',
        message=log_msg(
            f'删除白名单条目: {entry.type}={entry.value}',
            f'Delete Whitelist Entry: {entry.type}={entry.value}'
        ),
        source='web',
        ip_address=request.remote_addr,
        user_id=current_user.id,
        details=f'entry_id: {entry.id}, description: {entry.description}'
    )
    db.session.add(log)

    db.session.delete(entry)
    db.session.commit()

    flash(_('条目已删除'), 'success')
    return redirect(url_for('web.whitelist'))


@web_bp.route('/whitelist/batch', methods=['POST'])
@login_required
def batch_whitelist():
    """批量操作白名单条目"""
    action = request.form.get('action', '')
    entry_ids_str = request.form.get('entry_ids', '')
    entry_ids = [eid.strip() for eid in entry_ids_str.split(',') if eid.strip()]

    if not entry_ids:
        flash(_('未选择任何条目'), 'error')
        return redirect(url_for('web.whitelist'))

    if action not in ('enable', 'disable', 'delete'):
        flash(_('无效的操作'), 'error')
        return redirect(url_for('web.whitelist'))

    entries = WhitelistEntry.query.filter(WhitelistEntry.id.in_(entry_ids)).all()

    if not entries:
        flash(_('未找到所选条目'), 'error')
        return redirect(url_for('web.whitelist'))

    count = len(entries)

    if action == 'enable':
        for e in entries:
            e.is_active = True
        msg = _('已启用 %(count)s 个条目', count=count)
    elif action == 'disable':
        for e in entries:
            e.is_active = False
        msg = _('已禁用 %(count)s 个条目', count=count)
    elif action == 'delete':
        for e in entries:
            db.session.delete(e)
        msg = _('已删除 %(count)s 个条目', count=count)

    db.session.commit()

    log = Log(
        level='warning' if action == 'delete' else 'info',
        message=log_msg(
            f'批量操作白名单: {action} {count}条',
            f'Batch Whitelist Operation: {action} {count} entries'
        ),
        source='web',
        ip_address=request.remote_addr,
        user_id=current_user.id,
        details=f'action: {action}, entry_ids: {entry_ids}, count: {count}'
    )
    db.session.add(log)
    db.session.commit()

    flash(msg, 'success')
    return redirect(url_for('web.whitelist'))


@web_bp.route('/logs')
@login_required
def logs():
    """系统日志查看（排除登陆日志）"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    level = request.args.get('level', '')
    source = request.args.get('source', '')
    hide_health = request.args.getlist('hide_health')[-1] if request.args.getlist('hide_health') else '0'

    # 构建查询 - 系统日志排除 login 级别
    query = Log.query.filter(Log.level != 'login')

    if level:
        query = query.filter_by(level=level)

    if source:
        query = query.filter_by(source=source)

    if hide_health == '1':
        query = query.filter(
            ~Log.message.ilike('%健康检查%'),
            ~Log.message.ilike('%health%')
        )

    # 分页
    pagination = query.order_by(desc(Log.created_at)).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # 获取日志级别和来源的统计
    level_stats = db.session.query(
        Log.level,
        db.func.count(Log.id)
    ).filter(Log.level != 'login').group_by(Log.level).all()

    source_stats = db.session.query(
        Log.source,
        db.func.count(Log.id)
    ).filter(Log.level != 'login').group_by(Log.source).all()

    filters = {
        'level': level,
        'source': source,
        'hide_health': hide_health,
    }

    return render_template('logs.html',
                           logs=pagination.items,
                           pagination=pagination,
                           level_stats=dict(level_stats),
                           source_stats=dict(source_stats),
                           filters=filters)


@web_bp.route('/logs/login')
@login_required
def login_logs():
    """登陆日志查看"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    server_id = request.args.get('server_id', '')
    show_success = request.args.getlist('show_success')[-1] if request.args.getlist('show_success') else '1'
    show_denied = request.args.getlist('show_denied')[-1] if request.args.getlist('show_denied') else '1'
    show_logout = request.args.getlist('show_logout')[-1] if request.args.getlist('show_logout') else '1'
    player_search = request.args.get('player_search', '').strip()

    # 构建查询 - 只查 login 级别，排除网页登录只显示玩家数据
    query = Log.query.filter_by(level='login', source='api')

    if player_search:
        query = query.filter(Log.player_name.ilike(f'%{player_search}%'))

    if server_id:
        query = query.filter_by(server_id=server_id)

    # 事件类型筛选
    conditions = []
    if show_success == '1':
        conditions.append(Log.details.like('%allowed: True%'))
    if show_denied == '1':
        conditions.append(Log.details.like('%allowed: False%'))
    if show_logout == '1':
        conditions.append(Log.details.like('%action: logout%'))
    if conditions:
        query = query.filter(or_(*conditions))

    # 分页
    pagination = query.order_by(desc(Log.created_at)).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # 获取所有唯一的 server_id 用于筛选下拉框
    server_ids = db.session.query(Log.server_id).filter(
        Log.server_id.isnot(None),
        Log.level == 'login',
        Log.source == 'api'
    ).distinct().all()
    server_ids = [s[0] for s in server_ids if s[0]]

    # 所有玩家名用于搜索下拉（排除网页登录）
    player_names = [row[0] for row in db.session.query(Log.player_name).filter(
        Log.player_name.isnot(None), Log.level == 'login', Log.source == 'api'
    ).distinct().order_by(Log.player_name).all()]

    filters = {
        'server_id': server_id,
        'show_success': show_success,
        'show_denied': show_denied,
        'show_logout': show_logout,
        'player_search': player_search,
    }

    return render_template('login_logs.html',
                           logs=pagination.items,
                           pagination=pagination,
                           server_ids=server_ids,
                           player_names=player_names,
                           filters=filters)


@web_bp.route('/logs/clear', methods=['POST'])
@login_required
def clear_logs():
    """清空日志 - 修复版本"""
    if not current_user.is_admin():
        flash(_('需要管理员权限'), 'error')
        return redirect(url_for('web.logs'))

    # 检查是否为测试请求
    is_test = request.form.get('test') == 'true'

    try:
        # 获取当前日志总数
        total_logs = Log.query.count()

        if is_test:
            # 测试模式，不实际删除
            flash(_('测试模式：当前有 %(total)s 条日志，点击确认后将清空') % {'total': total_logs}, 'info')
            return redirect(url_for('web.logs'))

        if total_logs == 0:
            flash(_('没有日志可清空'), 'info')
            return redirect(url_for('web.logs'))

        # 使用更可靠的方式删除日志
        deleted_count = 0

        # 方法1：分批删除（更安全）
        batch_size = 100
        while True:
            # 获取一批日志
            batch = Log.query.limit(batch_size).all()
            if not batch:
                break

            # 逐个删除
            for log in batch:
                db.session.delete(log)

            try:
                db.session.commit()
                deleted_count += len(batch)
                print(f"已删除 {len(batch)} 条日志，累计 {deleted_count} 条")
            except Exception as e:
                db.session.rollback()
                print(f"删除批次失败: {e}")
                # 尝试单个删除
                for log in batch:
                    try:
                        db.session.delete(log)
                        db.session.commit()
                        deleted_count += 1
                    except:
                        db.session.rollback()
                        continue

        # 验证删除结果
        remaining_count = Log.query.count()

        # 记录操作日志
        operation_log = Log(
            level='warning',
            message=log_msg(
                f'管理员清空日志，删除了 {deleted_count} 条记录',
                f'Admin cleared logs, deleted {deleted_count} entries'
            ),
            source='web',
            ip_address=request.remote_addr,
            user_id=current_user.id,
            details=f'user: {current_user.username}, cleared: {deleted_count}, remaining: {remaining_count}'
        )
        db.session.add(operation_log)
        db.session.commit()

        flash(_('成功清空 %(deleted)s 条日志，剩余 %(remaining)s 条') % {'deleted': deleted_count, 'remaining': remaining_count}, 'success')

    except Exception as e:
        db.session.rollback()
        print(f"清空日志异常: {e}")
        flash(_('清空日志失败: %(error)s') % {'error': str(e)}, 'error')

    return redirect(url_for('web.logs'))


@web_bp.route('/settings/clear-health-check-logs', methods=['POST'])
@login_required
def clear_health_check_logs():
    """清除健康检查日志"""
    if not current_user.is_admin():
        flash(_('需要管理员权限'), 'error')
        return redirect(url_for('web.settings'))

    try:
        health_logs = Log.query.filter(Log.details.like('%endpoint: /health%'))
        total_count = health_logs.count()

        if total_count == 0:
            flash(_('没有健康检查日志可清除'), 'info')
            return redirect(url_for('web.settings'))

        # 分批删除
        deleted = 0
        batch_size = 500
        while True:
            batch = health_logs.limit(batch_size).all()
            if not batch:
                break
            for log_entry in batch:
                db.session.delete(log_entry)
            db.session.commit()
            deleted += len(batch)

        # 记录操作日志
        op_log = Log(
            level='warning',
            message=log_msg(
                f'管理员清除健康检查日志，删除了 {deleted} 条记录',
                f'Admin cleared health check logs, deleted {deleted} entries'
            ),
            source='web',
            ip_address=request.remote_addr,
            user_id=current_user.id,
            details=f'user: {current_user.username}, cleared_health_checks: {deleted}'
        )
        db.session.add(op_log)
        db.session.commit()

        flash(_('成功清除 %(count)s 条健康检查日志') % {'count': deleted}, 'success')

    except Exception as e:
        db.session.rollback()
        flash(_('清除健康检查日志失败: %(error)s') % {'error': str(e)}, 'error')

    return redirect(url_for('web.settings'))


@web_bp.route('/settings')
@login_required
def settings():
    """系统设置"""
    if not current_user.is_admin():
        flash(_('需要管理员权限'), 'error')
        return redirect(url_for('web.dashboard'))

    settings_list = Setting.query.order_by(Setting.category, Setting.key).all()

    # 按分类分组
    settings_by_category = {}
    for setting in settings_list:
        category = setting.category or 'general'
        if category not in settings_by_category:
            settings_by_category[category] = []
        settings_by_category[category].append(setting)

    # 构建简单 key->value 映射供模板使用
    settings_dict = {s.key: s.value for s in settings_list}

    # 获取Token统计
    from utils.timezone import now_utc
    total_tokens = Token.query.count()
    active_tokens = Token.query.filter_by(is_active=True).count()
    expired_tokens = Token.query.filter(
        Token.expires_at.isnot(None),
        Token.expires_at < now_utc(),
        Token.is_active == True
    ).count()

    return render_template('settings.html',
                           settings=settings_dict,
                           settings_by_category=settings_by_category,
                           version=current_app.config.get('APP_VERSION', '2.3.0'),
                           token_stats={
                               'total': total_tokens,
                               'active': active_tokens,
                               'expired': expired_tokens
                           })


@web_bp.route('/settings/save', methods=['POST'])
@login_required
def save_settings():
    """保存系统设置"""
    if not current_user.is_admin():
        flash(_('需要管理员权限'), 'error')
        return redirect(url_for('web.dashboard'))

    try:
        # 更新设置
        for key in request.form:
            if key.startswith('setting_'):
                setting_key = key[8:]  # 去掉'setting_'
                value = request.form[key]

                setting = Setting.query.filter_by(key=setting_key).first()
                if setting:
                    setting.value = value
                else:
                    setting = Setting(key=setting_key, value=value)
                    db.session.add(setting)

        db.session.commit()

        # 记录操作日志
        log = Log(
            level='info',
            message=log_msg(
                '更新系统设置',
                'Update System Settings'
            ),
            source='web',
            ip_address=request.remote_addr,
            user_id=current_user.id
        )
        db.session.add(log)
        db.session.commit()

        flash(_('设置已保存'), 'success')
    except Exception as e:
        db.session.rollback()
        flash(_('保存设置失败: %(error)s') % {'error': str(e)}, 'error')

    return redirect(url_for('web.settings'))


@web_bp.route('/api/docs')
@login_required
def api_docs():
    """API文档"""
    return render_template('api_docs.html',
                           version=current_app.config.get('APP_VERSION', '2.3.0'))


@web_bp.route('/about')
def about():
    """关于页面"""
    return render_template('about.html',
                           version=current_app.config.get('APP_VERSION', '2.3.0'))


@web_bp.route('/oobe', methods=['GET', 'POST'])
def oobe():
    """OOBE设置页面 - 完整集成初始化功能"""
    # 如果系统已经初始化且不需要OOBE，重定向到登录页
    if not is_oobe_required():
        print("系统已初始化，重定向到登录页")
        flash(_('系统已初始化，请登录'), 'info')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        # 处理OOBE设置
        admin_username = request.form.get('admin_username', 'admin').strip()
        admin_email = request.form.get('admin_email', '').strip()
        admin_password = request.form.get('admin_password', '')
        admin_confirm = request.form.get('admin_confirm', '')
        site_title = request.form.get('site_title', '').strip()

        # 验证输入
        errors = []

        if not admin_username:
            errors.append(_('请填写管理员用户名'))
        elif len(admin_username) < 3:
            errors.append(_('用户名至少3个字符'))

        if not admin_email:
            errors.append(_('请填写管理员邮箱'))
        elif '@' not in admin_email:
            errors.append(_('邮箱格式不正确'))

        if not admin_password:
            errors.append(_('请填写管理员密码'))
        elif admin_password != admin_confirm:
            errors.append(_('两次输入的密码不一致'))
        elif len(admin_password) < 8:
            errors.append(_('密码长度至少8位'))

        if not site_title:
            errors.append(_('请填写站点标题'))

        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('oobe.html')

        try:
            print("开始系统初始化...")

            # 1. 创建数据库表（如果不存在）
            print("步骤1: 创建数据库表...")
            db.create_all()
            print("✓ 数据库表创建完成")

            # 2. 创建管理员用户
            print("步骤2: 创建管理员用户...")
            from models.user import User

            # 检查是否已存在管理员
            existing_admin = User.query.filter_by(role='admin').first()
            if existing_admin:
                # 更新现有管理员
                existing_admin.username = admin_username
                existing_admin.email = admin_email
                existing_admin.set_password(admin_password)
                print("✓ 更新现有管理员")
            else:
                # 创建新管理员
                admin_user = User(
                    username=admin_username,
                    email=admin_email,
                    role='admin',
                    is_active=True
                )
                admin_user.set_password(admin_password)
                db.session.add(admin_user)
                print("✓ 创建新管理员")

            # 3. 创建系统设置
            print("步骤3: 创建系统设置...")

            # 保存基本设置
            Setting.set_value('site_title', site_title, '站点标题', 'system')
            Setting.set_value('admin_email', admin_email, '管理员邮箱', 'system')
            Setting.set_value('app_name', 'CWhitelist', '应用名称', 'system')
            Setting.set_value('timezone', 'Asia/Shanghai', '系统时区设置', 'system')

            # 设置默认配置
            default_settings = [
                ('registration_enabled', 'false', '允许用户注册', 'security'),
                ('system_log_retention_days', '0', '系统日志保存天数', 'logging'),
                ('login_log_retention_days', '0', '登陆日志保存天数', 'logging'),
                ('max_login_attempts', '5', '最大登录尝试次数', 'security'),
                ('session_timeout', '60', '会话超时（分钟）', 'security'),
                ('require_auth', 'true', 'API需要认证', 'security'),
                ('api_rate_limit', '100/hour', 'API速率限制', 'api'),
                ('default_timezone', 'Asia/Shanghai', '默认时区', 'system'),
                ('site_description', 'CWhitelist管理系统', '站点描述', 'system'),
                ('maintenance_mode', 'false', '维护模式', 'system'),
                ('enable_api', 'true', '启用API', 'api'),
            ]

            for key, value, description, category in default_settings:
                Setting.set_value(key, value, description, category)

            print("✓ 系统设置创建完成")

            # 4. 创建示例Token（可选）
            print("步骤4: 创建示例API Token...")
            try:
                import secrets
                from werkzeug.security import generate_password_hash
                raw_token = secrets.token_hex(32)
                token_hash_val = generate_password_hash(raw_token)

                # 获取刚创建的管理员ID
                admin = User.query.filter_by(email=admin_email).first()
                if admin:
                    from utils.permissions import Permission
                    example_token = Token(
                        token_hash=token_hash_val,
                        name='示例服务器Token',
                        user_id=admin.id,
                        permissions=Permission.SERVER_FULL,
                        is_active=True
                    )
                    db.session.add(example_token)
                    print(f"✓ 创建示例Token: {raw_token[:16]}...")
            except Exception as token_error:
                print(f"⚠ 创建示例Token失败: {token_error}")

            # 5. 提交所有更改
            db.session.commit()
            print("✓ 数据库提交完成")

            # 6. 记录初始化日志
            log = Log(
                level='info',
                message=log_msg(
                    '系统OOBE初始化完成',
                    'System OOBE Initialization Completed'
                ),
                source='system',
                ip_address=request.remote_addr,
                details=f'admin_username: {admin_username}, admin_email: {admin_email}, site_title: {site_title}'
            )
            db.session.add(log)
            db.session.commit()

            # 7. 验证初始化结果
            print("\n验证初始化结果:")
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()

            required_tables = ['users', 'settings', 'whitelist_entries', 'logs', 'tokens']
            for table in required_tables:
                if table in tables:
                    print(f"  ✓ {table} 表存在")
                else:
                    print(f"  ✗ {table} 表缺失")

            # 检查管理员
            admin_check = User.query.filter_by(role='admin').first()
            if admin_check:
                print(f"  ✓ 管理员用户: {admin_check.username}")
            else:
                print("  ✗ 未找到管理员用户")

            # 检查设置
            settings_count = Setting.query.count()
            print(f"  ✓ 系统设置: {settings_count} 条")

            print("\n✅ 系统初始化成功完成！")

            flash(_('系统初始化成功！管理员账户: %(username)s，请使用该账户登录。') % {'username': admin_username}, 'success')
            return redirect(url_for('auth.login'))

        except Exception as e:
            db.session.rollback()
            print(f"❌ 初始化失败: {e}")
            traceback.print_exc()

            # 提供更详细的错误信息
            error_msg = _('初始化失败: %(error)s') % {'error': str(e)}
            if 'UNIQUE constraint failed' in str(e):
                error_msg += _(' (可能是用户名或邮箱已存在)')
            elif 'no such table' in str(e):
                error_msg += _(' (数据库表创建失败)')

            flash(error_msg, 'error')
            return render_template('oobe.html')

    return render_template('oobe.html')


@web_bp.route('/whitelist/import', methods=['POST'])
@login_required
def import_whitelist():
    """从JSON文件导入白名单"""
    try:
        if 'json_file' not in request.files:
            flash(_('请选择JSON文件'), 'error')
            return redirect(url_for('web.whitelist'))

        file = request.files['json_file']
        if file.filename == '':
            flash(_('请选择JSON文件'), 'error')
            return redirect(url_for('web.whitelist'))

        if not file.filename.endswith('.json'):
            flash(_('只支持JSON文件'), 'error')
            return redirect(url_for('web.whitelist'))

        # 读取文件内容
        file_content = file.read().decode('utf-8')
        data = json.loads(file_content)

        if not isinstance(data, list):
            flash(_('JSON格式不正确，应该是一个数组'), 'error')
            return redirect(url_for('web.whitelist'))

        # 获取导入选项
        skip_existing = request.form.get('skip_existing') == 'on'
        set_inactive = request.form.get('set_inactive') == 'on'
        description = request.form.get('description', '').strip()
        server_id = request.form.get('server_id', '').strip()

        if not server_id:
            flash(_('请填写服务器ID'), 'error')
            return redirect(url_for('web.whitelist'))

        imported_count = 0
        skipped_count = 0
        error_count = 0

        for item in data:
            try:
                # 验证数据格式
                if not isinstance(item, dict) or 'type' not in item or 'value' not in item:
                    error_count += 1
                    continue

                entry_type = item['type'].lower().strip()
                value = item['value'].strip()
                # 支持每个条目独立server_id，fallback到表单值
                entry_server_id = item.get('server_id', '').strip() or server_id

                if not entry_server_id:
                    error_count += 1
                    continue

                # 验证类型
                if entry_type not in ['name', 'uuid', 'ip']:
                    error_count += 1
                    continue

                # 检查是否已存在（相同server_id下）
                existing = WhitelistEntry.query.filter_by(
                    type=entry_type,
                    value=value,
                    server_id=entry_server_id
                ).first()

                if existing and skip_existing:
                    skipped_count += 1
                    continue

                # 创建或更新条目
                if existing:
                    # 更新现有条目
                    existing.description = description or existing.description
                    existing.is_active = not set_inactive if set_inactive else existing.is_active
                else:
                    # 创建新条目
                    entry = WhitelistEntry(
                        type=entry_type,
                        value=value,
                        server_id=entry_server_id,
                        description=description,
                        created_by=current_user.username,
                        is_active=not set_inactive
                    )
                    db.session.add(entry)

                imported_count += 1

            except Exception as e:
                error_count += 1
                print(f"导入条目失败: {e}")

        db.session.commit()

        # 记录导入操作日志
        log = Log(
            level='info',
            message=log_msg(
                f'导入白名单数据: {imported_count}条成功，{skipped_count}条跳过，{error_count}条错误',
                f'Import Whitelist Data: {imported_count} succeeded, {skipped_count} skipped, {error_count} errors'
            ),
            source='web',
            ip_address=request.remote_addr,
            user_id=current_user.id,
            details=f'file: {file.filename}, total_entries: {len(data)}'
        )
        db.session.add(log)
        db.session.commit()

        flash(_('导入完成: %(imported)s条成功导入，%(skipped)s条跳过，%(errors)s条错误') % {'imported': imported_count, 'skipped': skipped_count, 'errors': error_count}, 'success')

    except json.JSONDecodeError:
        flash(_('JSON文件格式不正确'), 'error')
    except Exception as e:
        db.session.rollback()
        flash(_('导入失败: %(error)s') % {'error': str(e)}, 'error')

    return redirect(url_for('web.whitelist'))


@web_bp.route('/whitelist/export')
@login_required
def export_whitelist():
    """导出白名单为JSON"""
    try:
        # 获取查询参数
        active_only = request.args.get('active_only', 'true').lower() == 'true'
        include_expired = request.args.get('include_expired', 'false').lower() == 'true'
        server_id = request.args.get('server_id', '').strip()

        # 构建查询
        query = WhitelistEntry.query

        if server_id:
            query = query.filter_by(server_id=server_id)

        if active_only:
            query = query.filter_by(is_active=True)

            if not include_expired:
                # 排除过期的条目
                query = query.filter(or_(
                    WhitelistEntry.expires_at.is_(None),
                    WhitelistEntry.expires_at > datetime.utcnow()
                ))

        entries = query.all()

        # 构建导出数据
        export_data = []
        for entry in entries:
            export_data.append({
                'type': entry.type,
                'value': entry.value,
                'server_id': entry.server_id,
                'description': entry.description,
                'created_by': entry.created_by,
                'created_at': entry.created_at.isoformat() if entry.created_at else None,
                'expires_at': entry.expires_at.isoformat() if entry.expires_at else None,
                'is_active': entry.is_active
            })

        # 记录导出操作日志
        log = Log(
            level='info',
            message=log_msg(
                f'导出白名单数据: {len(entries)}条',
                f'Export Whitelist Data: {len(entries)} entries'
            ),
            source='web',
            ip_address=request.remote_addr,
            user_id=current_user.id
        )
        db.session.add(log)
        db.session.commit()

        # 创建JSON响应
        from flask import make_response
        response = make_response(json.dumps(export_data, indent=2, ensure_ascii=False))
        response.headers['Content-Type'] = 'application/json'
        response.headers[
            'Content-Disposition'] = f'attachment; filename=whitelist_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'

        return response

    except Exception as e:
        flash(_('导出失败: %(error)s') % {'error': str(e)}, 'error')
        return redirect(url_for('web.whitelist'))


@web_bp.route('/timezone')
@login_required
def timezone_info():
    """显示时区信息"""
    from utils.timezone import get_timezone_info
    info = get_timezone_info()
    return jsonify(info)


# 在 web_bp 中添加时区设置路由

@web_bp.route('/settings/timezone', methods=['GET'])
@login_required
def timezone_settings():
    """时区设置页面"""
    if not current_user.is_admin():
        flash(_('需要管理员权限'), 'error')
        return redirect(url_for('web.dashboard'))

    from utils.timezone import get_common_timezones, get_timezone_info, get_app_timezone, now_utc
    import pytz
    from datetime import datetime as dt_module
    from collections import OrderedDict

    info = get_timezone_info()
    now = now_utc()

    # 将分组时区数据转为扁平字典供模板使用
    common_groups = get_common_timezones()
    timezones = OrderedDict()
    now_dt = dt_module.now()
    for group_name, tz_list in common_groups.items():
        # 添加分组标签
        timezones[f'__group__{group_name}'] = {
            'display_name': f'── {group_name} ──',
            'utc_offset': 999,  # 标记为分组标题
            'is_group': True
        }
        for tz_id, tz_name in tz_list:
            try:
                t = pytz.timezone(tz_id)
                offset = t.utcoffset(now_dt).total_seconds() / 3600 if t.utcoffset(now_dt) else 0
            except Exception:
                offset = 0
            timezones[tz_id] = {
                'display_name': tz_name,
                'utc_offset': offset,
                'is_group': False
            }

    return render_template('settings_timezone.html',
                           timezones=timezones,
                           current_timezone=info.get('timezone', 'UTC'),
                           utc_offset=info.get('utc_offset', 8),
                           now=now)


@web_bp.route('/settings/timezone/save', methods=['POST'])
@login_required
def save_timezone():
    """保存时区设置"""
    if not current_user.is_admin():
        flash(_('需要管理员权限'), 'error')
        return redirect(url_for('web.timezone_settings'))

    timezone_str = request.form.get('timezone', '').strip()

    if not timezone_str:
        flash(_('请选择时区'), 'error')
        return redirect(url_for('web.timezone_settings'))

    # 验证时区有效性
    import pytz
    try:
        pytz.timezone(timezone_str)
    except pytz.UnknownTimeZoneError:
        flash(_('无效的时区'), 'error')
        return redirect(url_for('web.timezone_settings'))

    try:
        # 保存到数据库
        Setting.set_value('timezone', timezone_str, '系统时区设置', 'system')

        # 记录操作日志
        log = Log(
            level='info',
            message=log_msg(
                f'更新系统时区设置: {timezone_str}',
                f'Update System Timezone: {timezone_str}'
            ),
            source='web',
            ip_address=request.remote_addr,
            user_id=current_user.id,
            details=f'old_timezone: {current_app.config.get("TIMEZONE", "UTC")}, new_timezone: {timezone_str}'
        )
        db.session.add(log)
        db.session.commit()

        flash(_('时区设置已保存为: %(timezone)s') % {'timezone': timezone_str}, 'success')

    except Exception as e:
        db.session.rollback()
        flash(_('保存失败: %(error)s') % {'error': str(e)}, 'error')

    return redirect(url_for('web.timezone_settings'))


@web_bp.route('/settings/timezone/test', methods=['POST'])
@login_required
def test_timezone():
    """测试时区设置"""
    if not current_user.is_admin():
        return jsonify({
            'success': False,
            'message': '需要管理员权限'
        }), 403

    try:
        timezone_str = request.json.get('timezone', '').strip()

        if not timezone_str:
            return jsonify({
                'success': False,
                'message': '请提供时区'
            }), 400

        # 验证时区有效性
        import pytz
        from datetime import datetime

        try:
            tz = pytz.timezone(timezone_str)

            # 获取当前时间
            now_utc = datetime.now(pytz.UTC)
            now_local = now_utc.astimezone(tz)

            return jsonify({
                'success': True,
                'timezone': str(tz),
                'utc_offset': now_local.utcoffset().total_seconds() / 3600,
                'current_utc': now_utc.strftime('%Y-%m-%d %H:%M:%S'),
                'current_local': now_local.strftime('%Y-%m-%d %H:%M:%S')
            })

        except pytz.UnknownTimeZoneError:
            return jsonify({
                'success': False,
                'message': '无效的时区'
            }), 400

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'测试失败: {str(e)}'
        }), 500


@web_bp.route('/api/timezone/offset')
@login_required
def get_timezone_offset():
    """获取时区偏移量"""
    try:
        import pytz
        from datetime import datetime

        timezone_str = request.args.get('tz', 'UTC')

        try:
            tz = pytz.timezone(timezone_str)
            now_utc = datetime.now(pytz.UTC)
            now_local = now_utc.astimezone(tz)
            offset = now_local.utcoffset().total_seconds() / 3600

            return jsonify({
                'success': True,
                'timezone': str(tz),
                'offset': offset,
                'current_utc': now_utc.strftime('%Y-%m-%d %H:%M:%S'),
                'current_local': now_local.strftime('%Y-%m-%d %H:%M:%S')
            })
        except pytz.UnknownTimeZoneError:
            return jsonify({
                'success': False,
                'message': '无效的时区'
            }), 400

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取偏移失败: {str(e)}'
        }), 500


@web_bp.route('/api/timezone/list')
@login_required
def get_all_timezones():
    """获取所有时区列表"""
    try:
        import pytz

        # 获取常用时区
        from utils.timezone import get_common_timezones
        common_timezones = get_common_timezones()

        # 展平常用时区列表
        common_tz_list = []
        for group in common_timezones.values():
            for tz_id, _ in group:
                common_tz_list.append(tz_id)

        # 获取所有时区，但排除已在常用列表中的
        all_timezones = pytz.all_timezones
        other_timezones = [tz for tz in all_timezones if tz not in common_tz_list]

        # 合并列表：常用时区在前，其他在后
        all_timezones_sorted = common_tz_list + other_timezones

        return jsonify({
            'success': True,
            'timezones': all_timezones_sorted[:200],  # 限制数量，避免响应过大
            'total': len(all_timezones_sorted)
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取时区列表失败: {str(e)}'
        }), 500


# Token管理路由

@web_bp.route('/tokens')
@login_required
def token_management():
    """Token管理页面"""
    if not current_user.is_admin():
        flash(_('需要管理员权限'), 'error')
        return redirect(url_for('web.dashboard'))

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    query = Token.query

    # 统计信息
    total_tokens = query.count()
    active_tokens = query.filter_by(is_active=True).count()

    from utils.timezone import now_utc
    expired_tokens = query.filter(
        Token.expires_at.isnot(None),
        Token.expires_at < now_utc()
    ).count()

    # 分页
    pagination = query.order_by(Token.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # 检查是否有新创建的Token需要显示
    new_token = None
    if session.get('new_token_created'):
        new_token = session.get('new_token_data')
        # 清除session中的标记
        session.pop('new_token_created', None)
        session.pop('new_token_data', None)

    from utils.permissions import Permission
    return render_template('tokens.html',
                           tokens=pagination.items,
                           pagination=pagination,
                           total_tokens=total_tokens,
                           Permission=Permission,
                           active_tokens=active_tokens,
                           expired_tokens=expired_tokens,
                           new_token=new_token)


@web_bp.route('/tokens/create', methods=['POST'])
@login_required
def create_web_token():
    """通过Web界面创建Token"""
    if not current_user.is_admin():
        flash(_('需要管理员权限'), 'error')
        return redirect(url_for('web.token_management'))

    name = request.form.get('name', '').strip()

    # 细粒度权限：从表单收集选中的权限
    from utils.permissions import Permission
    selected_perms = []
    for perm in Permission.all_permissions():
        if request.form.get(f'perm_{perm}') == 'on':
            selected_perms.append(perm)

    # 处理有效期
    days_valid_str = request.form.get('days_valid', '0').strip()
    if days_valid_str == '' or days_valid_str == '0':
        days_valid = None
    else:
        try:
            days_valid = int(days_valid_str)
            if days_valid <= 0:
                days_valid = None
        except ValueError:
            flash(_('有效期格式错误'), 'error')
            return redirect(url_for('web.token_management'))

    if not name:
        flash(_('请输入Token名称'), 'error')
        return redirect(url_for('web.token_management'))

    try:
        import secrets
        from werkzeug.security import generate_password_hash
        raw_token = secrets.token_hex(32)
        token_hash_val = generate_password_hash(raw_token)

        from datetime import timedelta

        now = datetime.utcnow()
        token = Token(
            token_hash=token_hash_val,
            name=name,
            user_id=current_user.id,
            permissions=selected_perms,
            is_active=True,
            created_at=now
        )

        if days_valid:
            token.expires_at = now + timedelta(days=days_valid)

        db.session.add(token)
        db.session.commit()

        # 准备显示的数据 - 仅此时返回原始token
        from utils.timezone import format_datetime
        new_token_data = {
            'name': token.name,
            'token': raw_token,
            'expires_at': token.expires_at.isoformat() if token.expires_at else None,
            'expires_at_formatted': format_datetime(token.expires_at) if token.expires_at else _('永不过期')
        }

        # 存储在session中以便在下一页显示
        session['new_token_created'] = True
        session['new_token_data'] = new_token_data

        # 记录操作日志
        log = Log(
            level='info',
            message=log_msg(
                f'创建API Token: {name}',
                f'Create API Token: {name}'
            ),
            source='web',
            ip_address=request.remote_addr,
            user_id=current_user.id,
            details=f'token_id: {token.id}, permissions: {selected_perms}'
        )
        db.session.add(log)
        db.session.commit()

    except Exception as e:
        db.session.rollback()
        flash(_('创建Token失败: %(error)s') % {'error': str(e)}, 'error')

    return redirect(url_for('web.token_management'))


@web_bp.route('/tokens/<int:token_id>/toggle', methods=['POST'])
@login_required
def toggle_token(token_id):
    """切换Token状态"""
    if not current_user.is_admin():
        flash(_('需要管理员权限'), 'error')
        return redirect(url_for('web.token_management'))

    token = Token.query.get_or_404(token_id)

    # 检查权限：只有Token创建者或管理员可以操作
    if token.user_id != current_user.id and not current_user.is_admin():
        flash(_('没有权限操作此Token'), 'error')
        return redirect(url_for('web.token_management'))

    old_status = token.is_active
    token.is_active = not token.is_active
    db.session.commit()

    # 记录操作日志
    log = Log(
        level='info',
        message=log_msg(
            f'切换Token状态: {token.name} ({old_status} -> {token.is_active})',
            f'Toggle Token Status: {token.name} ({old_status} -> {token.is_active})'
        ),
        source='web',
        ip_address=request.remote_addr,
        user_id=current_user.id,
        details=f'token_id: {token.id}'
    )
    db.session.add(log)
    db.session.commit()

    status = _('启用') if token.is_active else _('禁用')
    flash(_('Token已%(status)s') % {'status': status}, 'success')
    return redirect(url_for('web.token_management'))


@web_bp.route('/tokens/<int:token_id>/delete', methods=['POST'])
@login_required
def delete_token(token_id):
    """删除Token"""
    if not current_user.is_admin():
        flash(_('需要管理员权限'), 'error')
        return redirect(url_for('web.token_management'))

    token = Token.query.get_or_404(token_id)

    # 检查权限：只有Token创建者或管理员可以操作
    if token.user_id != current_user.id and not current_user.is_admin():
        flash(_('没有权限操作此Token'), 'error')
        return redirect(url_for('web.token_management'))

    token_name = token.name

    # 记录删除日志
    log = Log(
        level='warning',
        message=log_msg(
            f'删除API Token: {token_name}',
            f'Delete API Token: {token_name}'
        ),
        source='web',
        ip_address=request.remote_addr,
        user_id=current_user.id,
        details=f'token_id: {token.id}'
    )
    db.session.add(log)

    db.session.delete(token)
    db.session.commit()

    flash(_('Token [%(name)s] 已删除') % {'name': token_name}, 'success')
    return redirect(url_for('web.token_management'))


@web_bp.route('/set-language/<lang>')
def switch_language(lang):
    """切换语言"""
    if lang in ['zh_CN', 'en']:
        session['lang'] = lang
    # 重定向回来源页面
    next_page = request.args.get('next') or request.referrer or url_for('web.dashboard')
    return redirect(next_page)


@web_bp.route('/tokens/<int:token_id>/refresh', methods=['POST'])
@login_required
def refresh_token(token_id):
    """刷新Token（生成新值）"""
    if not current_user.is_admin():
        flash(_('需要管理员权限'), 'error')
        return redirect(url_for('web.token_management'))

    token = Token.query.get_or_404(token_id)

    # 检查权限：只有Token创建者或管理员可以操作
    if token.user_id != current_user.id and not current_user.is_admin():
        flash(_('没有权限操作此Token'), 'error')
        return redirect(url_for('web.token_management'))

    try:
        import secrets
        from werkzeug.security import generate_password_hash

        # 生成新Token，存储哈希值
        new_raw_token = secrets.token_hex(32)
        token.token_hash = generate_password_hash(new_raw_token)

        # 可选：重置过期时间
        from datetime import timedelta

        # 保持原有过期时间或重置为30天后
        now = datetime.utcnow()
        if token.expires_at and token.expires_at < now:
            token.expires_at = now + timedelta(days=30)

        db.session.commit()

        # 记录操作日志
        log = Log(
            level='info',
            message=log_msg(
                f'刷新API Token: {token.name}',
                f'Refresh API Token: {token.name}'
            ),
            source='web',
            ip_address=request.remote_addr,
            user_id=current_user.id,
            details=f'token_id: {token.id}'
        )
        db.session.add(log)
        db.session.commit()

        # 将新Token存储在session中以便显示 - 仅此时可见
        from utils.timezone import format_datetime
        new_token_data = {
            'name': token.name,
            'token': new_raw_token,
            'expires_at': token.expires_at.isoformat() if token.expires_at else None,
            'expires_at_formatted': format_datetime(token.expires_at) if token.expires_at else _('永不过期')
        }

        session['new_token_created'] = True
        session['new_token_data'] = new_token_data

        flash(_('Token已刷新，请保存新Token'), 'success')

    except Exception as e:
        db.session.rollback()
        flash(_('刷新Token失败: %(error)s') % {'error': str(e)}, 'error')

    return redirect(url_for('web.token_management'))


@web_bp.route('/analytics')
@login_required
def user_analytics():
    """用户游玩数据分析"""
    from models.session import LoginSession
    from collections import defaultdict
    import requests

    view = request.args.get('view', '').strip()
    player_name = request.args.get('player_name', '').strip()
    player_uuid = request.args.get('player_uuid', '').strip()
    server_id = request.args.get('server_id', '').strip()

    # 总览数据
    overview = None
    overview_days = request.args.get('trend_days', 7, type=int)
    overview_servers = request.args.getlist('os')  # overview server filter

    if view == 'overview' or (not player_name):
        query = LoginSession.query
        all_sessions = query.all()

        # 时间范围筛选
        cutoff_time = datetime.utcnow() - timedelta(days=overview_days)
        time_filtered = [s for s in all_sessions if s.login_time and s.login_time >= cutoff_time]

        # 服务器筛选
        all_overview_servers = sorted(set(s.server_id or 'default' for s in all_sessions))
        if overview_servers:
            filtered = [s for s in time_filtered if (s.server_id or 'default') in overview_servers]
        else:
            filtered = time_filtered

        # 全服总在线时间
        total_online = sum(s.duration or 0 for s in filtered)
        # 最大单次在线时长
        max_single = max((s.duration or 0 for s in filtered), default=0)
        max_single_session = max(filtered, key=lambda s: s.duration or 0) if filtered else None

        # 玩家汇总统计
        player_stats = defaultdict(lambda: {'total_duration': 0, 'login_count': 0, 'max_single': 0})
        for s in filtered:
            name = s.player_name or 'Unknown'
            player_stats[name]['total_duration'] += s.duration or 0
            player_stats[name]['login_count'] += 1
            if (s.duration or 0) > player_stats[name]['max_single']:
                player_stats[name]['max_single'] = s.duration or 0

        # 最大单玩家在线时长
        if player_stats:
            top_duration_player = max(player_stats.items(), key=lambda x: x[1]['total_duration'])
            top_login_player = max(player_stats.items(), key=lambda x: x[1]['login_count'])
        else:
            top_duration_player = (None, {'total_duration': 0, 'login_count': 0, 'max_single': 0})
            top_login_player = (None, {'total_duration': 0, 'login_count': 0, 'max_single': 0})

        # 最大同时在线玩家数 (sweep line)
        events = []
        for s in filtered:
            if s.login_time:
                events.append((s.login_time, 1))
                lt = s.logout_time or datetime.utcnow()
                events.append((lt, -1))
        events.sort(key=lambda x: x[0])
        concurrent = 0
        max_concurrent = 0
        for _, delta in events:
            concurrent += delta
            if concurrent > max_concurrent:
                max_concurrent = concurrent

        # 玩家在线排行 (前15名)
        player_ranking = sorted(player_stats.items(), key=lambda x: x[1]['total_duration'], reverse=True)[:15]

        overview = {
            'total_online': total_online,
            'max_concurrent': max_concurrent,
            'max_single': max_single,
            'max_single_player': max_single_session.player_name if max_single_session else '-',
            'max_single_server': max_single_session.server_id if max_single_session else '-',
            'max_single_duration': max_single_session.duration if max_single_session else 0,
            'top_duration_player': top_duration_player[0],
            'top_duration_value': top_duration_player[1]['total_duration'],
            'top_login_player': top_login_player[0],
            'top_login_value': top_login_player[1]['login_count'],
            'total_players': len(player_stats),
            'player_ranking': player_ranking,
            'all_overview_servers': all_overview_servers,
            'overview_servers': overview_servers,
        }

    # 获取所有出现过登入记录的玩家
    all_players = db.session.query(
        Log.player_name, Log.player_uuid
    ).filter(
        Log.level == 'login',
        Log.source == 'api',
        Log.player_name.isnot(None)
    ).distinct().order_by(Log.player_name).all()

    # 区分白名单用户和游客
    whitelist_players = []
    guest_players = []
    for name, uuid in all_players:
        if is_whitelist_user(player_name=name, player_uuid=uuid):
            whitelist_players.append({'name': name, 'uuid': uuid})
        else:
            guest_players.append({'name': name, 'uuid': uuid})

    stats = None
    sessions = []
    gantt_data = []
    ip_geo = {}

    if player_name:
        stats = LoginSession.get_player_stats(player_name=player_name, player_uuid=player_uuid)
        all_player_sessions = LoginSession.get_player_sessions(
            player_name=player_name,
            player_uuid=player_uuid,
            server_id=server_id if server_id else None,
            limit=500
        )
        # 时间范围筛选
        cutoff_time = datetime.utcnow() - timedelta(days=overview_days)
        sessions = [s for s in all_player_sessions if s.login_time and s.login_time >= cutoff_time]

        # 甘特图数据（最近50条，反转顺序使最新在上）
        from utils.timezone import utc_to_local
        gantt_data = []
        for s in reversed(sessions[:50]):
            if s.login_time:
                login_local = utc_to_local(s.login_time)
                logout_local = utc_to_local(s.logout_time) if s.logout_time else utc_to_local(datetime.utcnow())
                gantt_data.append({
                    'start': login_local.isoformat(),
                    'end': logout_local.isoformat(),
                    'duration': s.duration,
                    'server': s.server_id,
                    'ip': s.login_ip or '',
                })

        if stats and stats.get('ip_ranking'):
            for ip, count in stats['ip_ranking'][:5]:
                if ip and ip != 'unknown' and ip not in ip_geo:
                    try:
                        resp = requests.get('https://uapis.cn/api/v1/network/ipinfo', params={'ip': ip}, timeout=3)
                        if resp.status_code == 200:
                            geo_data = resp.json()
                            ip_geo[ip] = {
                                'region': geo_data.get('region', 'Unknown'),
                                'isp': geo_data.get('isp', ''),
                                'lat': geo_data.get('latitude'),
                                'lng': geo_data.get('longitude'),
                            }
                        else:
                            ip_geo[ip] = {'region': 'N/A', 'isp': '', 'lat': None, 'lng': None}
                    except Exception:
                        ip_geo[ip] = {'region': 'N/A', 'isp': '', 'lat': None, 'lng': None}

    # 登陆趋势（共用 overview_days，如选定玩家则只显示该玩家）
    trend_days = overview_days
    trend_type = request.args.get('trend_type', 'all')
    trend_server_id = request.args.get('trend_server_id', '').strip()

    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    login_trend_data = defaultdict(int)
    for i in range(trend_days - 1, -1, -1):
        day_start = today - timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        query = Log.query.filter(
            Log.level == 'login',
            Log.source == 'api',
            Log.created_at >= day_start,
            Log.created_at < day_end
        )
        if trend_server_id:
            query = query.filter_by(server_id=trend_server_id)
        # 如果选了具体玩家，只统计该玩家
        if player_name:
            query = query.filter_by(player_name=player_name)
            day_count = query.count()
            login_trend_data[day_start.strftime('%m-%d')] = day_count
        elif trend_type == 'whitelist':
            day_logs = query.all()
            count = 0
            for log_entry in day_logs:
                if is_whitelist_user(player_name=log_entry.player_name, player_uuid=log_entry.player_uuid):
                    count += 1
            login_trend_data[day_start.strftime('%m-%d')] = count
        elif trend_type == 'guest':
            day_logs = query.all()
            count = 0
            for log_entry in day_logs:
                if not is_whitelist_user(player_name=log_entry.player_name, player_uuid=log_entry.player_uuid):
                    count += 1
            login_trend_data[day_start.strftime('%m-%d')] = count
        else:
            login_trend_data[day_start.strftime('%m-%d')] = query.count()

    is_player_view = bool(player_name)

    all_server_ids = [row[0] for row in db.session.query(Log.server_id).filter(
        Log.server_id.isnot(None), Log.level == 'login', Log.source == 'api'
    ).distinct().order_by(Log.server_id).all()]

    return render_template('analytics.html',
                           view=view,
                           overview=overview,
                           all_players=all_players,
                           whitelist_players=whitelist_players,
                           guest_players=guest_players,
                           player_name=player_name,
                           stats=stats,
                           sessions=sessions,
                           gantt_data=gantt_data,
                           ip_geo=ip_geo,
                           login_trend=login_trend_data,
                           trend_type=trend_type,
                           trend_days=trend_days,
                           trend_server_id=trend_server_id,
                           all_server_ids=all_server_ids,
                           server_id=server_id,
                           is_player_view=is_player_view)


@web_bp.route('/servers')
@login_required
def servers():
    """服务器管理页面"""
    from models.server_status import ServerStatus
    from models.session import LoginSession
    from collections import defaultdict

    # 收集所有在白名单和登陆日志中出现过的server_id
    whitelist_servers = set(row[0] for row in db.session.query(
        WhitelistEntry.server_id
    ).filter(WhitelistEntry.server_id.isnot(None)).distinct().all())

    log_servers = set(row[0] for row in db.session.query(
        Log.server_id
    ).filter(
        Log.server_id.isnot(None),
        Log.level == 'login',
        Log.source == 'api'
    ).distinct().all())

    all_server_ids = sorted(whitelist_servers | log_servers)

    # 获取每个服务器的详细信息
    server_list = []
    for sid in all_server_ids:
        # 在线状态
        status = ServerStatus.query.filter_by(server_id=sid).first()
        is_online = ServerStatus.is_server_online(sid) if status else False

        # 当前在线用户（LoginSession中logout_time为NULL的记录）
        online_sessions = LoginSession.query.filter_by(
            server_id=sid, logout_time=None
        ).all()
        online_count = len(online_sessions)
        online_users = []
        for s in online_sessions:
            online_users.append({
                'player_name': s.player_name,
                'player_uuid': s.player_uuid,
                'login_time': s.login_time,
                'login_ip': s.login_ip,
            })

        # 白名单条目数
        whitelist_count = WhitelistEntry.query.filter_by(
            server_id=sid, is_active=True
        ).count()

        # 总登陆次数（排除登出事件）
        total_logins = Log.query.filter(
            Log.server_id == sid,
            Log.level == 'login',
            Log.source == 'api',
            ~Log.details.like('%action: logout%')
        ).count()

        # 允许/拒绝统计
        allowed_logins = Log.query.filter(
            Log.server_id == sid,
            Log.level == 'login',
            Log.source == 'api',
            Log.details.like('%allowed: True%'),
            ~Log.details.like('%action: logout%')
        ).count()
        denied_logins = total_logins - allowed_logins

        # 今日登陆次数（排除登出事件）
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_logins = Log.query.filter(
            Log.server_id == sid,
            Log.level == 'login',
            Log.source == 'api',
            Log.created_at >= today,
            ~Log.details.like('%action: logout%')
        ).count()

        # 服务器名称（优先使用Server表中的名称，表不存在则用server_id）
        server_name = sid
        try:
            from models.server import Server as ServerModel
            server_record = ServerModel.query.filter_by(server_id=sid).first()
            if server_record:
                server_name = server_record.name
        except Exception:
            pass

        server_list.append({
            'server_id': sid,
            'server_name': server_name,
            'is_online': is_online,
            'last_heartbeat': status.last_heartbeat if status else None,
            'last_offline': status.last_offline if status else None,
            'online_count': online_count,
            'online_users': online_users,
            'whitelist_count': whitelist_count,
            'total_logins': total_logins,
            'allowed_logins': allowed_logins,
            'denied_logins': denied_logins,
            'today_logins': today_logins,
            'has_status': status is not None,
        })

    return render_template('servers.html', servers=server_list)


@web_bp.route('/api/servers/<server_id>/online-history')
@login_required
def server_online_history(server_id):
    """获取服务器在线人数历史数据（用于折线图）"""
    from models.session import LoginSession
    from utils.timezone import utc_to_local

    hours = request.args.get('hours', 24, type=int)
    if hours not in (6, 12, 24, 48, 72, 168):
        hours = 24

    now = datetime.utcnow()
    since = now - timedelta(hours=hours)

    def _naive(dt):
        """将datetime转为naive UTC，兼容aware/naive混合情况"""
        if dt is None:
            return None
        if dt.tzinfo is not None:
            from datetime import timezone
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    # 获取所有可能与时间窗口有交集的会话
    all_sessions = LoginSession.query.filter(
        LoginSession.server_id == server_id
    ).all()

    # 为每个会话提取 (start, end) 区间，fallback login_time -> created_at
    intervals = []
    for s in all_sessions:
        start = _naive(s.login_time) or _naive(s.created_at)
        if start is None:
            continue
        end = _naive(s.logout_time)  # None 表示仍在线
        intervals.append((start, end))

    # 按采样间隔统计每个时间点的在线人数
    interval = timedelta(minutes=5)
    data_points = []
    t = since
    while t <= now:
        count = 0
        for start, end in intervals:
            if start <= t and (end is None or end >= t):
                count += 1
        local_t = utc_to_local(t)
        data_points.append({
            'time': local_t.strftime('%m-%d %H:%M'),
            'count': count,
        })
        t += interval

    hour_labels = {6: '6h', 12: '12h', 24: '24h', 48: '48h', 72: '3d', 168: '7d'}

    return jsonify({
        'success': True,
        'server_id': server_id,
        'hours': hours,
        'label': hour_labels.get(hours, f'{hours}h'),
        'data': data_points,
    })