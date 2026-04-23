# Supervisor 守护进程监控系统 - 部署文档

## 一、环境依赖

### 1.1 系统要求

- Linux 服务器（推荐 Ubuntu 20.04+、CentOS 7+）
- Python 3.12.7
- Supervisor（用于管理守护进程）
- 宝塔面板（用于部署与管理）

### 1.2 安装 Supervisor

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install supervisor

# CentOS/RHEL
sudo yum install supervisor

# 启动并设置开机自启
sudo systemctl start supervisord
sudo systemctl enable supervisord
```

确保 Supervisor 的 XML-RPC 接口已启用。编辑 `/etc/supervisor/supervisord.conf`，确认包含：

```ini
[unix_http_server]
file=/var/run/supervisor.sock
chmod=0770
chown=root:www

[inet_http_server]
port=127.0.0.1:9001

[rpcinterface:supervisor]
supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface

[supervisord]
logfile=/tmp/supervisord.log ; main log file; default $CWD/supervisord.log
logfile_maxbytes=50MB        ; max main logfile bytes b4 rotation; default 50MB
logfile_backups=10           ; # of main logfile backups; 0 means none, default 10
loglevel=info                ; log level; default info; others: debug,warn,trace
pidfile=/tmp/supervisord.pid ; supervisord pidfile; default supervisord.pid
nodaemon=false               ; start in foreground if true; default false
minfds=1024                  ; min. avail startup file descriptors; default 1024
minprocs=200                 ; min. avail process descriptors;default 200

[supervisorctl]
serverurl=unix:///var/run/supervisor.sock

