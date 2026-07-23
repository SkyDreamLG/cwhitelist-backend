# routes/api.py
from flask import Blueprint, request, jsonify
from datetime import datetime
import uuid

from models.database import db
from models.token import Token
from models.whitelist import WhitelistEntry
from models.log import Log
from models.session import LoginSession
from models.server_status import ServerStatus
from utils.auth import require_api_auth  # 导入装饰器

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

    # 记录心跳
    ServerStatus.heartbeat(server_id)

    # 检查是否有超时服务器，自动关闭其会话
    offline_servers = ServerStatus.check_offline(timeout_seconds=60)
    for sid in offline_servers:
        now = datetime.utcnow()
        open_sessions = LoginSession.query.filter_by(
            server_id=sid, logout_time=None
        ).all()
        for s in open_sessions:
            s.close_session(logout_time=now)

    # 记录API访问日志
    log = Log(
        level='info',
        message=f'API健康检查: {server_id}',
        source='api',
        ip_address=request.remote_addr,
        server_id=server_id,
        details=f'endpoint: /health, method: GET, server_id: {server_id}'
    )
    db.session.add(log)
    db.session.commit()

    return jsonify({
        'success': True,
        'status': 'ok',
        'server_id': server_id,
        'timestamp': datetime.utcnow().isoformat(),
        'service': 'CWhitelist API',
        'version': '2.0.0'
    })


