# CWhitelist 后端 — 现代化白名单 API 与管理控制台

<div align="center">
  <br>
  <em>📡 面向 API 的 CWhitelist 后端与管理界面 —— 为 Minecraft 白名单管理提供中心化服务。</em>
</div>

<p align="center">
  <a href="https://github.com/SkyDreamLG/cwhitelist-backend/releases"><img alt="release" src="https://img.shields.io/github/v/release/SkyDreamLG/cwhitelist-backend?style=for-the-badge&color=4A90E2"></a>
  <a href="https://github.com/SkyDreamLG/cwhitelist-backend/issues"><img alt="issues" src="https://img.shields.io/github/issues/SkyDreamLG/cwhitelist-backend?style=for-the-badge&color=FF6B6B"></a>
  <a href="https://github.com/SkyDreamLG/cwhitelist-backend"><img alt="repo" src="https://img.shields.io/badge/repo-SkyDreamLG/cwhitelist--backend-6f42c1?style=for-the-badge"></a>
</p>

---

中文 | [English](./README.md)

CWhitelist 后端是一个基于 Flask 的轻量级服务，提供用于白名单同步、管理和登录日志记录的 REST API，并附带网页管理界面（模板已包含）。该后端适合作为 CWhitelist Minecraft 模组或其它客户端的数据中心。

## 主要功能

- 基于 Token 的 API 认证（支持 Header 或 query 参数）
- 健康检查接口，便于监控
- 白名单同步接口，可按是否激活与服务器 ID 过滤
- 通过 API 添加 / 删除白名单条目（支持 name、uuid、ip）
- 登录事件上报接口（用于记录玩家登录尝试）
- 管理界面与内置 API 文档页（templates/api_docs.html）
- 默认使用 SQLite，支持通过环境变量切换数据库
- 会话与文件上传目录支持
- 启动脚本支持命令行参数与可选 GUI 配置提示

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
（如果仓库没有 requirements.txt，至少安装 Flask、SQLAlchemy、Flask-Login、Flask-Session 等：`pip install Flask SQLAlchemy Flask-Login Flask-Session`）

4. 运行应用
```bash
# 默认监听 0.0.0.0:5000
python app.py

# 带选项运行
python app.py --host 0.0.0.0 --port 5000 --no-gui
```

5. 打开管理界面
- 启动后控制台会输出地址（例如 http://127.0.0.1:5000），在浏览器中访问以查看后台管理 UI 和 API 文档。

## 配置

通过 config.py 与环境变量配置。常用配置项：

- SECRET_KEY — Flask 密钥（环境变量：SECRET_KEY）
- TIMEZONE — 时区（环境变量：TIMEZONE）
- DATABASE_URL — SQLAlchemy 连接字符串（环境变量：DATABASE_URL），默认：
  sqlite:///instance/cwhitelist.db
- SESSION_TYPE — 会话类型（默认 filesystem）
- PERMANENT_SESSION_LIFETIME — 会话过期时间（默认 60 分钟）
- API_PREFIX — API 前缀（默认 /api）
- API_VERSION — 版本（默认 v1）
- UPLOAD_FOLDER — 上传目录

可通过 FLASK_CONFIG 环境变量选择配置类（例如 `config.DevelopmentConfig` 或 `config.ProductionConfig`）。

示例（Linux / macOS）：
```bash
export FLASK_CONFIG=config.DevelopmentConfig
export SECRET_KEY="replace-with-production-secret"
export DATABASE_URL="sqlite:///instance/cwhitelist.db"
python app.py --no-gui
```

## API 概览

基础路径：{host}{API_PREFIX}（默认 /api）

- GET /api/health
  - 健康检查（无需认证）
  - 示例响应：
  ```json
  {
    "success": true,
    "status": "ok",
    "timestamp": "2024-01-01T00:00:00Z",
    "service": "CWhitelist API",
    "version": "1.0.0"
  }
  ```

