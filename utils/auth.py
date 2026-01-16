import jwt
import secrets
from datetime import datetime, timedelta
from functools import wraps

from models.token import Token
from models.database import db

# JWT配置
JWT_SECRET_KEY = 'change-this-in-production'
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_HOURS = 24


def generate_token(user_id, purpose='api'):
    """生成JWT令牌"""
    payload = {
        'user_id': user_id,
        'purpose': purpose,
        'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
        'iat': datetime.utcnow(),
        'jti': secrets.token_hex(16)  # JWT ID
    }

    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return token


def validate_token(token_str):
    """验证JWT令牌"""
    try:
        payload = jwt.decode(token_str, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])

        # 检查令牌是否在数据库中
        token = Token.query.filter_by(token=token_str).first()
        if not token or not token.is_valid():
            return None

        return token

    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
    except Exception:
        return None


def require_auth(roles=None):
    """要求认证的装饰器"""

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from flask import request, jsonify
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