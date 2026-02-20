# 📊 Portfolio Monitor

**股票监控工作台** — 美股 + A股实时行情，多档位目标价告警（Telegram 推送），持仓 & 交易记录管理。

[![Docker Build](https://github.com/YOUR_USERNAME/portfolio-monitor/actions/workflows/docker-build.yml/badge.svg)](https://github.com/YOUR_USERNAME/portfolio-monitor/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## ✨ 功能特性

- **📈 实时行情** — 美股 + A股，自动刷新（盘中 30s / 盘外 5min）
- **🔔 多档位告警** — 每只股票支持主档 + 多个子档（买入 / 卖出 / 止损），Telegram 即时推送
- **💰 持仓管理** — 自动计算成本、盈亏、收益率，按市场分组，ECharts 图表可视化
- **📝 交易记录** — 增删查改、筛选、CSV 导出
- **💵 现金账户** — USD / CNY 现金管理，交易自动联动
- **🎨 双主题** — 暗色 / 明色主题，跟随系统设置，一键切换
- **📱 响应式** — 桌面端 & 移动端完美适配

## 📸 界面预览

### 暗色主题

| 看板 | 持仓管理 |
|:---:|:---:|
| ![Dashboard Dark](screenshots/01-dashboard-dark.png) | ![Portfolio Dark](screenshots/02-portfolio-dark.png) |

| 监控预警 | 告警历史 |
|:---:|:---:|
| ![Alerts Dark](screenshots/03-alerts-dark.png) | ![History Dark](screenshots/04-history-dark.png) |

| 交易记录 | 现金账户 |
|:---:|:---:|
| ![Transactions Dark](screenshots/05-transactions-dark.png) | ![Cash Dark](screenshots/06-cash-dark.png) |

### 明色主题

| 看板 | 持仓管理 | 告警 |
|:---:|:---:|:---:|
| ![Dashboard Light](screenshots/07-dashboard-light.png) | ![Portfolio Light](screenshots/08-portfolio-light.png) | ![Alerts Light](screenshots/09-alerts-light.png) |

### 移动端

| 看板 | 持仓 | 告警 | 交易 |
|:---:|:---:|:---:|:---:|
| ![Mobile Dashboard](screenshots/mobile-dashboard.png) | ![Mobile Portfolio](screenshots/mobile-portfolio.png) | ![Mobile Alerts](screenshots/mobile-alerts.png) | ![Mobile Transactions](screenshots/mobile-transactions.png) |

## 🚀 快速部署（Docker）

推荐使用 Docker 一键部署，3 步搞定：

```bash
# 1. 复制配置文件
cp config.example.yaml config.yaml

# 2. 编辑配置，填入你的 Telegram Bot Token 和 Chat ID
vim config.yaml

# 3. 启动！
docker compose up -d
```

打开浏览器访问 **http://localhost:8802** 🎉

### 常用命令

```bash
docker compose logs -f          # 查看日志
docker compose restart           # 重启
docker compose down              # 停止
docker compose up -d --build     # 重新构建并启动
```

## 🛠️ 本地开发

```bash
# 后端
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt

# 前端
cd frontend
npm install
npm run build
cd ..

# 启动
bash start.sh      # 前台运行（开发调试）
bash run.sh        # 后台运行
bash stop.sh       # 停止后台进程
```

前端开发模式（热更新）：

```bash
cd frontend
npm run dev        # Vite dev server → localhost:5173
                   # 自动代理 /api 到后端
```

## ⚙️ 配置说明

配置文件为 `config.yaml`，参考 [`config.example.yaml`](config.example.yaml)：

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `server.host` | 监听地址 | `0.0.0.0` |
| `server.port` | 监听端口 | `8802` |
| `database.url` | SQLite 数据库路径 | `sqlite:///data/portfolio.db` |
| `monitor.interval_active` | 盘中刷新间隔（秒） | `30` |
| `monitor.interval_idle` | 盘外刷新间隔（秒） | `300` |
| `monitor.change_alert_pct` | 涨跌幅告警阈值（%） | `5.0` |
| `telegram.bot_token` | Telegram Bot Token（从 @BotFather 获取） | — |
| `telegram.chat_id` | 推送目标（群组 ID 为负数，个人 ID 为正数） | — |
| `telegram.thread_id` | Forum 群组话题 ID（非 Forum 群可删除） | — |
| `alert.cooldown` | 同一告警冷却时间（秒） | `3600` |
| `watchlist` | 默认监控标的列表（也可通过 Web 界面管理） | — |

## 📡 API 文档

后端基于 FastAPI，自带交互式 API 文档：

- **Swagger UI**：`http://localhost:8802/docs`
- **ReDoc**：`http://localhost:8802/redoc`

### 主要端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/dashboard` | GET | 看板聚合数据 |
| `/api/portfolio` | GET | 当前持仓 |
| `/api/transactions` | GET / POST | 交易记录 |
| `/api/transactions/{id}` | GET / DELETE | 单条交易 |
| `/api/transactions/export/csv` | GET | 导出 CSV |
| `/api/alerts` | GET / POST | 告警设置 |
| `/api/alerts/grouped` | GET | 告警按股票分组 |
| `/api/alerts/{id}` | PUT / DELETE | 修改 / 删除告警 |
| `/api/alerts/test-send` | POST | 测试 Telegram 推送 |
| `/api/alerts/history` | GET | 告警历史 |
| `/api/watchlist` | GET / POST | 监控列表 |
| `/api/prices` | GET | 缓存行情 |
| `/api/cash` | GET | 现金账户 |
| `/api/cash/adjust` | POST | 调整现金 |
| `/health` | GET | 健康检查 |

## 🏗️ 技术栈

| 组件 | 技术 |
|------|------|
| 后端 | Python 3.11 + FastAPI + SQLAlchemy + APScheduler |
| 前端 | Vue 3 + Vite + ECharts 5 |
| 数据库 | SQLite |
| 行情数据 | Yahoo Finance（美股）/ AKShare（A股） |
| 告警推送 | Telegram Bot API |
| 容器化 | Docker 多阶段构建 |

## 📁 项目结构

```
portfolio-monitor/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口 + 后台调度
│   │   ├── models.py            # ORM 模型 + Pydantic Schema
│   │   ├── database.py          # SQLite 连接
│   │   ├── services/            # 业务逻辑
│   │   └── routers/             # API 路由
│   └── requirements.txt
├── frontend/
│   ├── src/                     # Vue 源码
│   ├── package.json
│   └── vite.config.js
├── skill/                       # OpenClaw AI Agent skill
│   ├── SKILL.md                 # Skill 描述与安装
│   ├── portfolio                # CLI 可执行文件
│   ├── skill.json               # Skill 元数据
│   └── README.md                # 详细文档
├── screenshots/                 # 界面截图
├── data/                        # 运行时数据（.gitignore）
├── config.example.yaml          # 配置模板
├── docker-compose.yml           # Docker 编排
├── Dockerfile                   # 多阶段构建
├── start.sh / run.sh / stop.sh  # 启动脚本
├── CONTRIBUTING.md              # 贡献指南
└── LICENSE                      # MIT License
```

## 🤖 AI Agent 集成

本项目附带 [OpenClaw](https://github.com/openclaw/openclaw) Agent Skill，让 AI 助手可以直接查询持仓、记录交易。

**安装 skill：**

```bash
cp -rp skill/ ~/.openclaw/skills/stock-portfolio/
chmod +x ~/.openclaw/skills/stock-portfolio/portfolio
```

**AI 可执行的操作：**

```bash
portfolio summary      # 资产总览
portfolio holdings     # 持仓及盈亏
portfolio buy TME 500 15.50   # 记录买入
portfolio sell BABA 50 200.00 # 记录卖出
portfolio cash         # 现金余额
```

详见 [`skill/SKILL.md`](skill/SKILL.md)。

## 📄 License

[MIT License](LICENSE) © kdp