- GET /api/whitelist/sync
  - 同步白名单条目
  - 需要 Token（Header 或 ?token=）
  - 查询参数：
    - server_id（可选）
    - only_active（默认 true）
    - include_expired（可选）
  - 示例：
    ```
    curl -H "Authorization: Bearer YOUR_TOKEN" "http://host:5000/api/whitelist/sync?only_active=true"
    ```

- POST /api/whitelist/entries
  - 添加白名单条目
  - 请求体 JSON：{ "type": "name|uuid|ip", "value": "<值>", "description": "", "expires_at": "ISO8601", "is_active": true }
  - 需要拥有写权限的 Token

- DELETE /api/whitelist/entries/<type>/<value>
  - 按类型和值删除条目
  - 需要拥有删除权限的 Token

- POST /api/login/log
  - 上报玩家登录事件（player_name, player_uuid, player_ip, allowed, check_type）
  - 需要写权限的 Token

- GET /api/tokens/verify
  - 校验 Token 状态与权限

认证方式：
- 推荐使用 Header：Authorization: Bearer <token>
- 也支持 ?token=<token> 作为回退

权限粒度（系统内 Token 字段）：
- Read：同步白名单
- Write：添加条目 / 记录事件
- Delete：删除条目
- Manage：管理型权限（用户/Token 管理等）

详见内置 API 文档页面 templates/api_docs.html 中的示例与说明。

## 重要文件与目录（选取）

```
.
├── app.py                 # 应用入口与 CLI 启动逻辑
├── config.py              # 配置类与默认值
├── routes/
│   └── api.py             # API 路由（health、sync、add/delete、login log）
├── models/                # 数据模型（WhitelistEntry、Token、Log 等）
├── templates/             # 管理界面与 API 文档模板
├── instance/              # 默认数据库与实例数据目录（sqlite）
└── requirements.txt       # Python 依赖（如果存在）
```

## 数据库

默认：SQLite（instance/cwhitelist.db）。生产环境建议使用 PostgreSQL 或 MySQL，并通过 DATABASE_URL 指定。

示例（Postgres）：
```
export DATABASE_URL="postgresql://user:password@db_host:5432/cwhitelist"
```

## 生产部署建议

- 使用 Gunicorn（或其它 WSGI 服务器）：
  ```
  pip install gunicorn
  gunicorn -w 4 -b 0.0.0.0:5000 "app:app"
  ```
- 使用反向代理（如 Nginx）并启用 HTTPS（TLS）
- 使用 Docker（如添加 Dockerfile）并挂载持久化数据卷
- 使用 systemd / supervisord 管理进程
- 设置强 Secret Key、数据库备份和访问控制

## 开发与测试

- 建议使用虚拟环境并安装 dev 依赖
- 本地调试：
  ```
  python app.py --debug
  ```
- 如果添加测试，建议使用 pytest 并在 CI 中运行

## 常见问题与故障排查

- SQLite 出现 "database is locked"：
  - SQLite 对并发写支持有限，生产请使用 Postgres/MySQL。
- Token ��证失败：
  - 确认 Token 存在数据库且权限（can_read/can_write/can_delete）正确；可调用 /api/tokens/verify。
- API 返回 403（权限不足）：
  - Token 缺少对应权限范围。

后端将通过 Log 模型记录详细日志，运行时也可能输出到控制台，检查日志以获取更多错误上下文。

## 贡献

欢迎贡献！流程建议：
1. Fork 仓库
2. 新建功能分支：git checkout -b feature/your-feature
3. 提交并推送：git commit -m "Add feature" && git push
4. 发起 Pull Request

请为新功能附上测试与文档，并保持向后兼容性。

## 许可证与致谢

- 许可证请参阅仓库中的 LICENSE 文件（如存在）。
- 感谢所有贡献者与社区的反馈与测试。

## 支持

- Issues: https://github.com/SkyDreamLG/cwhitelist-backend/issues
- 邮箱: 1607002411@qq.com

---

由 SkyDream 团队维护。如果这个项目对你有帮助，欢迎在 GitHub 上点个 ⭐！