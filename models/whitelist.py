from datetime import datetime
import uuid

from .database import db
from utils.timezone import now_utc


class WhitelistEntry(db.Model):
    """白名单条目模型"""
    __tablename__ = 'whitelist_entries'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    type = db.Column(db.String(16), nullable=False, index=True)  # 'name', 'uuid', 'ip'
    value = db.Column(db.String(255), nullable=False, index=True)
    description = db.Column(db.String(255))
    created_by = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, default=now_utc)  # 修改这里
    expires_at = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True, index=True)

    # 新增：登录统计字段
    last_login = db.Column(db.DateTime, nullable=True)  # 最近登录时间
    login_count = db.Column(db.Integer, default=0)  # 登录次数
    last_login_ip = db.Column(db.String(45), nullable=True)  # 最近登录IP

    def to_dict(self):
        """转换为字典"""
        from utils.timezone import format_datetime
        return {
            'id': self.id,
            'type': self.type,
            'value': self.value,
            'description': self.description,
            'created_by': self.created_by,
            'created_at': format_datetime(self.created_at) if self.created_at else None,
            'expires_at': format_datetime(self.expires_at) if self.expires_at else None,
            'is_active': self.is_active,
            'last_login': format_datetime(self.last_login) if self.last_login else None,
            'login_count': self.login_count,
            'last_login_ip': self.last_login_ip
        }

    def update_login_info(self, ip_address=None):
        """更新登录信息"""
        self.last_login = now_utc()
        self.login_count += 1
        if ip_address:
            self.last_login_ip = ip_address
        db.session.commit()

    def is_expired(self):
        """检查是否已过期"""
        from utils.timezone import now_utc
        if self.expires_at:
            return now_utc() > self.expires_at
        return False

    def __repr__(self):
        return f'<WhitelistEntry {self.type}:{self.value}>'