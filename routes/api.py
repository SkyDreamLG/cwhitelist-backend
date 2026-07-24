# routes/api.py
from flask import Blueprint, current_app, request, jsonify
from datetime import datetime
import uuid
import secrets

from models.database import db
from models.token import Token
from models.whitelist import WhitelistEntry
from models.log import Log
from models.session import LoginSession
from models.server_status import ServerStatus
from models.setting import Setting
from utils.auth import require_api_auth
from utils.permissions import Permission
from utils.helpers import log_msg
from utils.async_log import write_log

api_bp = Blueprint('api', __name__)


@api_bp.route('/health', methods=['GET'])
def health():
    """健康检查接口 - 不需要Token验证，server_id必填"""
    server_id = request.args.get('server_id', '').strip()
    if not server_id:
        return jsonify({
            'success': False,
            'message': 'server_id is required'
        }), 400

    ServerStatus.heartbeat(server_id)

    offline_servers = ServerStatus.check_offline(timeout_seconds=60)
    for sid in offline_servers:
        now = datetime.utcnow()
        open_sessions = LoginSession.query.filter_by(
            server_id=sid, logout_time=None
        ).all()
        for s in open_sessions:
            s.close_session(logout_time=now)

    # 根据设置决定是否保存健康检查日志
    save_health_logs = Setting.get_value('save_health_check_logs', 'true') != 'false'
    if save_health_logs:
        log = Log(
            level='info',
            message=log_msg(
                f'API健康检查: {server_id}',
                f'API Health Check: {server_id}'
            ),
            source='api',
            ip_address=request.remote_addr,
            server_id=server_id,
            details=f'endpoint: /health, method: GET, server_id: {server_id}'
        )
        write_log(log)

    return jsonify({
        'success': True,
        'status': 'ok',
        'server_id': server_id,
        'timestamp': datetime.utcnow().isoformat(),
        'service': 'CWhitelist API',
        'version': current_app.config.get('APP_VERSION', '2.3.0')
    })


@api_bp.route('/whitelist/sync', methods=['GET'])
@require_api_auth(Permission.WHITELIST_READ)
def sync_whitelist():
    """同步白名单数据"""
    try:
        server_id = request.args.get('server_id', '').strip()
        only_active = request.args.get('only_active', 'true').lower() == 'true'

        if not server_id:
            return jsonify({
                'success': False,
                'message': 'server_id is required'
            }), 400

        token = getattr(request, 'token', None)

        log_details = {
            'endpoint': '/whitelist/sync',
            'entries_count': 'unknown',
            'server_id': server_id,
            'token_id': token.id if token else None,
            'token_name': token.name if token else None
        }

        query = WhitelistEntry.query.filter_by(server_id=server_id)

        if only_active:
            query = query.filter_by(is_active=True)
            from sqlalchemy import or_
            query = query.filter(or_(
                WhitelistEntry.expires_at.is_(None),
                WhitelistEntry.expires_at > datetime.utcnow()
            ))

        entries = query.order_by(WhitelistEntry.type, WhitelistEntry.value).all()
        log_details['entries_count'] = len(entries)

        log = Log(
            level='info',
            message=log_msg(
                'API同步白名单数据',
                'API Sync Whitelist Data'
            ),
            source='api',
            ip_address=request.remote_addr,
            user_id=token.user_id if token else None,
            details=str(log_details)
        )
        write_log(log)

        return jsonify({
            'success': True,
            'message': 'Sync successful',
            'entries': [entry.to_dict() for entry in entries],
            'total_count': len(entries),
            'synced_at': datetime.utcnow().isoformat(),
            'token_info': {
                'token_id': token.id if token else None,
                'token_name': token.name if token else None,
                'permissions': token.permissions if token else None
            } if token else None
        })

    except Exception as e:
        log = Log(
            level='error',
            message=log_msg(
                'API同步白名单数据失败',
                'API Sync Whitelist Data Failed'
            ),
            source='api',
            ip_address=request.remote_addr,
            details=f'endpoint: /whitelist/sync, error: {str(e)}'
        )
        write_log(log)

        return jsonify({
            'success': False,
            'message': 'Internal server error',
            'error': str(e)
        }), 500