@api_bp.route('/whitelist/sync', methods=['GET'])
@require_api_auth  # 添加Token验证
def sync_whitelist():
    """同步白名单数据"""
    try:
        # 获取查询参数
        server_id = request.args.get('server_id', '').strip()
        only_active = request.args.get('only_active', 'true').lower() == 'true'

        # server_id 为必填参数
        if not server_id:
            return jsonify({
                'success': False,
                'message': 'server_id is required'
            }), 400

        # 获取Token信息（通过装饰器附加）
        token = getattr(request, 'token', None)

        # 记录带Token信息的日志
        log_details = {
            'endpoint': '/whitelist/sync',
            'entries_count': 'unknown',
            'server_id': server_id,
            'token_id': token.id if token else None,
            'token_name': token.name if token else None
        }

        # 构建查询 - 按server_id过滤
        query = WhitelistEntry.query.filter_by(server_id=server_id)

        if only_active:
            query = query.filter_by(is_active=True)

            # 排除过期的条目
            from sqlalchemy import or_
            query = query.filter(or_(
                WhitelistEntry.expires_at.is_(None),
                WhitelistEntry.expires_at > datetime.utcnow()
            ))

        entries = query.order_by(WhitelistEntry.type, WhitelistEntry.value).all()

        # 更新日志详情
        log_details['entries_count'] = len(entries)

        # 记录API操作日志
        log = Log(
            level='info',
            message='API同步白名单数据',
            source='api',
            ip_address=request.remote_addr,
            user_id=token.user_id if token else None,
            details=str(log_details)
        )
        db.session.add(log)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Sync successful',
            'entries': [entry.to_dict() for entry in entries],
            'total_count': len(entries),
            'synced_at': datetime.utcnow().isoformat(),
            'token_info': {
                'token_id': token.id if token else None,
                'token_name': token.name if token else None,
                'permissions': {
                    'can_read': token.can_read if token else None,
                    'can_write': token.can_write if token else None
                }
            } if token else None
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
@require_api_auth  # 添加Token验证
def add_whitelist_entry():
    """添加白名单条目"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': 'No data provided'
            }), 400

        # 获取Token信息
        token = getattr(request, 'token', None)

        # 检查写入权限
        if token and not token.can_write:
            return jsonify({
                'success': False,
                'message': 'Token does not have write permission'
            }), 403

        # 验证必需字段
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

        # 验证类型
        if entry_type not in ['name', 'uuid', 'ip']:
            return jsonify({
                'success': False,
                'message': 'Invalid type. Must be: name, uuid, or ip'
            }), 400

        # 检查是否已存在（相同server_id下）
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

        # 创建条目
        entry = WhitelistEntry(
            type=entry_type,
            value=value,
            server_id=server_id,
            description=data.get('description', ''),
            created_by=data.get('created_by', f'api_token_{token.name if token else "unknown"}'),
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
            user_id=token.user_id if token else None,
            details=f'endpoint: /whitelist/entries, type: {entry_type}, value: {value}, entry_id: {entry.id}, token: {token.name if token else None}'
        )
        db.session.add(log)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Entry added successfully',
            'entry': entry.to_dict(),
            'added_by': f'api_token_{token.name if token else "unknown"}'
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


@api_bp.route('/whitelist/entries/<entry_id>', methods=['PUT'])
@require_api_auth
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

        if token and not token.can_write:
            return jsonify({
                'success': False,
                'message': 'Token does not have write permission'
            }), 403

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
            message=f'API更新白名单条目: {entry.type}={entry.value}',
            source='api',
            ip_address=request.remote_addr,
            user_id=token.user_id if token else None,
            details=f'endpoint: /whitelist/entries/{entry_id}, entry_id: {entry.id}, old: ({old_data}), new: type={entry.type}, value={entry.value}, token: {token.name if token else None}'
        )
        db.session.add(log)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Entry updated successfully',
            'entry': entry.to_dict()
        })

    except Exception as e:
        db.session.rollback()

        log = Log(
            level='error',
            message='API更新白名单条目失败',
            source='api',
            ip_address=request.remote_addr,
            details=f'endpoint: /whitelist/entries/{entry_id}, error: {str(e)}'
        )
        db.session.add(log)
        db.session.commit()

        return jsonify({
            'success': False,
            'message': 'Internal server error',
            'error': str(e)
        }), 500


@api_bp.route('/whitelist/entries/<entry_type>/<value>', methods=['DELETE'])
@require_api_auth  # 添加Token验证
def delete_whitelist_entry(entry_type, value):
    """删除白名单条目"""
    try:
        # 获取Token信息
        token = getattr(request, 'token', None)

        # 检查删除权限
        if token and not token.can_delete:
            return jsonify({
                'success': False,
                'message': 'Token does not have delete permission'
            }), 403

        # server_id 为必填参数
        server_id = request.args.get('server_id', '').strip()
        if not server_id:
            return jsonify({
                'success': False,
                'message': 'server_id is required'
            }), 400

        # 查找条目（按server_id范围查找）
        entry = WhitelistEntry.query.filter_by(
            type=entry_type.lower(),
            value=value,
            server_id=server_id
        ).first()

        if not entry:
            # 记录未找到条目的日志
            log = Log(
                level='warning',
                message=f'API删除白名单条目失败：条目不存在',
                source='api',
                ip_address=request.remote_addr,
                user_id=token.user_id if token else None,
                details=f'endpoint: /whitelist/entries/{entry_type}/{value}, type: {entry_type}, value: {value}, token: {token.name if token else None}'
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
            user_id=token.user_id if token else None,
            details=f'endpoint: /whitelist/entries/{entry_type}/{value}, entry_id: {entry.id}, description: {entry.description}, token: {token.name if token else None}'
        )
        db.session.add(log)

        # 删除条目
        db.session.delete(entry)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Entry deleted successfully',
            'deleted_by': f'api_token_{token.name if token else "unknown"}'
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
@require_api_auth  # 添加Token验证
def log_login():
    """记录登录事件"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': 'No data provided'
            }), 400

        # 获取Token信息
        token = getattr(request, 'token', None)

        # 验证必需字段
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

        # 记录Minecraft玩家登入事件
        log = Log.create_login_log(
            player_name=player_name,
            player_uuid=player_uuid,
            player_ip=player_ip,
            allowed=allowed,
            check_type=check_type,
            server_id=server_id,
            user_id=token.user_id if token else None
        )

        # 如果允许登入，创建或更新会话记录
        session_id = None
        if allowed:
            # 查找该玩家是否有未关闭的会话
            open_session = LoginSession.query.filter_by(
                player_name=player_name,
                server_id=server_id,
                logout_time=None
            ).first()
            if open_session:
                # 已有打开会话，更新登入时间
                open_session.login_time = datetime.utcnow()
                open_session.login_ip = player_ip
                if player_uuid:
                    open_session.player_uuid = player_uuid
                db.session.commit()
                session_id = open_session.id
            else:
                # 创建新会话 - 如服务器刚恢复，用恢复时间
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


