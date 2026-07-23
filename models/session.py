from datetime import datetime
from .database import db
from utils.timezone import now_utc


class LoginSession(db.Model):
    """登入登出会话记录"""
    __tablename__ = 'login_sessions'

    id = db.Column(db.Integer, primary_key=True)
    player_name = db.Column(db.String(64), nullable=False, index=True)
    player_uuid = db.Column(db.String(36), index=True)
    server_id = db.Column(db.String(36), nullable=False, index=True)

    login_time = db.Column(db.DateTime, nullable=False, default=now_utc, index=True)
    logout_time = db.Column(db.DateTime, nullable=True)
    duration = db.Column(db.Integer, nullable=True)  # 在线时长（秒）

    login_ip = db.Column(db.String(45))
    logout_ip = db.Column(db.String(45))

    created_at = db.Column(db.DateTime, default=now_utc)

    def close_session(self, logout_time=None, logout_ip=None):
        """关闭会话（登出时调用）"""
        self.logout_time = logout_time or now_utc()
        if logout_ip:
            self.logout_ip = logout_ip
        if self.login_time:
            delta = self.logout_time - self.login_time
            # 确保两个时间都有时区信息或都没有
            if self.logout_time.tzinfo and self.login_time.tzinfo:
                self.duration = int(delta.total_seconds())
            elif not self.logout_time.tzinfo and not self.login_time.tzinfo:
                self.duration = int(delta.total_seconds())
            else:
                self.duration = int(abs(delta.total_seconds()))
        db.session.commit()

    @classmethod
    def get_player_sessions(cls, player_name=None, player_uuid=None, server_id=None, limit=100):
        """获取玩家会话记录"""
        query = cls.query
        if player_name:
            query = query.filter_by(player_name=player_name)
        if player_uuid:
            query = query.filter_by(player_uuid=player_uuid)
        if server_id:
            query = query.filter_by(server_id=server_id)
        return query.order_by(cls.login_time.desc()).limit(limit).all()

    @classmethod
    def get_player_stats(cls, player_name=None, player_uuid=None):
        """获取玩家统计数据"""
        query = cls.query
        if player_name:
            query = query.filter_by(player_name=player_name)
        elif player_uuid:
            query = query.filter_by(player_uuid=player_uuid)
        else:
            return None

        sessions = query.filter(cls.duration.isnot(None)).all()
        total_sessions = len(sessions)
        total_duration = sum(s.duration or 0 for s in sessions)
        avg_duration = total_duration / total_sessions if total_sessions > 0 else 0

        # IP 排名
        ip_counts = {}
        for s in sessions:
            ip = s.login_ip or 'unknown'
            ip_counts[ip] = ip_counts.get(ip, 0) + 1
        ip_ranking = sorted(ip_counts.items(), key=lambda x: x[1], reverse=True)

        # 在线时间按小时分布（转换为本地时区）
        from utils.timezone import utc_to_local
        hourly_distribution = {}
        for s in sessions:
            if s.login_time:
                hour = utc_to_local(s.login_time).hour
                hourly_distribution[str(hour)] = hourly_distribution.get(str(hour), 0) + 1

        return {
            'total_sessions': total_sessions,
            'total_duration': total_duration,
            'avg_duration': avg_duration,
            'ip_ranking': ip_ranking[:10],
            'hourly_distribution': hourly_distribution,
            'recent_sessions': sessions[:50],
        }

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'player_name': self.player_name,
            'player_uuid': self.player_uuid,
            'server_id': self.server_id,
            'login_time': self.login_time.isoformat() if self.login_time else None,
            'logout_time': self.logout_time.isoformat() if self.logout_time else None,
            'duration': self.duration,
            'login_ip': self.login_ip,
            'logout_ip': self.logout_ip,
        }

    def __repr__(self):
        return f'<LoginSession {self.player_name} {self.login_time}>'
