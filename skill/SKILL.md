# stock-portfolio skill

通过 CLI 与 portfolio-monitor 服务交互，管理股票持仓、现金账户、交易记录和告警。

## 安装

> 前提：portfolio-monitor 服务已运行（见根目录 README 的 Docker 部署）

```bash
# 复制 skill 到 OpenClaw
cp -rp skill/ ~/.openclaw/skills/stock-portfolio/

# 确认 CLI 有执行权限
chmod +x ~/.openclaw/skills/stock-portfolio/portfolio
```

## 配置

默认连接 `http://localhost:8802`，可通过环境变量覆盖：

```bash
export PORTFOLIO_API_URL="http://your-server:8802"
```

## 主要命令

| 命令 | 说明 |
|------|------|
| `portfolio summary` | 资产总览（持仓 + 现金） |
| `portfolio holdings` | 当前持仓及盈亏 |
| `portfolio cash` | 现金账户余额 |
| `portfolio buy SYMBOL SHARES PRICE` | 记录买入 |
| `portfolio sell SYMBOL SHARES PRICE` | 记录卖出 |
| `portfolio transactions` | 交易历史 |
| `portfolio watch` | 监控列表 |

## 示例

```bash
# 查持仓
portfolio holdings

# 记录买入 TME 500股 @ $15.50
portfolio buy TME 500 15.50 "建仓"

# 记录卖出
portfolio sell BABA 50 200.00 "止盈"

# 查现金
portfolio cash
```

## 详细文档

见 `README.md`。
