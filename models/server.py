from datetime import datetime
import uuid
from .database import db


class Server(db.Model):
    """服务器模型"""
    __tablename__ = 'servers'

    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.String(255))
    ip_address = db.Column(db.String(45))  # 支持IPv6
    port = db.Column(db.Integer, default=25565)
    game_version = db.Column(db.String(32))
    mod_version = db.Column(db.String(32))
    is_active = db.Column(db.Boolean, default=True)
    last_sync = db.Column(db.DateTime)
    sync_status = db.Column(db.String(32), default='unknown')  # 'synced', 'failed', 'pending'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 统计信息
    total_logins = db.Column(db.Integer, default=0)
    allowed_logins = db.Column(db.Integer, default=0)
    denied_logins = db.Column(db.Integer, default=0)

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'server_id': self.server_id,
            'name': self.name,
            'description': self.description,
            'ip_address': self.ip_address,
            'port': self.port,
            'game_version': self.game_version,
            'mod_version': self.mod_version,
            'is_active': self.is_active,
            'last_sync': self.last_sync.isoformat() if self.last_sync else None,
            'sync_status': self.sync_status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'stats': {
                'total_logins': self.total_logins,
                'allowed_logins': self.allowed_logins,
                'denied_logins': self.denied_logins
            }
        }

    def update_sync_status(self, status, success=True):
        """更新同步状态"""
        self.last_sync = datetime.utcnow()
        self.sync_status = 'synced' if success else 'failed'
        db.session.commit()

    def increment_stats(self, allowed):
        """增加登录统计"""
        self.total_logins += 1
        if allowed:
            self.allowed_logins += 1
        else:
            self.denied_logins += 1
        db.session.commit()

    def __repr__(self):
        return f'<Server {self.name} ({self.server_id})>'