@api_bp.route('/login/logout', methods=['POST'])
@require_api_auth
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

        # 记录登出日志
        log = Log(
            level='login',
            message=f'Player logout: {player_name}',
            source='api',
            ip_address=player_ip,
            player_name=player_name,
            player_uuid=player_uuid,
            server_id=server_id,
            user_id=token.user_id if token else None,
            details=f'player_name: {player_name}, player_uuid: {player_uuid}, action: logout, server_id: {server_id}'
        )
        db.session.add(log)

        # 关闭最近的打开会话
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
            # 没有打开会话 - 用服务器恢复时间作为登入时间，正常关闭
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
            message='API记录登出事件失败',
            source='api',
            ip_address=request.remote_addr,
            details=f'endpoint: /login/logout, error: {str(e)}'
        )
        db.session.add(log)
        db.session.commit()

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

        # 构建响应
        response_data = {
            'success': True,
            'message': 'Token is valid',
            'token': {
                'id': token.id,
                'name': token.name,
                'created_at': token.created_at.isoformat() if token.created_at else None,
                'expires_at': token.expires_at.isoformat() if token.expires_at else None,
                'is_active': token.is_active,
                'permissions': {
                    'can_read': token.can_read,
                    'can_write': token.can_write,
                    'can_delete': token.can_delete,
                    'can_manage': token.can_manage
                }
            },
            'valid_until': token.expires_at.isoformat() if token.expires_at else 'never'
        }

        print(f"[API] ✅ Token verification successful for: {token.name}")

        return jsonify(response_data)

    except Exception as e:
        print(f"[API] ❌ Token verification error: {str(e)}")
        import traceback
        print(f"[API] Stack trace: {traceback.format_exc()}")

        return jsonify({
            'success': False,
            'message': f'Token verification failed: {str(e)}'
        }), 500


@api_bp.route('/tokens/create', methods=['POST'])
def create_token():
    """创建新的API Token（需要管理员权限）"""
    from flask_login import current_user
    from models.user import User

    try:
        # 验证管理员权限（通过Web登录）
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

        # 必需字段
        name = data.get('name', '').strip()
        if not name:
            return jsonify({
                'success': False,
                'message': 'Token name is required'
            }), 400

        # 权限设置
        permissions = {
            'can_read': data.get('can_read', True),
            'can_write': data.get('can_write', False),
            'can_delete': data.get('can_delete', False),
            'can_manage': data.get('can_manage', False)
        }

        # 有效期（天）
        days_valid = data.get('days_valid', 365)

        # 创建Token
        from utils.auth import generate_api_key
        token_str = generate_api_key()

        token = Token(
            token=token_str,
            name=name,
            user_id=current_user.id,
            can_read=permissions['can_read'],
            can_write=permissions['can_write'],
            can_delete=permissions['can_delete'],
            can_manage=permissions['can_manage']
        )

        if days_valid:
            from utils.timezone import now_utc
            from datetime import timedelta
            token.expires_at = now_utc() + timedelta(days=days_valid)

        db.session.add(token)
        db.session.commit()

        # 记录操作日志
        log = Log(
            level='info',
            message=f'创建API Token: {name}',
            source='api',
            ip_address=request.remote_addr,
            user_id=current_user.id,
            details=f'token_id: {token.id}, permissions: {permissions}'
        )
        db.session.add(log)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Token created successfully',
            'token': token_str,  # 只在这里返回完整token
            'token_info': {
                'id': token.id,
                'name': token.name,
                'created_at': token.created_at.isoformat() if token.created_at else None,
                'expires_at': token.expires_at.isoformat() if token.expires_at else None,
                'permissions': permissions
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Failed to create token: {str(e)}'
        }), 500