import re
import ipaddress
from uuid import UUID


def validate_email(email):
    """验证邮箱格式"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_password(password):
    """验证密码强度"""
    if len(password) < 8:
        return False

    # 必须包含字母和数字
    has_letter = re.search(r'[a-zA-Z]', password)
    has_digit = re.search(r'\d', password)

    return has_letter and has_digit


def validate_uuid(uuid_str):
    """验证UUID格式"""
    try:
        UUID(uuid_str)
        return True
    except ValueError:
        return False


def validate_ip_address(ip_str):
    """验证IP地址格式"""
    try:
        ipaddress.ip_address(ip_str)
        return True
    except ValueError:
        return False


def validate_ip_pattern(pattern):
    """验证IP模式（支持通配符）"""
    # 简单的IP模式验证
    pattern = pattern.strip()

    # 允许通配符*
    if '*' in pattern:
        parts = pattern.split('.')
        if len(parts) != 4:
            return False

        for part in parts:
            if part != '*' and not part.isdigit():
                return False
            if part.isdigit() and not 0 <= int(part) <= 255:
                return False

        return True

    # 否则验证标准IP地址
    return validate_ip_address(pattern)


def validate_minecraft_username(username):
    """验证Minecraft用户名"""
    if len(username) < 3 or len(username) > 16:
        return False

    # 只能包含字母、数字和下划线
    pattern = r'^[a-zA-Z0-9_]+$'
    return re.match(pattern, username) is not None