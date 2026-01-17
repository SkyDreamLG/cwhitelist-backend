from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from sqlalchemy import desc, or_
from datetime import datetime

import json
from werkzeug.utils import secure_filename
import os

from config import config
from models.database import db
from models.whitelist import WhitelistEntry
from models.setting import Setting
from models.log import Log

web_bp = Blueprint('web', __name__)


# OOBE 检查函数
def is_oobe_required():
    """检查是否需要OOBE设置"""
    from models.user import User
    from models.setting import Setting

    try:
        # 检查是否有管理员用户
        admin_exists = User.query.filter_by(role='admin').first() is not None

        # 检查必要设置是否存在
        required_settings = ['site_title', 'admin_email']
        settings_exist = True
        for key in required_settings:
            if not Setting.query.filter_by(key=key).first():
                settings_exist = False
                break

        # 如果需要OOBE，返回True
        return not (admin_exists and settings_exist)
    except Exception as e:
        # 如果查询出错，说明数据库可能还没初始化，需要OOBE
        print(f"OOBE检查出错: {e}")
        return True


@web_bp.route('/')
def index():
    """首页"""
    if is_oobe_required():
        return redirect(url_for('web.oobe'))
    return redirect(url_for('auth.login'))


@web_bp.route('/dashboard')
@login_required
def dashboard():
    """仪表板"""

    # 获取统计信息
    total_entries = WhitelistEntry.query.count()
    active_entries = WhitelistEntry.query.filter_by(is_active=True).count()

    # 获取日志统计
    log_stats = {
        'total': Log.query.count(),
        'info': Log.query.filter_by(level='info').count(),
        'warning': Log.query.filter_by(level='warning').count(),
        'error': Log.query.filter_by(level='error').count(),
        'login': Log.query.filter_by(level='login').count(),
    }

    # 获取用户统计
    from models.user import User
    user_count = User.query.count()

    # 获取最近添加的白名单条目
    recent_entries = WhitelistEntry.query.order_by(desc(WhitelistEntry.created_at)).limit(10).all()

    return render_template('dashboard.html',
                           total_entries=total_entries,
                           active_entries=active_entries,
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

    # 将字符串转换为布尔值
    active_only_bool = active_only == 'true'

    # 构建查询
    query = WhitelistEntry.query

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
        'active_only': active_only_bool
    }

    return render_template('whitelist.html',
                           entries=entries_with_login_info,
                           pagination=pagination,
                           filters=filters_dict)


