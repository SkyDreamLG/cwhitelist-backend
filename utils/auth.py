# utils/auth.py
import jwt
import secrets
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, current_app

from models.token import Token
from models.database import db


def get_jwt_config():
    """获取JWT配置"""
    return {
        'secret_key': current_app.config.get('JWT_SECRET_KEY', 'change-this-in-production'),
        'algorithm': current_app.config.get('JWT_ALGORITHM', 'HS256'),
        'expiration_hours': current_app.config.get('JWT_EXPIRATION_HOURS', 24)
    }


def generate_token(user_id, purpose='api'):
    """生成JWT令牌"""
    config = get_jwt_config()

    payload = {
        'user_id': user_id,
        'purpose': purpose,
        'exp': datetime.utcnow() + timedelta(hours=config['expiration_hours']),
        'iat': datetime.utcnow(),
        'jti': secrets.token_hex(16)
    }

    token = jwt.encode(payload, config['secret_key'], algorithm=config['algorithm'])
    return token


def validate_token(token_str):
    """验证令牌 - 支持JWT和简单API Key"""
    if not token_str:
        return None

    try:
        # JWT验证
        if token_str.count('.') == 2:
            config = get_jwt_config()
            try:
                payload = jwt.decode(token_str, config['secret_key'],
                                     algorithms=[config['algorithm']])
                user_id = payload.get('user_id')

                token = Token.query.filter_by(
                    user_id=user_id, is_active=True
                ).first()
                if token:
                    return token
                return None

            except jwt.ExpiredSignatureError:
                return None
            except jwt.InvalidTokenError:
                return None

        # API Key验证 — 哈希比对
        token = Token.find_by_raw_token(token_str)
        if not token:
            return None

        if not token.is_active:
            return None

        if token.is_expired():
            return None

        return token

    except Exception:
        return None


def require_api_auth(required_permission=None):
    """API认证装饰器 - 细粒度权限控制

    Args:
        required_permission: 权限字符串或字符串列表（满足任一即可）
            - "whitelist:read"      单一权限
            - ["whitelist:read", "whitelist:write"]  任一满足即放行
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            auth_header = request.headers.get('Authorization', '')

            if auth_header.startswith('Bearer '):
                token_str = auth_header[7:]
            else:
                token_str = request.args.get('token') or auth_header

            if not token_str:
                return jsonify({
                    'success': False,
                    'message': 'Authentication required. Please provide a valid token.'
                }), 401

            token = validate_token(token_str)
            if not token:
                return jsonify({
                    'success': False,
                    'message': 'Invalid or expired token.'
                }), 401

            if required_permission and not token.has_permission(required_permission):
                return jsonify({
                    'success': False,
                    'message': 'Insufficient permissions for this operation.'
                }), 403

            request.token = token
            token.update_usage(request.remote_addr)

            return f(*args, **kwargs)

        return decorated_function

    if callable(required_permission):
        f = required_permission
        required_permission = None
        return decorator(f)

    return decorator


def require_auth(roles=None):
    """要求认证的装饰器（用于Web界面）"""

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from flask_login import current_user

            if not current_user.is_authenticated:
                return jsonify({
                    'success': False,
                    'message': 'Authentication required'
                }), 401

            if roles and current_user.role not in roles:
                return jsonify({
                    'success': False,
                    'message': 'Insufficient permissions'
                }), 403

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def hash_password(password):
    """哈希密码"""
    from werkzeug.security import generate_password_hash
    return generate_password_hash(password)


def verify_password(password_hash, password):
    """验证密码"""
    from werkzeug.security import check_password_hash
    return check_password_hash(password_hash, password)


def generate_api_key():
    """生成API密钥"""
    return secrets.token_hex(32)


def create_server_token(server_id, name, permissions=None, days_valid=365):
    """为服务器创建API令牌 - 返回原始token字符串，仅此时可见"""
    from models.server import Server
    from werkzeug.security import generate_password_hash
    from utils.permissions import Permission

    server = Server.query.filter_by(server_id=server_id).first()
    if not server:
        return None

    raw_token = secrets.token_hex(32)
    token_hash = generate_password_hash(raw_token)

    token = Token(
        token_hash=token_hash,
        name=name,
        user_id=1,
        permissions=list(permissions or []) if permissions else [],
    )

    if days_valid:
        from utils.timezone import now_utc
        token.expires_at = now_utc() + timedelta(days=days_valid)

    db.session.add(token)
    db.session.commit()

    return raw_token
