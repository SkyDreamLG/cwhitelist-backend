from datetime import datetime, timedelta
import secrets
from .database import db
from utils.timezone import now_utc


class Token(db.Model):
    """API令牌模型"""
    __tablename__ = 'tokens'

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True, default=lambda: secrets.token_hex(32))
    name = db.Column(db.String(128), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=now_utc)  # 修改这里
    expires_at = db.Column(db.DateTime)
    last_used = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)

    # 权限
    can_read = db.Column(db.Boolean, default=True)
    can_write = db.Column(db.Boolean, default=True)
    can_delete = db.Column(db.Boolean, default=False)
    can_manage = db.Column(db.Boolean, default=False)

    # 使用统计
    use_count = db.Column(db.Integer, default=0)
    last_ip = db.Column(db.String(45))

    def is_valid(self):
        """检查令牌是否有效"""
        if not self.is_active:
            return False

        if self.expires_at and now_utc() > self.expires_at:
            return False

        return True

    def update_usage(self, ip_address):
        """更新使用信息"""
        self.last_used = now_utc()
        self.use_count += 1
        self.last_ip = ip_address
        db.session.commit()

    def to_dict(self):
        """转换为字典"""
        from utils.timezone import format_datetime
        return {
            'id': self.id,
            'name': self.name,
            'token': self.token[:8] + '...' if self.token else None,  # 只显示部分
            'user_id': self.user_id,
            'username': self.user.username if self.user else None,
            'created_at': format_datetime(self.created_at) if self.created_at else None,
            'expires_at': format_datetime(self.expires_at) if self.expires_at else None,
            'last_used': format_datetime(self.last_used) if self.last_used else None,
            'is_active': self.is_active,
            'permissions': {
                'can_read': self.can_read,
                'can_write': self.can_write,
                'can_delete': self.can_delete,
                'can_manage': self.can_manage
            },
            'stats': {
                'use_count': self.use_count,
                'last_ip': self.last_ip
            }
        }

    @classmethod
    def create_token(cls, user_id, name, permissions=None, days_valid=365):
        """创建新令牌"""
        token = cls(
            user_id=user_id,
            name=name,
            can_read=True,
            can_write=True,
            can_delete=False,
            can_manage=False
        )

        if permissions:
            for key, value in permissions.items():
                setattr(token, key, value)

        if days_valid:
            token.expires_at = now_utc() + timedelta(days=days_valid)

        db.session.add(token)
        db.session.commit()

        return token