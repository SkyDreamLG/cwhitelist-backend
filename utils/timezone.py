# utils/timezone.py
from datetime import datetime, timezone, timedelta
import pytz
from flask import current_app


def get_app_timezone():
    """获取应用的时区设置，支持动态从数据库加载"""
    try:
        # 先从应用配置获取
        timezone_str = current_app.config.get('TIMEZONE', 'UTC')

        # 如果应用正在运行，尝试从数据库获取最新的时区设置
        if current_app:
            from models.setting import Setting
            from models.database import db

            # 使用应用上下文
            with current_app.app_context():
                try:
                    timezone_setting = Setting.query.filter_by(key='timezone').first()
                    if timezone_setting and timezone_setting.value:
                        timezone_str = timezone_setting.value
                except Exception:
                    # 如果数据库查询失败，使用配置中的时区
                    pass

        return pytz.timezone(timezone_str)
    except pytz.UnknownTimeZoneError:
        # 如果时区无效，使用UTC
        return pytz.UTC


def update_app_timezone(timezone_str):
    """更新应用时区设置"""
    try:
        # 验证时区有效性
        tz = pytz.timezone(timezone_str)

        # 更新应用配置
        current_app.config['TIMEZONE'] = timezone_str

        # 保存到数据库
        from models.setting import Setting
        from models.database import db

        with current_app.app_context():
            Setting.set_value('timezone', timezone_str, '系统时区设置', 'system')

        return True
    except pytz.UnknownTimeZoneError:
        return False


def utc_to_local(utc_dt):
    """将UTC时间转换为本地时间"""
    if not utc_dt:
        return None

    if not utc_dt.tzinfo:
        utc_dt = utc_dt.replace(tzinfo=pytz.UTC)

    local_tz = get_app_timezone()
    return utc_dt.astimezone(local_tz)


def local_to_utc(local_dt):
    """将本地时间转换为UTC时间"""
    if not local_dt:
        return None

    if not local_dt.tzinfo:
        local_tz = get_app_timezone()
        local_dt = local_tz.localize(local_dt)

    return local_dt.astimezone(pytz.UTC)


def now_utc():
    """获取当前UTC时间"""
    return datetime.now(pytz.UTC)


def now_local():
    """获取当前本地时间"""
    return utc_to_local(now_utc())


def format_datetime(dt, format_str='%Y-%m-%d %H:%M:%S', timezone_aware=True):
    """格式化日期时间，自动转换为本地时间"""
    if not dt:
        return ''

    # 如果时间没有时区信息，假设它是UTC
    if not dt.tzinfo and timezone_aware:
        dt = dt.replace(tzinfo=pytz.UTC)

    # 转换为本地时间
    if timezone_aware and dt.tzinfo:
        local_dt = utc_to_local(dt)
    else:
        local_dt = dt

    # 移除时区信息用于显示
    if local_dt.tzinfo:
        local_dt = local_dt.replace(tzinfo=None)

    return local_dt.strftime(format_str)


def parse_datetime(dt_str, timezone_aware=True):
    """解析日期时间字符串，转换为本地时间"""
    if not dt_str:
        return None

    try:
        # 尝试解析ISO格式
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    except ValueError:
        # 尝试解析其他常见格式
        formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M',
            '%Y-%m-%d',
            '%Y/%m/%d %H:%M:%S',
            '%Y/%m/%d %H:%M',
            '%Y/%m/%d'
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(dt_str, fmt)
                break
            except ValueError:
                continue
        else:
            return None

    # 如果没有时区信息，假设是本地时间
    if not dt.tzinfo and timezone_aware:
        local_tz = get_app_timezone()
        dt = local_tz.localize(dt)

    return dt


def get_timezone_info():
    """获取时区信息"""
    tz = get_app_timezone()
    now_utc_dt = now_utc()
    now_local_dt = utc_to_local(now_utc_dt)

    return {
        'timezone': str(tz),
        'utc_offset': now_local_dt.utcoffset().total_seconds() / 3600,
        'is_dst': now_local_dt.dst() != timedelta(0),
        'current_utc': now_utc_dt.strftime('%Y-%m-%d %H:%M:%S'),
        'current_local': now_local_dt.strftime('%Y-%m-%d %H:%M:%S'),
        'timezone_name': str(tz).split('/')[-1].replace('_', ' ')
    }


def get_common_timezones():
    """获取常用时区列表"""
    common_timezones = {
        '常用时区': [
            ('UTC', '协调世界时'),
            ('Asia/Shanghai', '中国标准时间 (北京)'),
            ('Asia/Tokyo', '日本标准时间 (东京)'),
            ('Asia/Seoul', '韩国标准时间 (首尔)'),
            ('Asia/Singapore', '新加坡标准时间'),
            ('Asia/Hong_Kong', '香港标准时间'),
        ],
        '美洲': [
            ('America/New_York', '美国东部时间 (纽约)'),
            ('America/Chicago', '美国中部时间 (芝加哥)'),
            ('America/Denver', '美国山地时间 (丹佛)'),
            ('America/Los_Angeles', '美国太平洋时间 (洛杉矶)'),
            ('America/Toronto', '加拿大东部时间 (多伦多)'),
            ('America/Vancouver', '加拿大太平洋时间 (温哥华)'),
        ],
        '欧洲': [
            ('Europe/London', '格林尼治标准时间 (伦敦)'),
            ('Europe/Paris', '中欧时间 (巴黎)'),
            ('Europe/Berlin', '中欧时间 (柏林)'),
            ('Europe/Moscow', '莫斯科时间'),
            ('Europe/Istanbul', '土耳其时间 (伊斯坦布尔)'),
        ],
        '大洋洲': [
            ('Australia/Sydney', '澳大利亚东部时间 (悉尼)'),
            ('Australia/Melbourne', '澳大利亚东部时间 (墨尔本)'),
            ('Australia/Perth', '澳大利亚西部时间 (珀斯)'),
            ('Pacific/Auckland', '新西兰时间 (奥克兰)'),
        ]
    }

    return common_timezones


def get_all_timezones():
    """获取所有可用时区"""
    return pytz.all_timezones


def get_timezone_by_country(country_code=None):
    """按国家获取时区"""
    # 这里可以扩展为根据国家代码获取时区
    # 目前返回常用时区
    return get_common_timezones()