[include]
files = /etc/supervisor/conf.d/*.conf
```

### 1.3 安装 Python 3.12

```bash
# Ubuntu 22.04+ 自带 Python 3.10，如需 3.12 可使用 deadsnakes PPA
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.12 python3.12-venv python3.12-dev
```

## 二、项目部署步骤

### 2.1 上传项目

将项目文件上传到服务器，例如 `/www/wwwroot/supervisor-monitor/`。

### 2.2 创建虚拟环境

```bash
cd /www/wwwroot/supervisor-monitor
python3.12 -m venv venv
source venv/bin/activate  # Linux
```

### 2.3 安装依赖

```bash
pip install -r requirements.txt
```

### 2.4 配置环境变量

创建 `.env` 文件或通过系统环境变量设置：

```bash
# 管理员账号（生产环境务必修改）
export ADMIN_USER=admin
export ADMIN_PASSWORD=your_secure_password

# 安全密钥（生产环境务必修改）
export SECRET_KEY=your_random_secret_key

# Supervisor 连接（当前采用：Unix socket + 本机 HTTP 回退）
export SUPERVISOR_SOCKET_PATH=/var/run/supervisor.sock
export SUPERVISOR_RPC_URL=http://127.0.0.1:9001/RPC2

# Supervisor 配置目录（需确保运行用户有写权限）
export SUPERVISOR_CONF_DIR=/etc/supervisor/conf.d
export SUPERVISOR_CONF_EXT=conf

# 前端启停重启统一走 systemd（当前采用）
export SUPERVISOR_START_CMD="sudo systemctl start supervisord"
export SUPERVISOR_STOP_CMD="sudo systemctl stop supervisord"
export SUPERVISOR_RESTART_CMD="sudo systemctl restart supervisord"

# 配置写入/删除使用 sudo（当前采用）
export SUPERVISOR_USE_SUDO_RM=1
export SUPERVISOR_USE_SUDO_WRITE=1
```

若宝塔环境变量未生效，请在项目根目录创建 `config_local.env`，填入以上相同变量。

### 2.5 配置目录权限（添加/删除进程必需）

监控系统需向 `/etc/supervisor/conf.d/` 写入和删除配置文件。若出现「Permission denied」或「权限不足」，执行：

```bash
# 赋予 www 用户对 conf.d 的完整读写权限
sudo chown -R www:www /etc/supervisor/conf.d
sudo chmod 775 /etc/supervisor/conf.d
```

## 三、宝塔面板部署

### 3.1 创建 Python 项目

1. 登录宝塔面板
2. 进入「软件商店」→ 安装「Python 项目管理器」（如未安装）
3. 进入「Python 项目」→「添加项目」
4. 填写：
   - 项目名称：supervisor-monitor
   - 项目路径：/www/wwwroot/supervisor-monitor
   - Python 版本：3.12
   - 框架：Flask
   - 启动方式：uWSGI

### 3.2 配置 uWSGI

在项目设置中，uWSGI 配置示例：

```ini
[uwsgi]
chdir = /www/wwwroot/supervisor-monitor
module = wsgi:app
callable = app
home = /www/wwwroot/supervisor-monitor/venv
http = 0.0.0.0:5000
processes = 2
threads = 2
```

### 3.3 环境变量

在宝塔 Python 项目设置中，添加环境变量：

- `ADMIN_USER`
- `ADMIN_PASSWORD`
- `SECRET_KEY`
- `SUPERVISOR_CONF_DIR`（如与默认不同）
- `FLASK_ENV=production`

### 3.4 Nginx 反向代理

若使用域名访问，在宝塔「网站」中添加反向代理：

- 代理名称：supervisor-monitor
- 目标 URL：`http://127.0.0.1:5000`

## 四、启动与验证

### 4.1 开发环境启动

```bash
cd /www/wwwroot/supervisor-monitor
source venv/bin/activate
python run.py
```

访问 `http://服务器IP:5000`。

### 4.2 生产环境（uWSGI）

```bash
uwsgi --ini uwsgi.ini
```

通过宝塔面板「启动项目」。

### 4.3 验证

1. 访问系统首页，应显示登录界面
2. 使用配置的管理员账号登录
3. 登录后应看到守护进程监控面板
4. 若 Supervisor 中已有进程，应能正常显示

## 五、宝塔面板配置检查清单

在宝塔「Python 项目管理」中创建/修改项目时，请确认以下配置：

| 配置项 | 正确值 | 说明 |
|--------|--------|------|
| 项目路径 | `/www/wwwroot/supervisor-monitor` | 项目根目录，与 wsgi.py 同级 |
| 入口文件 | `/www/wwwroot/supervisor-monitor/wsgi.py` | 完整绝对路径 |
| 应用名称 | `app` | wsgi.py 中导出的变量名 |
| 通讯协议 | `wsgi` | 使用 WSGI 协议 |
| 通信方式 | `http` | 与 Nginx 反向代理方式匹配 |
| 启动用户 | `www` | 需确保对项目目录有读权限、对 logs 有写权限 |

**环境变量**：务必在「环境变量」中选择「指定变量」，添加：
- `ADMIN_USER`：管理员用户名
- `ADMIN_PASSWORD`：管理员密码
- `SECRET_KEY`：随机密钥（生产环境必改）
- `FLASK_ENV`：`production`
- `SUPERVISOR_SOCKET_PATH`：`/var/run/supervisor.sock`（解决 Connection refused，路径以 supervisord.conf 为准）

**目录权限**：确保 `www` 用户可写 `logs/` 目录：
```bash
chown -R www:www /www/wwwroot/supervisor-monitor
chmod 755 /www/wwwroot/supervisor-monitor
mkdir -p /www/wwwroot/supervisor-monitor/logs
chmod 775 /www/wwwroot/supervisor-monitor/logs
```

## 六、常见问题

### 6.1 500 Internal Server Error

可能原因及排查：

1. **路径错误**：确认项目路径、入口文件为绝对路径，且 static、templates 目录存在
2. **环境变量缺失**：在宝塔中配置 `SECRET_KEY`、`ADMIN_USER`、`ADMIN_PASSWORD`
3. **Python 环境**：确认虚拟环境已激活，依赖已安装（`pip install -r requirements.txt`）
4. **日志目录**：`logs/` 需存在且 www 用户可写
5. **查看 uWSGI 日志**：宝塔面板 → 项目 → 日志，查看具体报错

### 6.2 连接 Supervisor 失败

当前采用的连接配置如下：

```ini
[unix_http_server]
file=/var/run/supervisor.sock
chmod=0770
chown=root:www

[inet_http_server]
port=127.0.0.1:9001

[supervisorctl]
serverurl=unix:///var/run/supervisor.sock
```

排查顺序：
1. 确认 `systemctl status supervisord` 为 `active (running)`
2. 确认 `ls -l /var/run/supervisor.sock` 存在且组为 `www`
3. 确认应用环境变量含 `SUPERVISOR_SOCKET_PATH=/var/run/supervisor.sock`
4. 若 socket 暂不可用，系统会按 `SUPERVISOR_RPC_URL` 回退到 `127.0.0.1:9001`

修改后需**重启 Python 项目**使权限生效。

### 6.3 添加/删除进程失败：Permission denied

无法写入或删除 `/etc/supervisor/conf.d/` 下的配置文件。

当前采用配置：
```bash
sudo chown -R www:www /etc/supervisor/conf.d
sudo chmod 775 /etc/supervisor/conf.d
sudo visudo -f /etc/sudoers.d/supervisor-monitor
```

在 `/etc/sudoers.d/supervisor-monitor` 中添加：
```
www ALL=(ALL) NOPASSWD: /usr/bin/rm -f /etc/supervisor/conf.d/*.conf
www ALL=(ALL) NOPASSWD: /usr/bin/tee /etc/supervisor/conf.d/*.conf
www ALL=(ALL) NOPASSWD: /usr/bin/systemctl start supervisord
www ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop supervisord
www ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart supervisord
```

设置权限：
```bash
sudo chmod 440 /etc/sudoers.d/supervisor-monitor
```

说明：若你的系统中 `systemctl`、`tee`、`rm` 路径不同，请先用 `which systemctl`、`which tee`、`which rm` 获取实际路径并替换上面内容。

### 6.4 systemd 显示运行但前端无进程（CGroup 残留）

现象：`systemctl status supervisord` 的 CGroup 里还有 WorkerMan1/WorkerMan2 进程，但前端列表为空或与 `supervisorctl status` 不一致。

原因：systemd 看到的是 cgroup 内存活进程；前端看到的是 Supervisor 当前已加载配置。若服务文件使用 `KillMode=process`，停止/重启时可能残留子进程。

处理步骤：

1. 修改 systemd service，确保如下配置：
   ```ini
   [Service]
   Type=forking
   ExecStart=/usr/bin/supervisord -c /etc/supervisor/supervisord.conf
   ExecStop=/usr/bin/supervisorctl -c /etc/supervisor/supervisord.conf shutdown
   KillMode=control-group
   Restart=on-failure
   ```
2. 重载并重启服务：
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart supervisord
   ```
3. 对比托管状态与进程：
   ```bash
   sudo supervisorctl -c /etc/supervisor/supervisord.conf status
   sudo systemctl status supervisord
   ```
4. 若存在未托管残留 PID，确认业务影响后手工清理：
   ```bash
   ps -o pid,ppid,cmd -p <PID1>,<PID2>
   sudo kill <PID1> <PID2>
   ```

### 6.5 添加进程失败：其他权限问题

- 检查 `SUPERVISOR_CONF_DIR` 目录权限
- 确认运行用户对该目录有写权限

### 6.6 登录后 401

- 检查 Session 配置，确保 `SECRET_KEY` 已设置
- 若使用 Nginx 反向代理，确认 Cookie 可正常传递

### 6.7 配置加载失败：进程名称包含非法字符（CANT_REREAD）

当出现「配置加载失败：存在包含非法字符的进程名称」时，说明 `conf.d` 目录下存在进程名包含冒号（`:`）的配置。Supervisor 进程名不能包含冒号。

**处理步骤：**

1. 检查 `/etc/supervisor/conf.d/` 下的 `.conf` 文件
2. 将 `[program:sora:video]` 改为 `[program:sora_video]`（冒号改为下划线）
3. 同时修改配置文件名，如 `sora:video.conf` → `sora_video.conf`
4. 执行 `supervisorctl reread` 或在前端重新加载

**命名规范：** 进程名称仅支持英文字母、数字、下划线和连字符，不能包含冒号。
