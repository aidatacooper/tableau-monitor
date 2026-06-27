# Tableau Flow Monitor

自动监控 Tableau Server 上长时间运行的 Flow 任务，超时自动取消。

## 功能

- 每 10 分钟检查一次 Flow 运行状态
- 超过 1 小时未完成的任务自动取消
- 支持自定义超时阈值
- 支持 `--dry-run` 模式（只检查不取消）
- 日志输出到 systemd journal
- 开机自启、崩溃自动重启

## 快速开始

### 1. 安装依赖

```bash
pip install tableauserverclient python-dotenv
```

### 2. 配置

复制 `.env.example` 为 `.env`，填入你的 Tableau Server 信息：

```bash
cp .env.example .env
vim .env
```

```env
TABLEAU_SERVER_URL = 'https://your-tableau-server.com'
PERSONAL_ACCESS_TOKEN_NAME = 'your_token_name'
PERSONAL_ACCESS_TOKEN_SECRET = 'your_token_secret'
SITE_NAME = ''
```

### 3. 测试运行

```bash
# 只检查一次，不取消（测试用）
python monitor_long_flows.py --once --dry-run

# 只检查一次，超时会实际取消
python monitor_long_flows.py --once
```

### 4. 部署为系统服务

```bash
# 创建 service 文件
cat > /etc/systemd/system/tableau-monitor.service << 'EOF'
[Unit]
Description=Tableau Flow Monitor - Auto cancel long-running flows
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/tableau-monitor
ExecStart=/usr/bin/python3 /opt/tableau-monitor/monitor_long_flows.py
Restart=on-failure
RestartSec=60
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# 启用并启动
systemctl daemon-reload
systemctl enable tableau-monitor
systemctl start tableau-monitor
```

## 使用方式

```bash
# 默认：每 10 分钟检查，超 1h 自动取消
python monitor_long_flows.py

# 只检查不取消
python monitor_long_flows.py --dry-run

# 自定义超时阈值（2 小时）
python monitor_long_flows.py --timeout 2

# 组合使用
python monitor_long_flows.py --dry-run --timeout 0.5

# 只运行一次就退出
python monitor_long_flows.py --once
```

## 服务管理

```bash
# 查看状态
systemctl status tableau-monitor

# 查看实时日志
journalctl -u tableau-monitor -f

# 查看最近日志
journalctl -u tableau-monitor --since "10 min ago"

# 停止服务
systemctl stop tableau-monitor

# 重启服务
systemctl restart tableau-monitor
```

## 工作原理

1. 通过 Tableau REST API (TSC) 查询最近 24 小时的 Flow Runs
2. 筛选未完成（`completed_at` 为空）且运行时间 ≥ 阈值的任务
3. 调用 `server.jobs.cancel()` 取消对应的 Background Job
4. 等待 10 分钟后重复检查

## 环境要求

- Python 3.8+
- Tableau Server 2024.2+ (API 3.10+)
- Personal Access Token

## License

MIT