@api_bp.route('/whitelist/entries', methods=['POST'])
@require_api_auth(Permission.WHITELIST_WRITE)
def add_whitelist_entry():
    """添加白名单条目"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': 'No data provided'
            }), 400

        token = getattr(request, 'token', None)

        required_fields = ['type', 'value', 'server_id']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'message': f'Missing required field: {field}'
                }), 400

        entry_type = data['type'].lower()
        value = data['value'].strip()
        server_id = data['server_id'].strip()

        if not server_id:
            return jsonify({
                'success': False,
                'message': 'server_id cannot be empty'
            }), 400

        if entry_type not in ['name', 'uuid', 'ip']:
            return jsonify({
                'success': False,
                'message': 'Invalid type. Must be: name, uuid, or ip'
            }), 400

        existing = WhitelistEntry.query.filter_by(
            type=entry_type,
            value=value,
            server_id=server_id
        ).first()

        if existing:
            return jsonify({
                'success': False,
                'message': 'Entry already exists'
            }), 409

        entry = WhitelistEntry(
            type=entry_type,
            value=value,
            server_id=server_id,
            description=data.get('description', ''),
            created_by=data.get('created_by', f'api_token_{token.name if token else "unknown"}'),
            is_active=data.get('is_active', True)
        )

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

        log = Log(
            level='info',
            message=log_msg(
                'API添加白名单条目',
                'API Add Whitelist Entry'
            ),
            source='api',
            ip_address=request.remote_addr,
            user_id=token.user_id if token else None,
            details=f'endpoint: /whitelist/entries, type: {entry_type}, value: {value}, entry_id: {entry.id}, token: {token.name if token else None}'
        )
        write_log(log)

        return jsonify({
            'success': True,
            'message': 'Entry added successfully',
            'entry': entry.to_dict(),
            'added_by': f'api_token_{token.name if token else "unknown"}'
        }), 201

    except Exception as e:
        db.session.rollback()

        log = Log(
            level='error',
            message=log_msg(
                'API添加白名单条目失败',
                'API Add Whitelist Entry Failed'
            ),
            source='api',
            ip_address=request.remote_addr,
            details=f'endpoint: /whitelist/entries, error: {str(e)}'
        )
        write_log(log)

        return jsonify({
            'success': False,
            'message': 'Internal server error',
            'error': str(e)
        }), 500


@api_bp.route('/whitelist/entries/<entry_id>', methods=['PUT'])
@require_api_auth(Permission.WHITELIST_WRITE)
def update_whitelist_entry(entry_id):
    """更新白名单条目"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': 'No data provided'
            }), 400

        token = getattr(request, 'token', None)

        entry = WhitelistEntry.query.get(entry_id)
        if not entry:
            return jsonify({
                'success': False,
                'message': 'Entry not found'
            }), 404

        old_data = f'type={entry.type}, value={entry.value}, server_id={entry.server_id}, description={entry.description}'

        if 'type' in data:
            entry_type = data['type'].lower()
            if entry_type not in ['name', 'uuid', 'ip']:
                return jsonify({
                    'success': False,
                    'message': 'Invalid type. Must be: name, uuid, or ip'
                }), 400
            entry.type = entry_type

        if 'value' in data:
            entry.value = data['value'].strip()

        if 'server_id' in data:
            entry.server_id = data['server_id'].strip()

        if 'description' in data:
            entry.description = data['description']

        if 'is_active' in data:
            entry.is_active = bool(data['is_active'])

        if 'expires_at' in data:
            if data['expires_at'] is None:
                entry.expires_at = None
            else:
                try:
                    entry.expires_at = datetime.fromisoformat(data['expires_at'].replace('Z', '+00:00'))
                except ValueError:
                    return jsonify({
                        'success': False,
                        'message': 'Invalid expires_at format. Use ISO 8601'
                    }), 400

        db.session.commit()

        log = Log(
            level='info',
            message=log_msg(
                f'API更新白名单条目: {entry.type}={entry.value}',
                f'API Update Whitelist Entry: {entry.type}={entry.value}'
            ),
            source='api',
            ip_address=request.remote_addr,
            user_id=token.user_id if token else None,
            details=f'endpoint: /whitelist/entries/{entry_id}, entry_id: {entry.id}, old: ({old_data}), new: type={entry.type}, value={entry.value}, token: {token.name if token else None}'
        )
        write_log(log)

        return jsonify({
            'success': True,
            'message': 'Entry updated successfully',
            'entry': entry.to_dict()
        })

    except Exception as e:
        db.session.rollback()

        log = Log(
            level='error',
            message=log_msg(
                'API更新白名单条目失败',
                'API Update Whitelist Entry Failed'
            ),
            source='api',
            ip_address=request.remote_addr,
            details=f'endpoint: /whitelist/entries/{entry_id}, error: {str(e)}'
        )
        write_log(log)

        return jsonify({
            'success': False,
            'message': 'Internal server error',
            'error': str(e)
        }), 500


