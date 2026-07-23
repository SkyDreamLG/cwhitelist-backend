# CWhitelist 后端 — 现代化白名单 API 与管理控制台

<div align="center">
  <br>
  <em>面向 API 的 CWhitelist 后端与管理界面 —— 为 Minecraft 白名单管理提供中心化服务。</em>
</div>

<p align="center">
  <a href="https://github.com/SkyDreamLG/cwhitelist-backend/releases"><img alt="release" src="https://img.shields.io/github/v/release/SkyDreamLG/cwhitelist-backend?style=for-the-badge&color=4A90E2"></a>
  <a href="https://github.com/SkyDreamLG/cwhitelist-backend/issues"><img alt="issues" src="https://img.shields.io/github/issues/SkyDreamLG/cwhitelist-backend?style=for-the-badge&color=FF6B6B"></a>
  <a href="https://github.com/SkyDreamLG/cwhitelist-backend"><img alt="repo" src="https://img.shields.io/badge/repo-SkyDreamLG/cwhitelist--backend-6f42c1?style=for-the-badge"></a>
</p>

---

中文 | [English](./README.md)

CWhitelist 后端是一个基于 Flask 的轻量级服务，提供 REST API 用于白名单同步、管理和登录日志记录，并附带网页管理界面。适合作为 CWhitelist Minecraft 模组（或其他客户端）的中心化数据中心。

**当前版本：2.0.0**

## 主要功能

- 基于 Token 的 RESTful API 认证
- 服务器健康检查与心跳追踪，超时自动离线检测
- 白名单同步接口（按 server_id 划分，支持 name/uuid/ip）
- 通过 API 添加/删除白名单条目，均需 server_id 范围限定
- 登入/登出事件上报，自动计算在线时长
- 玩家数据分析仪表板 — 在线时间图、IP 地理位置、服务器活力排行
- 管理后台 Web UI，支持国际化（简体中文 / English）
- 服务器状态监控，自动清理离线服务器的会话
- 全页面时区感知的时间显示
- 命令行启动，可选 GUI 配置

## 快速开始

先决条件：
- Python 3.8+（推荐 3.10+）
- pip

1. 克隆仓库
```bash
git clone https://github.com/SkyDreamLG/cwhitelist-backend.git
cd cwhitelist-backend
```

2. 创建并激活虚拟环境
```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
```

3. 安装依赖
```bash
pip install -r requirements.txt
```

4. 运行应用
```bash
python app.py

# 带选项运行
python app.py --host 0.0.0.0 --port 5000 --no-gui
```

5. 打开管理界面
- 启动后在浏览器中访问（默认 http://127.0.0.1:5000），首次运行需完成 OOBE 初始化向导创建管理员账号。

## 配置

通过 `config.py` 与环境变量配置：

| 变量 | 说明 | 默认值 |
|----------|-------------|---------|
| `SECRET_KEY` | Flask 密钥 | 自动生成（生产环境务必修改） |
| `TIMEZONE` | 默认时区 | `Asia/Shanghai` |
| `DATABASE_URL` | SQLAlchemy 连接字符串 | `sqlite:///instance/cwhitelist.db` |
| `SESSION_TYPE` | 会话存储方式 | `filesystem` |
| `PERMANENT_SESSION_LIFETIME` | 会话超时 | 60 分钟 |

```bash
export SECRET_KEY="replace-with-production-secret"
export DATABASE_URL="sqlite:///instance/cwhitelist.db"
python app.py --no-gui
```

## API 概览

基础路径：`{host}/api`

### 健康检查
```
GET /api/health?server_id=<id>
```
无需认证。`server_id` **必填**，同时作为服务器心跳上报。若某服务器超过 60 秒未上报心跳，其所有未关闭的玩家会话将自动关闭。

```json
{
  "success": true,
  "status": "ok",
  "server_id": "lobby",
  "timestamp": "2026-07-23T00:00:00Z",
  "service": "CWhitelist API",
  "version": "2.0.0"
}
```

### 同步白名单
```
GET /api/whitelist/sync?server_id=<id>&only_active=true
```
需要 Token（读取权限）。`server_id` **必填**。

### 添加白名单条目
```
POST /api/whitelist/entries
```
需要 Token（写入权限）。请求体：
```json
{
  "type": "name",
  "value": "PlayerName",
  "server_id": "lobby",
  "description": "VIP Player",
  "expires_at": "2026-12-31T23:59:59Z"
}
```

### 删除白名单条目
```
DELETE /api/whitelist/entries/<type>/<value>?server_id=<id>
```
需要 Token（删除权限）。`server_id` **必填**。

### 记录登入事件
```
POST /api/login/log
```
需要 Token（写入权限）。请求体：
```json
{
  "player_name": "SkyDream",
  "player_uuid": "xxx-xxx-xxx",
  "player_ip": "192.168.1.100",
  "allowed": true,
  "server_id": "lobby",
  "check_type": "name"
}
```

