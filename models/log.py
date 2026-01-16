from datetime import datetime
from .database import db


class Log(db.Model):
    """日志模型"""
    __tablename__ = 'logs'

    id = db.Column(db.Integer, primary_key=True)
    level = db.Column(db.String(16), nullable=False, index=True)  # 'info', 'warning', 'error', 'login'
    message = db.Column(db.Text, nullable=False)
    source = db.Column(db.String(64), nullable=False, index=True)  # 'api', 'web', 'sync', 'system'
    ip_address = db.Column(db.String(45))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    player_name = db.Column(db.String(64), index=True)  # 新增：玩家名称
    player_uuid = db.Column(db.String(36), index=True)  # 新增：玩家UUID
    details = db.Column(db.Text)  # 额外的JSON数据
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'level': self.level,
            'message': self.message,
            'source': self.source,
            'ip_address': self.ip_address,
            'user_id': self.user_id,
            'player_name': self.player_name,
            'player_uuid': self.player_uuid,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'details': self.details
        }

    @classmethod
    def create_login_log(cls, player_name, player_uuid, player_ip, allowed, check_type=None, user_id=None):
        """创建登录日志"""
        log = cls(
            level='login',
            message=f'Player {"allowed" if allowed else "denied"}: {player_name}',
            source='api',
            ip_address=player_ip,
            player_name=player_name,
            player_uuid=player_uuid,
            user_id=user_id,
            details=f'player_name: {player_name}, player_uuid: {player_uuid}, allowed: {allowed}, check_type: {check_type}'
        )
        db.session.add(log)
        db.session.commit()
        return log

    @classmethod
    def get_last_login_info(cls, identifier_type, identifier_value):
        """
        获取指定玩家的最后登录信息
        identifier_type: 'name' 或 'uuid'
        identifier_value: 玩家名称或UUID
        """
        if identifier_type == 'name':
            query = cls.query.filter_by(
                level='login',
                player_name=identifier_value
            )
        elif identifier_type == 'uuid':
            query = cls.query.filter_by(
                level='login',
                player_uuid=identifier_value
            )
        else:
            return None

        # 获取最近一次登录记录
        last_login = query.order_by(cls.created_at.desc()).first()

        if last_login:
            # 解析详情中的信息
            details = {}
            if last_login.details:
                # 解析简单的 key: value 格式
                for line in last_login.details.split(', '):
                    if ':' in line:
                        key, value = line.split(': ', 1) if ': ' in line else line.split(':', 1)
                        details[key.strip()] = value.strip()

            return {
                'last_login_at': last_login.created_at,
                'ip_address': last_login.ip_address,
                'allowed': details.get('allowed', 'false').lower() == 'true',
                'check_type': details.get('check_type', 'unknown')
            }

        return None

    def __repr__(self):
        return f'<Log {self.level}: {self.message[:50]}>'