@api_bp.route('/whitelist/entries/<entry_type>/<value>', methods=['DELETE'])
@require_api_auth(Permission.WHITELIST_DELETE)
def delete_whitelist_entry(entry_type, value):
    """删除白名单条目"""
    try:
        token = getattr(request, 'token', None)

        server_id = request.args.get('server_id', '').strip()
        if not server_id:
            return jsonify({
                'success': False,
                'message': 'server_id is required'
            }), 400

        entry = WhitelistEntry.query.filter_by(
            type=entry_type.lower(),
            value=value,
            server_id=server_id
        ).first()

        if not entry:
            log = Log(
                level='warning',
                message=log_msg(
                    f'API删除白名单条目失败：条目不存在',
                    f'API Delete Whitelist Entry Failed: Entry Not Found'
                ),
                source='api',
                ip_address=request.remote_addr,
                user_id=token.user_id if token else None,
                details=f'endpoint: /whitelist/entries/{entry_type}/{value}, type: {entry_type}, value: {value}, token: {token.name if token else None}'
            )
            write_log(log)

            return jsonify({
                'success': False,
                'message': 'Entry not found'
            }), 404

        db.session.delete(entry)
        db.session.commit()

        log = Log(
            level='warning',
            message=log_msg(
                f'API删除白名单条目: {entry.type}={entry.value}',
                f'API Delete Whitelist Entry: {entry.type}={entry.value}'
            ),
            source='api',
            ip_address=request.remote_addr,
            user_id=token.user_id if token else None,
            details=f'endpoint: /whitelist/entries/{entry_type}/{value}, entry_id: {entry.id}, description: {entry.description}, token: {token.name if token else None}'
        )
        write_log(log)

        return jsonify({
            'success': True,
            'message': 'Entry deleted successfully',
            'deleted_by': f'api_token_{token.name if token else "unknown"}'
        })

    except Exception as e:
        db.session.rollback()

        log = Log(
            level='error',
            message=log_msg(
                'API删除白名单条目失败',
                'API Delete Whitelist Entry Failed'
            ),
            source='api',
            ip_address=request.remote_addr,
            details=f'endpoint: /whitelist/entries/{entry_type}/{value}, error: {str(e)}'
        )
        write_log(log)

        return jsonify({
            'success': False,
            'message': 'Internal server error',
            'error': str(e)
        }), 500


@api_bp.route('/login/log', methods=['POST'])
@require_api_auth(Permission.LOGIN_LOG)
def log_login():
    """记录登录事件"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': 'No data provided'
            }), 400

        token = getattr(request, 'token', None)

        required_fields = ['player_name', 'player_uuid', 'player_ip', 'allowed', 'server_id']
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
        server_id = data['server_id']

        log = Log.create_login_log(
            player_name=player_name,
            player_uuid=player_uuid,
            player_ip=player_ip,
            allowed=allowed,
            check_type=check_type,
            server_id=server_id,
            user_id=token.user_id if token else None
        )

        session_id = None
        if allowed:
            open_session = LoginSession.query.filter_by(
                player_name=player_name,
                server_id=server_id,
                logout_time=None
            ).first()
            if open_session:
                open_session.login_time = datetime.utcnow()
                open_session.login_ip = player_ip
                if player_uuid:
                    open_session.player_uuid = player_uuid
                db.session.commit()
                session_id = open_session.id
            else:
                recovery_time = ServerStatus.get_recovery_time(server_id)
                login_time = recovery_time or datetime.utcnow()
                new_session = LoginSession(
                    player_name=player_name,
                    player_uuid=player_uuid,
                    server_id=server_id,
                    login_time=login_time,
                    login_ip=player_ip,
                )
                db.session.add(new_session)
                db.session.commit()
                session_id = new_session.id

        return jsonify({
            'success': True,
            'message': 'Login logged successfully',
            'log_id': log.id,
            'session_id': session_id,
            'logged_by': f'api_token_{token.name if token else "unknown"}'
        })

    except Exception as e:
        log = Log(
            level='error',
            message=log_msg(
                'API记录登录事件失败',
                'API Log Login Event Failed'
            ),
            source='api',
            ip_address=request.remote_addr,
            details=f'endpoint: /login/log, error: {str(e)}'
        )
        write_log(log)

        return jsonify({
            'success': False,
            'message': 'Internal server error',
            'error': str(e)
        }), 500


@api_bp.route('/login/logout', methods=['POST'])
@require_api_auth(Permission.LOGIN_LOG)
def log_logout():
    """记录登出事件"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': 'No data provided'
            }), 400

        token = getattr(request, 'token', None)

        required_fields = ['player_name', 'player_uuid', 'player_ip', 'server_id']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'message': f'Missing required field: {field}'
                }), 400

        player_name = data['player_name']
        player_uuid = data['player_uuid']
        player_ip = data['player_ip']
        server_id = data['server_id']

        log = Log(
            level='login',
            message=log_msg(
                f'玩家登出: {player_name}',
                f'Player logout: {player_name}'
            ),
            source='api',
            ip_address=player_ip,
            player_name=player_name,
            player_uuid=player_uuid,
            server_id=server_id,
            user_id=token.user_id if token else None,
            details=f'player_name: {player_name}, player_uuid: {player_uuid}, action: logout, server_id: {server_id}'
        )
        db.session.add(log)

        open_session = LoginSession.query.filter_by(
            player_name=player_name,
            server_id=server_id,
            logout_time=None
        ).order_by(LoginSession.login_time.desc()).first()

        if open_session:
            open_session.close_session(logout_time=datetime.utcnow(), logout_ip=player_ip)
            db.session.commit()
            return jsonify({
                'success': True,
                'message': 'Logout logged successfully',
                'log_id': log.id,
                'session_id': open_session.id,
                'duration': open_session.duration,
            })
        else:
            recovery_time = ServerStatus.get_recovery_time(server_id)
            login_time = recovery_time or datetime.utcnow()
            logout_time = datetime.utcnow()
            delta = logout_time - login_time
            if hasattr(delta, 'total_seconds'):
                dur = int(delta.total_seconds()) if delta.total_seconds() > 0 else 0
            else:
                dur = 0

            new_session = LoginSession(
                player_name=player_name,
                player_uuid=player_uuid,
                server_id=server_id,
                login_time=login_time,
                logout_time=logout_time,
                duration=dur,
                login_ip=player_ip,
                logout_ip=player_ip,
            )
            db.session.add(new_session)
            db.session.commit()
            return jsonify({
                'success': True,
                'message': 'Logout logged (auto-created session)',
                'log_id': log.id,
                'session_id': new_session.id,
                'duration': new_session.duration,
            })

    except Exception as e:
        db.session.rollback()
        log = Log(
            level='error',
            message=log_msg(
                'API记录登出事件失败',
                'API Log Logout Event Failed'
            ),
            source='api',
            ip_address=request.remote_addr,
            details=f'endpoint: /login/logout, error: {str(e)}'
        )
        write_log(log)

        return jsonify({
            'success': False,
            'message': 'Internal server error',
            'error': str(e)
        }), 500


