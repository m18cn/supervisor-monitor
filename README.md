# Supervisor 守护进程实时监控系统

基于 Flask + jQuery 的 Supervisor 守护进程监控与管理 Web 系统，支持实时状态展示、添加/删除进程、启动/停止/重启等操作。

## 功能特性

- **实时监控**：每 4 秒自动刷新进程状态，延迟不超过 5 秒
- **进程管理**：添加、删除、启动、停止、重启守护进程
- **完整配置**：添加进程时支持工作目录、自动重启策略、日志路径等参数
- **安全认证**：登录验证，防止未授权访问
- **操作日志**：记录所有关键操作到 `logs/operations.log`

## 技术栈

- 前端：jQuery 3.x、HTML5、CSS3
- 后端：Python 3.12、Flask 3.x
- 认证：Flask-Login
- 与 Supervisor 交互：XML-RPC

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量（按当前部署方案）

```bash
export ADMIN_USER=admin
export ADMIN_PASSWORD=admin123
export SECRET_KEY=your-secret-key

# Supervisor 连接（当前采用：Unix socket + 本机 HTTP 回退）
export SUPERVISOR_SOCKET_PATH=/var/run/supervisor.sock
export SUPERVISOR_RPC_URL=http://127.0.0.1:9001/RPC2
export SUPERVISOR_CONF_DIR=/etc/supervisor/conf.d
export SUPERVISOR_CONF_EXT=conf

# 前端启停重启统一走 systemd
export SUPERVISOR_START_CMD="sudo systemctl start supervisord"
export SUPERVISOR_STOP_CMD="sudo systemctl stop supervisord"
export SUPERVISOR_RESTART_CMD="sudo systemctl restart supervisord"

# 配置写入/删除使用 sudo
export SUPERVISOR_USE_SUDO_RM=1
export SUPERVISOR_USE_SUDO_WRITE=1
```

同时请确保 `supervisord.conf` 已启用：
- `[unix_http_server]`：`file=/var/run/supervisor.sock`、`chmod=0770`、`chown=root:www`
- `[inet_http_server]`：`port=127.0.0.1:9001`
- `[supervisorctl]`：`serverurl=unix:///var/run/supervisor.sock`

### 3. 启动

```bash
python run.py
```

### 4. 访问

打开浏览器访问 `http://localhost:5000`，使用配置的账号密码登录。

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/status | 获取所有进程状态 |
| POST | /api/process | 添加守护进程 |
| DELETE | /api/process/<name> | 删除守护进程 |
| POST | /api/process/<name>/start | 启动进程 |
| POST | /api/process/<name>/stop | 停止进程 |
| POST | /api/process/<name>/restart | 重启进程 |
| GET | /api/login | 检查登录状态 |
| POST | /api/login | 登录 |
| POST | /api/logout | 登出 |

所有接口（除登录外）需先登录，返回格式统一为：

```json
{
  "success": true,
  "message": "操作成功",
  "data": { ... }
}
```

## 部署

详见 [DEPLOY.md](DEPLOY.md)（已按当前线上方案整理）。

## 性能要求

- 状态更新延迟：≤ 5 秒
- 支持进程数：≥ 20 个
- 页面加载时间：≤ 3 秒

## 许可证

MIT