@web_bp.route('/whitelist/add', methods=['POST'])
@login_required
def add_whitelist():
    """添加白名单条目"""
    from utils.timezone import parse_datetime, local_to_utc

    entry_type = request.form.get('type', '').strip().lower()
    value = request.form.get('value', '').strip()
    description = request.form.get('description', '').strip()
    expires_at = request.form.get('expires_at')

    if not entry_type or not value:
        flash('请填写类型和值', 'error')
        return redirect(url_for('web.whitelist'))

    if entry_type not in ['name', 'uuid', 'ip']:
        flash('类型必须为: name, uuid 或 ip', 'error')
        return redirect(url_for('web.whitelist'))

    # 检查是否已存在
    existing = WhitelistEntry.query.filter_by(
        type=entry_type,
        value=value
    ).first()

    if existing:
        flash('条目已存在', 'error')
        return redirect(url_for('web.whitelist'))

    # 创建条目
    entry = WhitelistEntry(
        type=entry_type,
        value=value,
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
            flash(f'过期时间格式错误: {str(e)}', 'error')
            return redirect(url_for('web.whitelist'))

    db.session.add(entry)
    db.session.commit()

    # 记录操作日志
    log = Log(
        level='info',
        message=f'添加白名单条目: {entry_type}={value}',
        source='web',
        ip_address=request.remote_addr,
        user_id=current_user.id,
        details=f'entry_id: {entry.id}, description: {description}'
    )
    db.session.add(log)
    db.session.commit()

    flash('白名单条目添加成功', 'success')
    return redirect(url_for('web.whitelist'))


@web_bp.route('/whitelist/<entry_id>/toggle', methods=['POST'])
@login_required
def toggle_whitelist(entry_id):
    """切换白名单条目状态"""
    entry = WhitelistEntry.query.get(entry_id)
    if not entry:
        flash('条目不存在', 'error')
        return redirect(url_for('web.whitelist'))

    entry.is_active = not entry.is_active
    db.session.commit()

    # 记录操作日志
    log = Log(
        level='info',
        message=f'切换白名单条目状态: {entry.type}={entry.value} -> {entry.is_active}',
        source='web',
        ip_address=request.remote_addr,
        user_id=current_user.id,
        details=f'entry_id: {entry.id}, new_status: {entry.is_active}'
    )
    db.session.add(log)
    db.session.commit()

    status = '启用' if entry.is_active else '禁用'
    flash(f'条目已{status}', 'success')
    return redirect(url_for('web.whitelist'))


@web_bp.route('/whitelist/<entry_id>/delete', methods=['POST'])
@login_required
def delete_whitelist(entry_id):
    """删除白名单条目"""
    entry = WhitelistEntry.query.get(entry_id)
    if not entry:
        flash('条目不存在', 'error')
        return redirect(url_for('web.whitelist'))

    # 记录操作日志
    log = Log(
        level='warning',
        message=f'删除白名单条目: {entry.type}={entry.value}',
        source='web',
        ip_address=request.remote_addr,
        user_id=current_user.id,
        details=f'entry_id: {entry.id}, description: {entry.description}'
    )
    db.session.add(log)

    db.session.delete(entry)
    db.session.commit()

    flash('条目已删除', 'success')
    return redirect(url_for('web.whitelist'))


@web_bp.route('/logs')
@login_required
def logs():
    """日志查看"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    level = request.args.get('level', '')
    source = request.args.get('source', '')

    # 构建查询
    query = Log.query

    if level:
        query = query.filter_by(level=level)

    if source:
        query = query.filter_by(source=source)

    # 分页
    pagination = query.order_by(desc(Log.created_at)).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # 获取日志级别和来源的统计
    level_stats = db.session.query(
        Log.level,
        db.func.count(Log.id)
    ).group_by(Log.level).all()

    source_stats = db.session.query(
        Log.source,
        db.func.count(Log.id)
    ).group_by(Log.source).all()

    filters = {
        'level': level,
        'source': source
    }

    return render_template('logs.html',
                           logs=pagination.items,
                           pagination=pagination,
                           level_stats=dict(level_stats),
                           source_stats=dict(source_stats),
                           filters=filters)


@web_bp.route('/logs/clear', methods=['POST'])
@login_required
def clear_logs():
    """清空日志 - 修复版本"""
    if not current_user.is_admin():
        flash('需要管理员权限', 'error')
        return redirect(url_for('web.logs'))

    # 检查是否为测试请求
    is_test = request.form.get('test') == 'true'

    try:
        # 获取当前日志总数
        total_logs = Log.query.count()

        if is_test:
            # 测试模式，不实际删除
            flash(f'测试模式：当前有 {total_logs} 条日志，点击确认后将清空', 'info')
            return redirect(url_for('web.logs'))

        if total_logs == 0:
            flash('没有日志可清空', 'info')
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
            message=f'管理员清空日志，删除了 {deleted_count} 条记录',
            source='web',
            ip_address=request.remote_addr,
            user_id=current_user.id,
            details=f'user: {current_user.username}, cleared: {deleted_count}, remaining: {remaining_count}'
        )
        db.session.add(operation_log)
        db.session.commit()

        flash(f'成功清空 {deleted_count} 条日志，剩余 {remaining_count} 条', 'success')

    except Exception as e:
        db.session.rollback()
        print(f"清空日志异常: {e}")
        flash(f'清空日志失败: {str(e)}', 'error')

    return redirect(url_for('web.logs'))


@web_bp.route('/settings')
@login_required
def settings():
    """系统设置"""
    if not current_user.is_admin():
        flash('需要管理员权限', 'error')
        return redirect(url_for('web.dashboard'))

    settings_list = Setting.query.order_by(Setting.category, Setting.key).all()

    # 按分类分组
    settings_by_category = {}
    for setting in settings_list:
        category = setting.category or 'general'
        if category not in settings_by_category:
            settings_by_category[category] = []
        settings_by_category[category].append(setting)

    return render_template('settings.html',
                           settings_by_category=settings_by_category)


@web_bp.route('/settings/save', methods=['POST'])
@login_required
def save_settings():
    """保存系统设置"""
    if not current_user.is_admin():
        flash('需要管理员权限', 'error')
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
            message='更新系统设置',
            source='web',
            ip_address=request.remote_addr,
            user_id=current_user.id
        )
        db.session.add(log)
        db.session.commit()

        flash('设置已保存', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'保存设置失败: {str(e)}', 'error')

    return redirect(url_for('web.settings'))


@web_bp.route('/api/docs')
@login_required
def api_docs():
    """API文档"""
    return render_template('api_docs.html')


@web_bp.route('/about')
def about():
    """关于页面"""
    return render_template('about.html')


@web_bp.route('/oobe', methods=['GET', 'POST'])
def oobe():
    """OOBE设置页面"""
    # 如果不需要OOBE，重定向到登录页
    if not is_oobe_required():
        print("OOBE不需要，重定向到登录页")
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        # 处理OOBE设置
        admin_email = request.form.get('admin_email', '').strip()
        admin_password = request.form.get('admin_password', '')
        admin_confirm = request.form.get('admin_confirm', '')
        site_title = request.form.get('site_title', '').strip()

        # 验证输入
        errors = []

        if not admin_email:
            errors.append('请填写管理员邮箱')

        if not admin_password:
            errors.append('请填写管理员密码')
        elif admin_password != admin_confirm:
            errors.append('两次输入的密码不一致')
        elif len(admin_password) < 8:
            errors.append('密码长度至少8位')

        if not site_title:
            errors.append('请填写站点标题')

        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('oobe.html')

        try:
            from models.user import User

            # 检查是否已存在管理员用户
            existing_admin = User.query.filter_by(role='admin').first()
            if existing_admin:
                # 更新现有管理员
                existing_admin.email = admin_email
                existing_admin.set_password(admin_password)
            else:
                # 创建管理员用户
                admin_user = User(
                    username='admin',
                    email=admin_email,
                    role='admin',
                    is_active=True
                )
                admin_user.set_password(admin_password)
                db.session.add(admin_user)

            # 保存设置
            Setting.set_value('site_title', site_title, '站点标题', 'system')
            Setting.set_value('admin_email', admin_email, '管理员邮箱', 'system')
            Setting.set_value('app_name', site_title, '应用名称', 'system')

            # 设置默认值
            default_settings = [
                ('registration_enabled', 'false', '允许用户注册', 'security'),
                ('log_retention_days', '30', '日志保留天数', 'logging'),
                ('max_login_attempts', '5', '最大登录尝试次数', 'security'),
            ]

            for key, value, description, category in default_settings:
                Setting.set_value(key, value, description, category)

            db.session.commit()

            flash('系统初始化完成，请使用管理员账号登录', 'success')
            return redirect(url_for('auth.login'))

        except Exception as e:
            db.session.rollback()
            flash(f'初始化失败: {str(e)}', 'error')
            return render_template('oobe.html')

    return render_template('oobe.html')


@web_bp.route('/whitelist/import', methods=['POST'])
@login_required
def import_whitelist():
    """从JSON文件导入白名单"""
    try:
        if 'json_file' not in request.files:
            flash('请选择JSON文件', 'error')
            return redirect(url_for('web.whitelist'))

        file = request.files['json_file']
        if file.filename == '':
            flash('请选择JSON文件', 'error')
            return redirect(url_for('web.whitelist'))

        if not file.filename.endswith('.json'):
            flash('只支持JSON文件', 'error')
            return redirect(url_for('web.whitelist'))

        # 读取文件内容
        file_content = file.read().decode('utf-8')
        data = json.loads(file_content)

        if not isinstance(data, list):
            flash('JSON格式不正确，应该是一个数组', 'error')
            return redirect(url_for('web.whitelist'))

        # 获取导入选项
        skip_existing = request.form.get('skip_existing') == 'on'
        set_inactive = request.form.get('set_inactive') == 'on'
        description = request.form.get('description', '').strip()

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

                # 验证类型
                if entry_type not in ['name', 'uuid', 'ip']:
                    error_count += 1
                    continue

                # 检查是否已存在
                existing = WhitelistEntry.query.filter_by(
                    type=entry_type,
                    value=value
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
            message=f'导入白名单数据: {imported_count}条成功，{skipped_count}条跳过，{error_count}条错误',
            source='web',
            ip_address=request.remote_addr,
            user_id=current_user.id,
            details=f'file: {file.filename}, total_entries: {len(data)}'
        )
        db.session.add(log)
        db.session.commit()

        flash(f'导入完成: {imported_count}条成功导入，{skipped_count}条跳过，{error_count}条错误', 'success')

    except json.JSONDecodeError:
        flash('JSON文件格式不正确', 'error')
    except Exception as e:
        db.session.rollback()
        flash(f'导入失败: {str(e)}', 'error')

    return redirect(url_for('web.whitelist'))


@web_bp.route('/whitelist/export')
@login_required
def export_whitelist():
    """导出白名单为JSON"""
    try:
        # 获取查询参数
        active_only = request.args.get('active_only', 'true').lower() == 'true'
        include_expired = request.args.get('include_expired', 'false').lower() == 'true'

        # 构建查询
        query = WhitelistEntry.query

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
                'description': entry.description,
                'created_by': entry.created_by,
                'created_at': entry.created_at.isoformat() if entry.created_at else None,
                'expires_at': entry.expires_at.isoformat() if entry.expires_at else None,
                'is_active': entry.is_active
            })

        # 记录导出操作日志
        log = Log(
            level='info',
            message=f'导出白名单数据: {len(entries)}条',
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
        flash(f'导出失败: {str(e)}', 'error')
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
        flash('需要管理员权限', 'error')
        return redirect(url_for('web.dashboard'))

    from utils.timezone import get_common_timezones, get_timezone_info

    return render_template('settings_timezone.html',
                           common_timezones=get_common_timezones(),
                           timezone_info=get_timezone_info())


@web_bp.route('/settings/timezone/save', methods=['POST'])
@login_required
def save_timezone():
    """保存时区设置"""
    if not current_user.is_admin():
        return jsonify({
            'success': False,
            'message': '需要管理员权限'
        }), 403

    try:
        timezone_str = request.form.get('timezone', '').strip()

        if not timezone_str:
            return jsonify({
                'success': False,
                'message': '请选择时区'
            }), 400

        # 验证时区有效性
        import pytz
        try:
            pytz.timezone(timezone_str)
        except pytz.UnknownTimeZoneError:
            return jsonify({
                'success': False,
                'message': '无效的时区'
            }), 400

        # 保存到数据库
        from models.setting import Setting
        Setting.set_value('timezone', timezone_str, '系统时区设置', 'system')

        # 更新应用配置（需要重启应用才能完全生效）
        # 这里我们先保存到数据库，应用会在下次请求时加载

        # 记录操作日志
        log = Log(
            level='info',
            message=f'更新系统时区设置: {timezone_str}',
            source='web',
            ip_address=request.remote_addr,
            user_id=current_user.id,
            details=f'old_timezone: {config.get("TIMEZONE")}, new_timezone: {timezone_str}'
        )
        db.session.add(log)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': '时区设置已保存',
            'timezone': timezone_str
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'保存失败: {str(e)}'
        }), 500


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