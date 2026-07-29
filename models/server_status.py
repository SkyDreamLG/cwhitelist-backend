from datetime import datetime
from .database import db
from utils.timezone import now_utc


class ServerStatus(db.Model):
    """服务器心跳状态"""
    __tablename__ = 'server_status'

    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.String(36), unique=True, nullable=False, index=True)
    is_online = db.Column(db.Boolean, default=True)
    last_heartbeat = db.Column(db.DateTime, default=now_utc)
    last_offline = db.Column(db.DateTime, nullable=True)
    last_recovery = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=now_utc)

    @classmethod
    def heartbeat(cls, server_id):
        """记录心跳，服务器在线"""
        status = cls.query.filter_by(server_id=server_id).first()
        now = now_utc()
        if not status:
            status = cls(server_id=server_id, is_online=True, last_heartbeat=now)
            db.session.add(status)
        else:
            was_offline = not status.is_online
            status.last_heartbeat = now
            if was_offline:
                status.is_online = True
                status.last_recovery = now
        db.session.commit()
        return status

    @classmethod
    def check_offline(cls, timeout_seconds=60):
        """检查超时服务器，返回变为离线的服务器列表"""
        from datetime import timedelta
        now = now_utc()
        cutoff = now - timedelta(seconds=timeout_seconds)
        stale = cls.query.filter(
            cls.is_online == True,
            cls.last_heartbeat < cutoff
        ).all()

        offline_servers = []
        for s in stale:
            s.is_online = False
            s.last_offline = now
            offline_servers.append(s.server_id)
        if offline_servers:
            db.session.commit()
        return offline_servers

    @classmethod
    def get_recovery_time(cls, server_id):
        """获取服务器最近一次恢复时间"""
        status = cls.query.filter_by(server_id=server_id).first()
        if status and status.last_recovery:
            return status.last_recovery
        return None

    @classmethod
    def is_server_online(cls, server_id, timeout_seconds=60):
        """检查服务器是否在线"""
        from datetime import timedelta, timezone
        status = cls.query.filter_by(server_id=server_id).first()
        if not status:
            return False
        if not status.is_online:
            return False
        now = now_utc()
        hb = status.last_heartbeat
        if hb and hb.tzinfo is None:
            hb = hb.replace(tzinfo=timezone.utc)
        return hb >= now - timedelta(seconds=timeout_seconds)

    def to_dict(self):
        return {
            'server_id': self.server_id,
            'is_online': self.is_online,
            'last_heartbeat': self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            'last_offline': self.last_offline.isoformat() if self.last_offline else None,
            'last_recovery': self.last_recovery.isoformat() if self.last_recovery else None,
        }

    def __repr__(self):
        return f'<ServerStatus {self.server_id} online={self.is_online}>'
