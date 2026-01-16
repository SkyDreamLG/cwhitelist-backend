from .database import db


class Setting(db.Model):
    """系统设置模型"""
    __tablename__ = 'settings'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    value = db.Column(db.Text)
    description = db.Column(db.String(255))
    category = db.Column(db.String(32), default='general', index=True)

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'key': self.key,
            'value': self.value,
            'description': self.description,
            'category': self.category,
        }

    @classmethod
    def get_value(cls, key, default=None):
        """获取设置值"""
        setting = cls.query.filter_by(key=key).first()
        return setting.value if setting else default

    @classmethod
    def set_value(cls, key, value, description=None, category='general'):
        """设置值"""
        setting = cls.query.filter_by(key=key).first()
        if setting:
            setting.value = value
            if description:
                setting.description = description
            setting.category = category
        else:
            setting = cls(
                key=key,
                value=value,
                description=description or key,
                category=category
            )
            db.session.add(setting)

        db.session.commit()
        return setting

    def __repr__(self):
        return f'<Setting {self.key}={self.value}>'