@api_bp.route('/tokens/verify', methods=['GET'])
@require_api_auth
def verify_token():
    """验证Token有效性"""
    try:
        token = getattr(request, 'token', None)
        if not token:
            return jsonify({
                'success': False,
                'message': 'Token not found'
            }), 404

        response_data = {
            'success': True,
            'message': 'Token is valid',
            'token': {
                'id': token.id,
                'name': token.name,
                'created_at': token.created_at.isoformat() if token.created_at else None,
                'expires_at': token.expires_at.isoformat() if token.expires_at else None,
                'is_active': token.is_active,
                'permissions': list(token.permissions or [])
            },
            'valid_until': token.expires_at.isoformat() if token.expires_at else 'never'
        }

        print(f"[API] Token verification successful for: {token.name}")

        return jsonify(response_data)

    except Exception as e:
        print(f"[API] Token verification error: {str(e)}")
        import traceback
        print(f"[API] Stack trace: {traceback.format_exc()}")

        return jsonify({
            'success': False,
            'message': f'Token verification failed: {str(e)}'
        }), 500


@api_bp.route('/tokens/create', methods=['POST'])
def create_token():
    """创建新的API Token（需要管理员Web登录）"""
    from flask_login import current_user
    from models.user import User

    try:
        if not current_user.is_authenticated or not current_user.is_admin():
            return jsonify({
                'success': False,
                'message': 'Admin privileges required'
            }), 403

        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': 'No data provided'
            }), 400

        name = data.get('name', '').strip()
        if not name:
            return jsonify({
                'success': False,
                'message': 'Token name is required'
            }), 400

        # 细粒度权限：从请求体获取权限字符串列表
        perms = data.get('permissions', [])
        if not isinstance(perms, list):
            perms = []

        days_valid = data.get('days_valid', 365)

        from werkzeug.security import generate_password_hash
        token_str = secrets.token_hex(32)
        token_hash = generate_password_hash(token_str)

        now = datetime.utcnow()

        token = Token(
            token_hash=token_hash,
            name=name,
            user_id=current_user.id,
            permissions=perms,
            created_at=now
        )

        if days_valid:
            from datetime import timedelta
            token.expires_at = now + timedelta(days=days_valid)

        db.session.add(token)
        db.session.commit()

        log = Log(
            level='info',
            message=log_msg(
                f'创建API Token: {name}',
                f'Create API Token: {name}'
            ),
            source='api',
            ip_address=request.remote_addr,
            user_id=current_user.id,
            details=f'token_id: {token.id}, permissions: {perms}'
        )
        write_log(log)

        return jsonify({
            'success': True,
            'message': 'Token created successfully',
            'token': token_str,
            'token_info': {
                'id': token.id,
                'name': token.name,
                'created_at': token.created_at.isoformat() if token.created_at else None,
                'expires_at': token.expires_at.isoformat() if token.expires_at else None,
                'permissions': list(token.permissions or [])
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Failed to create token: {str(e)}'
        }), 500