### 记录登出事件
```
POST /api/login/logout
```
需要 Token（写入权限）。请求体：
```json
{
  "player_name": "SkyDream",
  "player_uuid": "xxx-xxx-xxx",
  "player_ip": "192.168.1.100",
  "server_id": "lobby"
}
```
自动计算在线时长。若无已打开的会话（如服务器刚恢复），则以服务器恢复时间作为登入时间自动创建会话。

### 验证 Token
```
GET /api/tokens/verify
```
需要 Token。返回 Token 状态、权限和有效期。

### 认证方式
- Header：`Authorization: Bearer <token>`（推荐）
- 查询参数：`?token=<token>`

### Token 权限
- **读取** — 同步白名单
- **写入** — 添加条目、记录事件
- **删除** — 删除条目
- **管理** — 管理员操作

## 白名单 JSON 导入/导出

### 导出格式
```json
[
  {
    "type": "name",
    "value": "SkyDream_LG",
    "server_id": "lobby",
    "description": "管理员玩家",
    "created_by": "admin",
    "created_at": "2026-07-23T10:00:00",
    "expires_at": null,
    "is_active": true
  },
  {
    "type": "uuid",
    "value": "117a97e0-10ad-338d-aae2-54c4ec32959f",
    "server_id": "survival",
    "description": "",
    "created_by": "admin",
    "created_at": "2026-07-23T10:05:00",
    "expires_at": "2026-12-31T23:59:59",
    "is_active": true
  }
]
```

### 导入格式
每个条目的最小必填字段：
```json
[
  {"type": "name", "value": "PlayerName", "server_id": "lobby"},
  {"type": "uuid", "value": "117a97e0-10ad-338d-aae2-54c4ec32959f", "server_id": "lobby"},
  {"type": "ip", "value": "192.168.1.100", "server_id": "survival"}
]
```
- `type`：`name`、`uuid` 或 `ip`（必填）
- `value`：条目值（必填）
- `server_id`：可在 JSON 中每个条目单独指定，也可通过导入表单统一设置（必填）
- `description`：可选
- `is_active`：可选，默认 `true`

## Web 管理界面

内置管理后台提供：

- **仪表板** — KPI 卡片、登陆趋势图（白名单/游客分类）、快速操作入口
- **白名单管理** — 增删改查，按 server_id 划分，支持 JSON 导入/导出
- **登陆日志** — 可按服务器、事件类型（允许/拒绝/登出）、玩家名筛选
- **系统日志** — 支持忽略健康检查日志，日志级别统计
- **用户分析** — 单人玩家在线时间线、会话记录、IP 地理位置、服务器活力总览与玩家排行
- **Token 管理** — 创建/管理 API Token，支持细粒度权限
- **设置** — 时区、语言、服务器配置
- **API 文档** — 内置交互式文档

国际化：通过顶栏语言选择器切换简体中文 / English。

## 主要文件与目录

```
.
├── app.py                     # 应用入口
├── config.py                  # 配置类
├── routes/
│   ├── api.py                 # 所有 API 接口
│   ├── web.py                 # Web UI 路由
│   └── auth.py                # 认证路由
├── models/                    # 数据模型
│   ├── whitelist.py           # WhitelistEntry
│   ├── token.py               # API Token
│   ├── log.py                 # 系统/登陆日志
│   ├── session.py             # LoginSession（登入/登出追踪）
│   ├── server_status.py       # 服务器心跳追踪
│   ├── user.py                # 用户账号
│   └── setting.py             # 系统设置
├── templates/                 # Jinja2 模板
├── static/                    # CSS/JS 资源
├── translations/              # 国际化文件 (.po/.mo)
├── instance/                  # 默认 SQLite 数据库
└── requirements.txt
```

## 生产部署建议

**Gunicorn（WSGI）：**
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 "app:app"
```

**安全建议：**
- 设置强 `SECRET_KEY`
- 使用反向代理（Nginx）+ TLS
- 生产环境使用 PostgreSQL/MySQL
- 限制管理界面访问权限

## 开发

```bash
python app.py --debug
```

修改模板后更新翻译：
```bash
pybabel extract -F babel.cfg -o messages.pot .
pybabel update -i messages.pot -d translations
pybabel compile -d translations
```

## 常见问题

- **SQLite "数据库被锁定"**：生产建议使用 PostgreSQL
- **Token 401/403**：确认 Token 存在且权限正确
- **缺少 `server_id` 列**：执行 `ALTER TABLE whitelist_entries ADD COLUMN server_id VARCHAR(36) NOT NULL DEFAULT 'default'`
- **缺少 `login_sessions` 表**：确保 Flask 启动时模型正确导入以自动建表，或手动迁移

## 许可证

GNU General Public License v3.0

## 支持

- Issues: https://github.com/SkyDreamLG/cwhitelist-backend/issues
- 邮箱: 1607002411@qq.com

---

由 SkyDream 团队维护。如果这个项目对你有帮助，欢迎在 GitHub 上点个 ⭐！
