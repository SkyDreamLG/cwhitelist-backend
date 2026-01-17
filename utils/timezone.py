# utils/timezone.py
from datetime import datetime, timezone, timedelta
import pytz
from flask import current_app


def get_app_timezone():
    """获取应用的时区设置"""
    timezone_str = current_app.config.get('TIMEZONE', 'UTC')
    try:
        return pytz.timezone(timezone_str)
    except pytz.UnknownTimeZoneError:
        # 如果时区无效，使用UTC
        return pytz.UTC


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
        'current_local': now_local_dt.strftime('%Y-%m-%d %H:%M:%S')
    }