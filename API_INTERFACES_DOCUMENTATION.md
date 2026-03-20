# Portfolio Monitor 项目 API 接口完整文档

## 📋 目录
- [概述](#概述)
- [技术栈](#技术栈)
- [认证机制](#认证机制)
- [接口分类详解](#接口分类详解)
  - [1. Dashboard 接口](#1-dashboard-接口)
  - [2. Portfolio 接口](#2-portfolio-接口)
  - [3. Transactions 接口](#3-transactions-接口)
  - [4. Alerts 接口](#4-alerts-接口)
  - [5. Prices 接口](#5-prices-接口)
  - [6. Cash 接口](#6-cash-接口)
  - [7. Watchlist 接口](#7-watchlist-接口)
  - [8. Quant 接口](#8-quant-接口)
  - [9. Earnings 接口](#9-earnings-接口)
  - [10. Snapshots 接口](#10-snapshots-接口)
  - [11. Macro 接口](#11-macro-接口)
  - [12. Market 数据接口](#12-market-数据接口)
- [后台任务](#后台任务)
- [数据模型](#数据模型)

---

## 概述

这是一个基于 FastAPI 开发的投资组合监控系统，提供以下主要功能：
- 投资组合管理和盈亏计算
- 交易记录管理（自动关联现金流）
- 多级价格预警设置
- 实时股价获取和缓存
- 资产净值历史追踪
- 财报分析和量化信号
- 宏观经济指标监控

### 核心特性
✅ 支持美股和A股（通过 `.SS` 和 `.SZ` 后缀区分）  
✅ 自动汇率转换（USD ↔ CNY）  
✅ Telegram 告警推送集成  
✅ 定时任务调度（价格更新、每日快照、量化信号刷新）  
✅ 浏览器伪装避免反爬限制（curl_cffi）

---

## 技术栈

| 层次 | 技术 |
|------|------|
| Web框架 | FastAPI |
| 数据库 | SQLAlchemy + SQLite (WAL模式) |
| 数据源 | Yahoo Finance API (via curl_cffi)、Financial Datasets API (可选) |
| 任务调度 | APScheduler (BackgroundScheduler) |
| 认证 | Telegram WebApp InitData 签名验证 |

---

## 认证机制

### 中间件：[`TelegramAuthMiddleware`](backend/app/main.py:258)

该中间件拦截所有 `/api/*` 请求进行身份验证：

#### 白名单路径（无需认证）
- `/health`, `/api/health`
- `/assets/**` （静态资源）
- 非 `/api` 开头的路径

#### 本地开发豁免
当 Host 为 `localhost`、`127.0.0.1` 或 IP 地址直连时跳过验证。

#### 验证逻辑
1. 从请求头 `X-Telegram-Init-Data` 获取初始化数据
2. 使用 HMAC-SHA256 验证签名（密钥来自 `config.yaml` 中的 `telegram.bot_token`）
3. 验证成功则放行，否则返回 403 错误

**相关函数**: [`_verify_telegram_init_data()`](backend/app/main.py:238)

---

## 接口分类详解

### 1. Dashboard 接口

**路由前缀**: `/api/dashboard`  
**文件位置**: [`backend/app/routers/dashboard.py`](backend/app/routers/dashboard.py)

#### GET `/api/dashboard`
聚合仪表板数据，一次性返回多个维度的信息。

**响应结构** (`DashboardOut`):
```json
{
  "prices": [...],                    // 所有缓存的股价列表
  "portfolio": {...},                  // 当前持仓汇总
  "cash_accounts": [...],              // 各币种账户余额
  "total_assets": {...},               // 总资产统计（统一换算成USD）
  "recent_alerts": [...],              // 最近10条告警历史
  "recent_transactions": [...]         // 最近10笔交易记录
}
```

**实现要点**:
- 批量查询优化：一次查询所有持仓的价格缓存，避免N+1问题
- 汇率处理：调用 [`get_usd_to_cny()`](backend/app/services/exchange_service.py:17) 进行实时汇率转换
- 分离中美股市价值分别计算后再合并

---

### 2. Portfolio 接口

**路由前缀**: `/api/portfolio`  
**文件位置**: [`backend/app/routers/portfolio.py`](backend/app/routers/portfolio.py)

#### GET `/api/portfolio`
获取当前持仓详情及盈亏统计。

**响应结构** (`PortfolioOut`):
```json
{
  "holdings": [
    {
      "symbol": "AAPL",
      "name": "Apple Inc.",
      "shares": 100.0,
      "avg_cost": 150.0,
      "current_price": 175.0,
      "market_value": 17500.0,
      "unrealized_pnl": 2500.0,
      "pnl_pct": 16.67,
      "currency": "USD",
      "market_value_usd": 17500.0,
      "unrealized_pnl_usd": 2500.0
    }
  ],
  "total_cost": 15000.0,
  "total_value": 17500.0,
  "total_pnl": 2500.0,
  "total_pnl_pct": 16.67
}
```

**核心算法** ([`get_holdings()`](backend/app/services/portfolio_service.py:22)):
1. 按时间顺序遍历所有交易记录
2. 对于每支股票维护累计持股数量和总成本
3. 卖出时按比例减少成本基础
4. 结合最新市价计算未实现盈亏

---

### 3. Transactions 接口

**路由前缀**: `/api/transactions`  
**文件位置**: [`backend/app/routers/transactions.py`](backend/app/routers/transactions.py)

#### GET `/api/transactions`
查询交易记录，支持多条件筛选。

**查询参数**:
- `symbol`: 股票代码过滤
- `action`: 操作类型过滤 (`buy`/`sell`)
- `start_date`: 开始日期
- `end_date`: 结束日期
- `limit`: 返回数量上限（最大500）
- `offset`: 分页偏移量

#### POST `/api/transactions`
添加新交易记录，同时自动调整对应币种的现金余额。

**请求体** (`TransactionCreate`):
```json
{
  "symbol": "AAPL",
  "name": "Apple Inc.",
  "action": "buy",
  "price": 150.0,
  "shares": 100,
  "fee": 5.0,
  "notes": "建仓",
  "date": "2024-01-15T10:00:00Z"
}
```

**业务规则**:
- 买入：扣除 `(价格 × 数量 + 手续费)`
- 卖出：增加 `(价格 × 数量 - 手续费)`
- 如果现金不足会抛出异常阻止交易创建
- 自动根据股票代码确定币种（`.SS`/`.SZ` 为人民币，其余为美元）

**相关函数**: [`update_cash_for_transaction()`](backend/app/routers/transactions.py:36)

#### GET `/api/transactions/{tx_id}`
查询单个交易详情。

#### DELETE `/api/transactions/{tx_id}`
删除交易记录，并回滚对应的现金变动。

#### GET `/api/transactions/export/csv`
导出所有交易记录为CSV格式下载。

---

### 4. Alerts 接口

**路由前缀**: `/api/alerts`  
**文件位置**: [`backend/app/routers/alerts.py`](backend/app/routers/alerts.py)

#### GET `/api/alerts`
获取所有告警设置的扁平列表。

#### GET `/api/alerts/grouped`
获取分组后的告警列表，包含当前价格信息。

**响应示例**:
```json
[
  {
    "symbol": "AAPL",
    "name": "苹果",
    "market": "us",
    "current_price": 175.0,
    "change_pct": 2.5,
    "primary": {
      "id": 1,
      "symbol": "AAPL",
      "target_buy": 150.0,
      "target_sell": 200.0,
      ...
    },
    "levels": [
      {
        "id": 2,
        "symbol": "AAPL",
        "is_primary": false,
        "label": "$140加仓位",
        "target_buy": 140.0,
        ...
      }
    ]
  }
]
```

**多级告警设计**:
- 主级别告警 (`is_primary=true`)：一支股票只有一个
- 子级别告警 (`is_primary=false`)：可以有多个，用于不同价位的目标设定
- 共享同一个真实股票代码和价格

#### POST `/api/alerts`
创建新的告警设置。

**特殊逻辑**:
- 如果是主级别且同一符号的主告警已存在，则更新而非新建
- 子级别总是新增一条记录

**请求体** (`AlertSettingCreate`):
```json
{
  "symbol": "AAPL",
  "name": "苹果",
  "market": "us",
  "target_buy": 150.0,
  "target_sell": 200.0,
  "stop_loss": 130.0,
  "enabled": true,
  "is_primary": true,
  "label": "首次建仓",
  "amount": "$15,000"
}
```

#### PUT `/api/alerts/{alert_id}`
更新指定ID的告警设置。

#### DELETE `/api/alerts/{alert_id}`
删除指定的告警设置。

#### POST `/api/alerts/test-send`
发送测试告警到Telegram，用于验证配置是否正确。

#### GET `/api/alerts/history`
查询告警触发历史。

**查询参数**:
- `symbol`: 按股票代码过滤
- `limit`: 返回数量（最大200）

---

### 5. Prices 接口

**路由前缀**: `/api/prices`  
**文件位置**: [`backend/app/routers/prices.py`](backend/app/routers/prices.py)

#### GET `/api/prices`
获取所有缓存的股价数据。

#### GET `/api/prices/quick`
轻量级价格快照，仅返回关键字段。

**响应字段**:
- `symbol`
- `price`
- `change`
- `change_pct`
- `updated_at`

#### GET `/api/prices/{symbol}`
获取单个股票的最新价格。

**智能降级策略**:
1. 先从本地缓存查找
2. 缓存不存在时调用 [`fetch_price()`](backend/app/services/price_service.py:91) 实时抓取
3. 更新缓存后返回

---

### 6. Cash 接口

**路由前缀**: `/api/cash`  
**文件位置**: [`backend/app/routers/cash.py`](backend/app/routers/cash.py)

#### GET `/api/cash`
获取所有现金账户余额列表。

支持的币种：USD, CNY

#### GET `/api/cash/logs`
查询资金调整历史记录。

**查询参数**:
- `currency`: 按币种过滤
- `limit`: 返回数量（默认50）

#### GET `/api/cash/{currency}`
获取指定币种的账户余额。

#### POST `/api/cash/adjust`
手动调整现金余额（存款或提款）。

**请求体** (`CashAccountUpdate`):
```json
{
  "currency": "USD",
  "amount": 1000.0,
  "notes": "追加本金"
}
```

**规则**:
- `amount > 0`: 存入
- `amount < 0`: 取出
- 会校验余额充足性
- 同时生成操作日志记录

#### POST `/api/cash/init`
初始化默认现金账户（如果尚未创建）。

---

### 7. Watchlist 接口

**路由前缀**: `/api/watchlist`  
**文件位置**: [`backend/app/routers/watchlist.py`](backend/app/routers/watchlist.py)

> 这是针对 Skill 功能设计的便捷封装，底层复用了 AlertSetting 表。

#### GET `/api/watchlist`
获取观察列表（仅返回主级别的告警项，附带当前价格）。

#### POST `/api/watchlist`
向观察列表添加股票。

**行为**:
- 如果股票已在列表中，则更新现有记录
- 否则创建新记录

#### PUT `/api/watchlist/{symbol}`
更新观察列表中的某一项。

**特点**:
- 仅更新请求体中明确提供的字段
- 可以显式传 `null` 来清除某个字段的值（如 `"target_buy": null`）

#### DELETE `/api/watchlist/{item_id}`
通过ID删除观察项。

#### DELETE `/api/watchlist/symbol/{symbol}`
通过股票代码删除观察项。

---

### 8. Quant 接口

**路由前缀**: `/api/quant`  
**文件位置**: [`backend/app/routers/quant.py`](backend/app/routers/quant.py)

#### GET `/api/quant/signals`
获取所有股票的最新量化基本面信号摘要。

**响应结构** (`QuantSignalSummary`):
```json
[
  {
    "symbol": "AAPL",
    "name": "苹果",
    "market": "us",
    "metrics": {
      "pe_ttm": {"value": 28.5, "percentile": 65},
      "pb": {"value": 45.2, "percentile": 70},
      "roe": {"value": 0.35, "percentile": 80},
      "gross_margin": {"value": 0.42, "percentile": 75},
      "revenue_growth": {"value": 0.08, "percentile": 60}
    },
    "score": 68.5
  }
]
```

**综合评分算法** ([`compute_composite_score()`](backend/app/routers/quant.py:41)):
- 权重分配：PE-TTM(35%), PB(25%), ROE(15%), 毛利率(10%), 收入增长(15%)
- 对于PE/PB：百分位数越低越好（便宜）
- 对于ROE/毛利率/收入增长：百分位数越高越好（质量好）
- 最终得分范围 0-100，分数越低代表性价比越高

#### GET `/api/quant/signals/{symbol}`
获取特定股票的历史信号数据。

**查询参数**:
- `metric`: 可选，按指标类型过滤（`pe_ttm`/`pb`/`roe`/`gross_margin`/`revenue_growth`）

#### POST `/api/quant/refresh`
手动触发量化信号数据的批量刷新。

**执行流程**:
1. 调用脚本 [`fetch_fundamentals.py::refresh_all_signals()`](backend/scripts/fetch_fundamentals.py)
2. 同步等待完成并返回更新的信号数量

---

### 9. Earnings 接口

**路由前缀**: `/api/earnings`  
**文件位置**: [`backend/app/routers/earnings.py`](backend/app/routers/earnings.py)

#### GET `/api/earnings/upcoming`
获取即将发布的财报日程（未来30-90天内）。

**数据来源**: Yahoo Finance Quote Summary API  
**缓存策略**: 内存缓存5分钟

**响应字段**:
- `symbol`, `name`
- `report_date`: 发布日期
- `days_until`: 还有几天
- `estimate_eps`: 盈利预期
- `estimate_revenue`: 营收预期

#### GET `/api/earnings/recent`
获取最近的财报实际表现（超预期/不及预期）。

**显示内容**:
- 最近4个季度的EPS对比
- Beat/Miss 判断标准：实际 vs 预估

#### GET `/api/earnings/analysis`
获取「老李」的人工财报分析记录。

**响应内容包括**:
- EPS和营收的实际值vs预估值
- Surprise百分比
- 公司给出的下季度指引
- 老李的综合判断（beat/met/miss）
- 短期观点（bullish/bearish/neutral）
- 详细分析文本（Markdown格式）
- 持仓建议
- 财报后股价反应幅度

#### POST `/api/earnings/analysis`
插入或更新一份财报分析记录。

**Upsert逻辑**: 按 `symbol + fiscal_quarter` 组合键去重

---

### 10. Snapshots 接口

**路由前缀**: `/api/snapshots`  
**文件位置**: [`backend/app/routers/snapshots.py`](backend/app/routers/snapshots.py)

#### GET `/api/snapshots/history`
获取过去N天的资产净值变化曲线。

**查询参数**:
- `days`: 天数范围（1-365，默认90）

**响应示例**:
```json
[
  {
    "date": "2024-01-15",
    "total_assets_usd": 50000.0,
    "stock_value_usd": 45000.0,
    "cash_usd": 3000.0,
    "cash_cny": 1400.0,
    "details": "AAPL:17500; MSFT:15000; GOOGL:12500"
  }
]
```

#### POST `/api/snapshots/take`
手动触发一次资产快照拍摄。

**定时任务**: 每天16:05 CST自动执行（见 [`lifespan()`](backend/app/main.py:175)）

**快照内容** ([`take_daily_snapshot()`](backend/app/routers/snapshots.py:60)):
- 股票市值（分USD和CNY）
- 现金余额
- 换算成USD的总资产
- 持仓明细字符串

---

### 11. Macro 接口

**路由前缀**: `/api/macro`  
**文件位置**: [`backend/app/routers/macro.py`](backend/app/routers/macro.py)

#### GET `/api/macro`
获取宏观经济指标的实时数值。

**监控标的**:
- ^VIX: VIX恐慌指数
- ^TNX: 美国10年期国债收益率
- DX-Y.NYB: 美元指数(DXY)
- ^GSPC: 标普500(SPX)
- ^IXIC: 纳斯达克(NASDAQ)

**响应结构**:
```json
[
  {
    "symbol": "^VIX",
    "name": "VIX 恐慌指数",
    "short_name": "VIX",
    "price": 18.5,
    "change": -0.3,
    "change_pct": -1.6
  }
]
```

**缓存策略**: 内存缓存60秒

---

### 12. Market 数据接口

**路由前缀**: `/api/market`  
**文件位置**: [`backend/app/routers/market.py`](backend/app/routers/market.py)

这是一组丰富的金融数据查询接口，采用双数据源策略：
1. **首选**: Financial Datasets API（需环境变量 `FINANCIAL_DATASETS_API_KEY`）
2. **备选**: yfinance（免费但可能被限流）

所有接口都有统一的内存缓存（TTL=5分钟），并通过装饰器 [`@cached()`](backend/app/routers/market.py:45) 实现。

#### GET `/api/market/price/{symbol}`
实时价格快照。

**响应字段**:
- `price`, `previous_close`, `change`, `change_pct`
- `volume`, `market_cap`
- `open`, `high`, `low`
- `currency`, `source`

#### GET `/api/market/ratios/{symbol}`
估值比率指标。

**包括**:
- PE-TTM, Forward PE, PB, PS, PEG
- EPS, Forward EPS
- Dividend Yield
- Profit Margin, Operating Margin
- Return on Equity/Assets
- Beta, 52周高低点

#### GET `/api/market/income/{symbol}?period=annual|quarterly`
财务报表之利润表。

**周期选项**: annual（年度）/ quarterly（季度）  
**返回最近4期的数据**

**标准化字段**:
- `revenue`, `cost_of_revenue`, `gross_profit`
- `operating_income`, `net_income`, `EBITDA`
- `EPS basic/diluted`
- R&D支出, 利息费用

#### GET `/api/market/balance/{symbol}?period=...&limit=4`
资产负债表。

**关键字段**:
- `total_assets`, `total_liabilities`, `shareholders_equity`
- `cash`, `total_debt`
- `book_value_per_share`

#### GET `/api/market/cashflow/{symbol}?period=...&limit=4`
现金流量表。

**关键字段**:
- `operating_cash_flow`
- `capital_expenditure`
- `free_cash_flow` (= OCF + CapEx)
- `net_income`

#### GET `/api/market/estimates/{symbol}?period=...`
分析师预期数据。

**包括**:
- 目标价区间（最低/最高/平均/中位数）
- 未来几年的盈利预测
- 营收预测
- 机构推荐分布

#### GET `/api/market/news/{symbol}?limit=10`
相关新闻资讯。

**返回字段**:
- 标题、描述、链接URL
- 来源媒体
- 发布时间

#### GET `/api/market/company/{symbol}`
公司基本信息。

**包括**:
- 名称、所属行业板块
- 所在国家、全职员工数
- 业务简介（截断至300字符）
- 官方网址、交易所

#### GET `/api/market/insiders/{symbol}?limit=10`
内部人交易记录。

**显示**:
- 高管姓名、职位
- 交易类型描述
- 交易股数和价值

#### GET `/api/market/segments/{symbol}`
营收细分数据。

**维度**:
- 按产品类别划分的收入
- 按地理区域划分的收入

#### GET `/api/market/crypto/{symbol}`
加密货币价格查询。

**用法**: 符号格式如 `BTC-USD`, `ETH-USD`

#### GET `/api/market/prices/{symbol}?start=&end=&interval=1d`
历史OHLCV价格序列。

**间隔选项**: `1d`(日线)|`1wk`(周线)|`1mo`(月线)|`5m`|`15m`|`30m`|`1h`

---

## 后台任务

在 [`main.py:lifespan()`](backend/app/main.py:144) 启动时注册三个定时任务：

### 1. 价格更新循环
- **频率**: 每60秒（可通过 `config.monitor.interval_active` 配置）
- **功能**: 
  - 获取所有启用的告警股票代码
  - 批量拉取最新价格（去重相同代码）
  - 更新 [`PriceCache`](backend/app/models.py:97) 表
  - 调用 [`check_alerts()`](backend/app/services/alert_service.py:99) 检测告警触发

**核心函数**: [`update_prices()`](backend/app/main.py:54)

### 2. 量化信号刷新
- **时间**: 每天16:00 CST (UTC 08:00)
- **功能**: 执行 [`fetch_fundamentals.py::refresh_all_signals()`](backend/scripts/fetch_fundamentals.py)，更新所有股票的基本面指标和历史百分位

### 3. 每日资产快照
- **时间**: 每天16:05 CST (UTC 08:05)
- **功能**: 调用 [`take_daily_snapshot()`](backend/app/routers/snapshots.py:60) 记录当日净资产

---

## 数据模型

### 核心ORM实体

| 表名 | 用途 | 关键字段 |
|-----|------|----------|
| `transactions` | 交易记录 | id, symbol, action, price, shares, amount, fee, date |
| `alert_settings` | 告警设置 | symbol, target_buy/target_sell/stop_loss, enabled, is_primary, label, amount |
| `alert_history` | 告警历史 | symbol, alert_type, message, price, triggered_at, sent |
| `price_cache` | 价格缓存 | symbol, price, previous_close, change, change_pct, volume, currency |
| `quant_signals` | 量化信号 | symbol, metric(pe_ttm/pb/roe...), value, percentile, date |
| `asset_snapshots` | 资产快照 | date, total_assets_usd, stock_value_usd, cash_usd, cash_cny |
| `cash_accounts` | 现金账户 | currency(PK), balance |
| `cash_logs` | 资金流水 | currency, amount(+/-), balance_after, reason |
| `earnings_analysis` | 财报分析 | symbol, fiscal_quarter, eps_actual/estimate, verdict, analysis |

### 枚举类型

```python
class TradeAction(Enum):
    buy = "buy"
    sell = "sell"

class MarketType(Enum):
    us = "us"
    cn = "cn"

class CurrencyType(Enum):
    usd = "USD"
    cny = "CNY"
```

---

## 附录：关键技术实现细节

### 1. 价格抓取抗反爬方案

使用 [`curl_cffi`](backend/app/services/price_service.py:14) 库模拟Chrome浏览器TLS指纹：

```python
_session = cffi_requests.Session(impersonate="chrome")
```

这能有效绕过Yahoo Finance的反机器人检测。

### 2. 并发批处理

[`fetch_prices_batch()`](backend/app/services/price_service.py:101) 采用线程池并发抓取：

- 每批次3个并发请求
- 批次之间延迟1秒避免速率限制
- 异常隔离不影响其他股票

### 3. 汇率服务集中化

[`get_usd_to_cny()`](backend/app/services/exchange_service.py:17) 提供带缓存的汇率查询：

- 默认汇率: 7.2
- 缓存时长: 5分钟
- 失败时静默fallback不中断业务

### 4. 告警冷却机制

双重防护防止刷屏：

1. **内存级冷却**: `_last_alert` 字典记录最后告警时间（1小时）
2. **数据库级冷却**: `alert_setting.last_triggered_at` 字段（24小时）

只有两者都满足才真正发送通知。

### 5. 数据库性能优化

SQLite启用WAL模式提升并发读写能力：

```python
@event.listens_for(engine, "connect")
def set_wal_mode(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
```

---

## 文档版本

- **生成时间**: 2026-03-20
- **项目版本**: 1.0.0
- **覆盖范围**: 全部12个API模块共约50个端点