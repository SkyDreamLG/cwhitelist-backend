from datetime import datetime, timedelta
import secrets
from flask_babel import _
from .database import db
from utils.timezone import now_utc
from werkzeug.security import generate_password_hash, check_password_hash
import pytz
import html


class Token(db.Model):
    """API令牌模型 - Token以哈希形式存储，权限为细粒度字符串列表"""
    __tablename__ = 'tokens'

    id = db.Column(db.Integer, primary_key=True)
    token_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(128), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user = db.relationship('User', backref='tokens')
    created_at = db.Column(db.DateTime, default=now_utc)
    expires_at = db.Column(db.DateTime)
    last_used = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)

    # 细粒度权限：JSON数组，如 ["whitelist:read", "login:log"]
    permissions = db.Column(db.JSON, default=list, nullable=False)

    # 使用统计
    use_count = db.Column(db.Integer, default=0)
    last_ip = db.Column(db.String(45))

    def has_permission(self, required):
        """检查是否拥有指定权限。支持 *:* 超级权限。

        Args:
            required: 权限字符串，或权限字符串列表（满足任一即可）
        """
        from utils.permissions import Permission

        if Permission.FULL in (self.permissions or []):
            return True

        if isinstance(required, list):
            return bool(set(required) & set(self.permissions or []))
        return required in (self.permissions or [])

    def check_raw_token(self, raw_token):
        """验证原始Token是否匹配存储的哈希值"""
        if not raw_token or not self.token_hash:
            return False
        return check_password_hash(self.token_hash, raw_token)

    def is_valid(self):
        """检查Token是否有效"""
        try:
            if not self.is_active:
                return False

            if self.expires_at:
                now = now_utc()
                if now > self.expires_at:
                    return False

            return True
        except Exception as e:
            print(f"[TOKEN] Error checking token validity: {e}")
            return False

    def update_usage(self, ip_address):
        """更新使用信息"""
        self.last_used = now_utc()
        self.use_count += 1
        self.last_ip = ip_address
        db.session.commit()

    def get_permissions_display(self):
        """获取权限显示文本"""
        from utils.permissions import Permission

        if Permission.FULL in (self.permissions or []):
            return _('全部权限')

        if not self.permissions:
            return _('无')

        labels = [_(Permission.get_label_key(p)) for p in self.permissions]
        return '、'.join(labels)

    def to_dict(self):
        """转换为字典"""
        from utils.timezone import format_datetime
        return {
            'id': self.id,
            'name': html.escape(self.name) if self.name else '',
            'token': None,
            'user_id': self.user_id,
            'username': html.escape(self.user.username) if self.user and self.user.username else '未知用户',
            'created_at': format_datetime(self.created_at) if self.created_at else None,
            'expires_at': format_datetime(self.expires_at) if self.expires_at else None,
            'last_used': format_datetime(self.last_used) if self.last_used else None,
            'is_active': self.is_active,
            'permissions': list(self.permissions or []),
            'stats': {
                'use_count': self.use_count,
                'last_ip': html.escape(self.last_ip) if self.last_ip else None
            }
        }

    def is_expired(self):
        """检查Token是否已过期"""
        if not self.expires_at:
            return False

        from utils.timezone import now_utc
        current_time = now_utc()

        if not self.expires_at.tzinfo:
            expires_at_utc = self.expires_at.replace(tzinfo=pytz.UTC)
        else:
            expires_at_utc = self.expires_at

        return current_time > expires_at_utc

    @classmethod
    def create_token(cls, user_id, name, permissions=None, days_valid=365):
        """创建新令牌 - 返回(raw_token, token_obj)元组，raw_token仅此时可见"""
        from utils.timezone import now_utc
        from datetime import timedelta
        from utils.permissions import Permission

        if name:
            name = html.escape(name.strip())
            if len(name) > 128:
                name = name[:128]

        raw_token = secrets.token_hex(32)
        token_hash = generate_password_hash(raw_token)

        now = datetime.utcnow()

        token = cls(
            token_hash=token_hash,
            user_id=user_id,
            name=name,
            permissions=list(permissions or []) if permissions else [],
            created_at=now
        )

        if days_valid and days_valid > 0:
            token.expires_at = now + timedelta(days=days_valid)

        db.session.add(token)
        db.session.commit()

        return raw_token, token

    @classmethod
    def find_by_raw_token(cls, raw_token):
        """通过原始Token字符串查找匹配的Token记录（比对哈希值）"""
        if not raw_token:
            return None
        now = now_utc()
        candidates = cls.query.filter_by(is_active=True).filter(
            db.or_(cls.expires_at.is_(None), cls.expires_at > now)
        ).all()
        for token in candidates:
            if token.check_raw_token(raw_token):
                return token
        return None

    def __repr__(self):
        return f'<Token {html.escape(self.name) if self.name else "Unnamed"} ({self.user_id})>'
