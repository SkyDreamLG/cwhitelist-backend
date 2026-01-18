# utils/auth.py
import jwt
import secrets
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, current_app

from models.token import Token
from models.database import db


# JWT配置 - 从应用配置获取
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
        'jti': secrets.token_hex(16)  # JWT ID
    }

    token = jwt.encode(payload, config['secret_key'], algorithm=config['algorithm'])
    return token


def validate_token(token_str):
    """验证令牌 - 支持JWT和简单API Key"""
    if not token_str:
        print("[AUTH] ❌ No token provided")
        return None

    print(f"[AUTH] 🔍 Validating token: {token_str[:16]}...")

    try:
        # 1. 首先检查数据库中的Token记录
        token = Token.query.filter_by(token=token_str).first()

        if not token:
            print(f"[AUTH] ❌ Token not found in database")
            return None

        print(f"[AUTH] ✅ Token found: {token.name} (ID: {token.id})")

        # 2. 检查Token是否有效
        if not token.is_active:
            print(f"[AUTH] ❌ Token is inactive")
            return None

        if token.is_expired():
            print(f"[AUTH] ❌ Token expired at {token.expires_at}")
            return None

        # 3. 如果是JWT格式，验证JWT签名
        config = get_jwt_config()

        # 检查是否是JWT格式（包含2个点）
        if token_str.count('.') == 2:
            try:
                # 尝试解码JWT
                payload = jwt.decode(token_str, config['secret_key'],
                                     algorithms=[config['algorithm']])
                print(f"[AUTH] ✅ Valid JWT for user {payload.get('user_id')}")

                # 确保JWT中的用户ID与数据库中的一致
                if 'user_id' in payload and payload['user_id'] != token.user_id:
                    print(f"[AUTH] ❌ JWT user_id mismatch")
                    return None

            except jwt.ExpiredSignatureError:
                print(f"[AUTH] ❌ JWT token expired")
                return None
            except jwt.InvalidTokenError as e:
                print(f"[AUTH] ❌ Invalid JWT: {e}")
                return None
            except Exception as e:
                print(f"[AUTH] ⚠️  JWT decode error: {e}")
                # 如果JWT解码失败，但数据库中有记录，仍然接受（降级处理）
                pass
        else:
            # 4. 不是JWT格式，直接使用API Key验证
            print(f"[AUTH] ✅ Valid API Key (non-JWT)")

        print(f"[AUTH] ✅ Token validation successful")
        print(f"[AUTH] 📊 Permissions - Read: {token.can_read}, Write: {token.can_write}, Delete: {token.can_delete}")

        return token

    except Exception as e:
        print(f"[AUTH] ❌ Token validation error: {str(e)}")
        import traceback
        print(f"[AUTH] Stack trace: {traceback.format_exc()}")
        return None


def require_api_auth(f):
    """API认证装饰器"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 从请求头获取Token
        auth_header = request.headers.get('Authorization', '')

        # 支持两种格式：Bearer token 或直接token
        if auth_header.startswith('Bearer '):
            token_str = auth_header[7:]
        else:
            # 也支持从查询参数获取
            token_str = request.args.get('token') or auth_header

        if not token_str:
            return jsonify({
                'success': False,
                'message': 'Authentication required. Please provide a valid token.'
            }), 401

        # 验证Token
        token = validate_token(token_str)
        if not token:
            return jsonify({
                'success': False,
                'message': 'Invalid or expired token.'
            }), 401

        # 检查Token权限（根据端点需要）
        endpoint = request.endpoint or ''
        method = request.method

        # 权限检查逻辑
        if not check_token_permissions(token, endpoint, method):
            return jsonify({
                'success': False,
                'message': 'Insufficient permissions for this operation.'
            }), 403

        # 将Token对象附加到请求上下文
        request.token = token

        # 更新使用统计
        token.update_usage(request.remote_addr)

        return f(*args, **kwargs)

    return decorated_function


def check_token_permissions(token, endpoint, method):
    """检查Token权限"""
    # 如果是只读操作，只需要can_read权限
    if method == 'GET':
        if not token.can_read:
            return False

    # 如果是写入操作，需要can_write权限
    elif method in ['POST', 'PUT', 'PATCH']:
        if not token.can_write:
            return False

    # 如果是删除操作，需要can_delete权限
    elif method == 'DELETE':
        if not token.can_delete:
            return False

    # 管理操作需要can_manage权限
    if endpoint and 'manage' in endpoint:
        if not token.can_manage:
            return False

    return True


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
    """为服务器创建API令牌"""
    from models.server import Server
    from models.database import db

    # 检查服务器是否存在
    server = Server.query.filter_by(server_id=server_id).first()
    if not server:
        return None

    # 生成Token（这里使用简单的随机字符串，不使用JWT）
    token_str = secrets.token_hex(32)

    # 创建Token记录
    token = Token(
        token=token_str,
        name=name,
        user_id=1,  # 默认管理员ID，应该根据实际情况调整
        can_read=True,
        can_write=True,
        can_delete=False,
        can_manage=False
    )

    if permissions:
        for key, value in permissions.items():
            setattr(token, key, value)

    if days_valid:
        from utils.timezone import now_utc
        token.expires_at = now_utc() + timedelta(days=days_valid)

    db.session.add(token)
    db.session.commit()

    return token_str