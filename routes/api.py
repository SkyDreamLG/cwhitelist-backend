from flask import Blueprint, request, jsonify
from datetime import datetime
import uuid

from models.database import db
from models.whitelist import WhitelistEntry
from models.log import Log

api_bp = Blueprint('api', __name__)


@api_bp.route('/health', methods=['GET'])
def health():
    """健康检查接口"""
    # 记录API访问日志
    log = Log(
        level='info',
        message='API健康检查',
        source='api',
        ip_address=request.remote_addr,
        details=f'endpoint: /health, method: GET'
    )
    db.session.add(log)
    db.session.commit()

    return jsonify({
        'success': True,
        'status': 'ok',
        'timestamp': datetime.utcnow().isoformat(),
        'service': 'CWhitelist API',
        'version': '1.0.0'
    })


@api_bp.route('/whitelist/sync', methods=['GET'])
def sync_whitelist():
    """同步白名单数据"""
    try:
        # 获取查询参数
        server_id = request.args.get('server_id')
        only_active = request.args.get('only_active', 'true').lower() == 'true'

        # 构建查询
        query = WhitelistEntry.query

        if server_id:
            # 这里可以添加服务器特定的查询逻辑
            pass

        if only_active:
            query = query.filter_by(is_active=True)

            # 排除过期的条目
            from sqlalchemy import or_
            query = query.filter(or_(
                WhitelistEntry.expires_at.is_(None),
                WhitelistEntry.expires_at > datetime.utcnow()
            ))

        entries = query.order_by(WhitelistEntry.type, WhitelistEntry.value).all()

        # 记录API操作日志
        log = Log(
            level='info',
            message='API同步白名单数据',
            source='api',
            ip_address=request.remote_addr,
            details=f'endpoint: /whitelist/sync, entries_count: {len(entries)}, server_id: {server_id}'
        )
        db.session.add(log)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Sync successful',
            'entries': [entry.to_dict() for entry in entries],
            'total_count': len(entries),
            'synced_at': datetime.utcnow().isoformat()
        })

    except Exception as e:
        # 记录API错误日志
        log = Log(
            level='error',
            message='API同步白名单数据失败',
            source='api',
            ip_address=request.remote_addr,
            details=f'endpoint: /whitelist/sync, error: {str(e)}'
        )
        db.session.add(log)
        db.session.commit()

        return jsonify({
            'success': False,
            'message': 'Internal server error',
            'error': str(e)
        }), 500


@api_bp.route('/whitelist/entries', methods=['POST'])
def add_whitelist_entry():
    """添加白名单条目"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': 'No data provided'
            }), 400

        # 验证必需字段
        required_fields = ['type', 'value']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'message': f'Missing required field: {field}'
                }), 400

        entry_type = data['type'].lower()
        value = data['value'].strip()

        # 验证类型
        if entry_type not in ['name', 'uuid', 'ip']:
            return jsonify({
                'success': False,
                'message': 'Invalid type. Must be: name, uuid, or ip'
            }), 400

        # 检查是否已存在
        existing = WhitelistEntry.query.filter_by(
            type=entry_type,
            value=value
        ).first()

        if existing:
            return jsonify({
                'success': False,
                'message': 'Entry already exists'
            }), 409

        # 创建条目
        entry = WhitelistEntry(
            type=entry_type,
            value=value,
            description=data.get('description', ''),
            created_by=data.get('created_by', 'api'),
            is_active=data.get('is_active', True)
        )

        # 设置过期时间
        if 'expires_at' in data:
            try:
                entry.expires_at = datetime.fromisoformat(data['expires_at'].replace('Z', '+00:00'))
            except ValueError:
                return jsonify({
                    'success': False,
                    'message': 'Invalid expires_at format. Use ISO 8601'
                }), 400

        db.session.add(entry)
        db.session.commit()

        # 记录API操作日志
        log = Log(
            level='info',
            message='API添加白名单条目',
            source='api',
            ip_address=request.remote_addr,
            details=f'endpoint: /whitelist/entries, type: {entry_type}, value: {value}, entry_id: {entry.id}'
        )
        db.session.add(log)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Entry added successfully',
            'entry': entry.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()

        # 记录API错误日志
        log = Log(
            level='error',
            message='API添加白名单条目失败',
            source='api',
            ip_address=request.remote_addr,
            details=f'endpoint: /whitelist/entries, error: {str(e)}'
        )
        db.session.add(log)
        db.session.commit()

        return jsonify({
            'success': False,
            'message': 'Internal server error',
            'error': str(e)
        }), 500


@api_bp.route('/whitelist/entries/<entry_type>/<value>', methods=['DELETE'])
def delete_whitelist_entry(entry_type, value):
    """删除白名单条目"""
    try:
        # 查找条目
        entry = WhitelistEntry.query.filter_by(
            type=entry_type.lower(),
            value=value
        ).first()

        if not entry:
            # 记录未找到条目的日志
            log = Log(
                level='warning',
                message=f'API删除白名单条目失败：条目不存在',
                source='api',
                ip_address=request.remote_addr,
                details=f'endpoint: /whitelist/entries/{entry_type}/{value}, type: {entry_type}, value: {value}'
            )
            db.session.add(log)
            db.session.commit()

            return jsonify({
                'success': False,
                'message': 'Entry not found'
            }), 404

        # 记录删除操作日志（在删除前记录）
        log = Log(
            level='warning',
            message=f'API删除白名单条目: {entry.type}={entry.value}',
            source='api',
            ip_address=request.remote_addr,
            details=f'endpoint: /whitelist/entries/{entry_type}/{value}, entry_id: {entry.id}, description: {entry.description}'
        )
        db.session.add(log)

        # 删除条目
        db.session.delete(entry)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Entry deleted successfully'
        })

    except Exception as e:
        db.session.rollback()

        # 记录API错误日志
        log = Log(
            level='error',
            message='API删除白名单条目失败',
            source='api',
            ip_address=request.remote_addr,
            details=f'endpoint: /whitelist/entries/{entry_type}/{value}, error: {str(e)}'
        )
        db.session.add(log)
        db.session.commit()

        return jsonify({
            'success': False,
            'message': 'Internal server error',
            'error': str(e)
        }), 500


@api_bp.route('/login/log', methods=['POST'])
def log_login():
    """记录登录事件"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': 'No data provided'
            }), 400

        # 验证必需字段
        required_fields = ['player_name', 'player_uuid', 'player_ip', 'allowed']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'message': f'Missing required field: {field}'
                }), 400

        player_name = data['player_name']
        player_uuid = data['player_uuid']
        player_ip = data['player_ip']
        allowed = data['allowed']
        check_type = data.get('check_type')

        # 记录Minecraft玩家登录事件
        log = Log.create_login_log(
            player_name=player_name,
            player_uuid=player_uuid,
            player_ip=player_ip,
            allowed=allowed,
            check_type=check_type,
            user_id=None
        )

        return jsonify({
            'success': True,
            'message': 'Login logged successfully',
            'log_id': log.id
        })

    except Exception as e:
        # 记录API错误日志
        log = Log(
            level='error',
            message='API记录登录事件失败',
            source='api',
            ip_address=request.remote_addr,
            details=f'endpoint: /login/log, error: {str(e)}'
        )
        db.session.add(log)
        db.session.commit()

        return jsonify({
            'success': False,
            'message': 'Internal server error',
            'error': str(e)
        }), 500