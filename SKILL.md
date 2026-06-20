---
name: stoke
description: |
  🔥 免费 A 股数据层 — 零 API Key、零注册、零付费，开箱即用。
  覆盖行情/研报/信号/新闻/基础数据/公告 6 大层面，40+ 个接口，6 源自动备份。
  当用户提到"股票"、"行情"、"K线"、"涨停"、"强势股"、"研报"、"PE"、"PB"、"估值"、
  "个股新闻"、"公告"、"题材"、"概念板块"、"行业板块"、"财联社"、"电报"、"A股"时触发。
  也用于查某只股票的实时价格、历史K线、财务研报、新闻公告等。
homepage: https://github.com/birdilsss-byte/stoke
platforms: [macos, windows]
metadata:
  openclaw:
    emoji: 🔥
    requires: {}
    install:
      uv:
        - akshare
        - baostock
        - beautifulsoup4
        - efinance
        - mootdx
        - pandas
        - requests
  hermes:
    tags: [stock, finance, a-share, market-data, quant, free, zero-api-key]
    category: finance
    requires:
      bins:
        - python3
        - uv
    install:
      uv: [akshare, baostock, beautifulsoup4, efinance, mootdx, pandas, requests]
    postinstall: "cd $STOKE_HOME && uv sync --no-cache --python-preference only-managed && uv run python3 -c \"from stoke import Stoke; print('OK')\""
---

# Stoke — A股数据层技能

纯数据获取层，**零 API Key 依赖**，所有数据源免注册。兼容 **Claude Code** · **OpenClaw** · **Hermes**。

## 🔧 安装（macOS / Windows 通用）

**1. 安装 uv（如果还没有）：**
   macOS: `brew install uv` | Windows: `winget install astral.uv`
   或官网脚本：https://docs.astral.sh/uv/getting-started/installation/

**2. 克隆项目：**

```bash
git clone https://github.com/birdilsss-byte/stoke.git ~/stoke
cd ~/stoke && uv sync
```

**3. 设置 STOKE_HOME 环境变量：**

| 系统 | 命令 |
|------|------|
| macOS | `echo 'export STOKE_HOME=~/stoke' >> ~/.bashrc` |
| Windows PowerShell | `[Environment]::SetEnvironmentVariable('STOKE_HOME', "$env:USERPROFILE\stoke", 'User')` |
| Windows CMD | `setx STOKE_HOME "%USERPROFILE%\stoke"` |

环境变量只需设置一次，重启终端后生效。也可手动 `export` 当前会话立即使用。

**4. 验证安装：**

```bash
cd "$STOKE_HOME" && uv run python3 -c "from stoke import Stoke; print('安装成功')"
```

---

## OpenClaw 安装

### 方式一：zip 压缩包（推荐）

1. 下载 `stoke-skill.zip`
2. 在 OpenClaw 中导入：设置 → Skills → Import → 选择 zip 文件
3. OpenClaw 自动解压、安装依赖、验证

### 方式二：Git 克隆

```bash
git clone https://github.com/birdilsss-byte/stoke.git ~/stoke
cd ~/stoke && uv sync
export STOKE_HOME=~/stoke
```

OpenClaw 会自动读取 SKILL.md 中的 `metadata.openclaw` 配置。

---

## Hermes 安装

### 方式一：zip 压缩包（推荐）

1. 下载 `stoke-skill.zip`
2. 解压到 Hermes skills 目录：
   ```bash
   unzip stoke-skill.zip -d ~/.hermes/skills/stoke/
   cd ~/.hermes/skills/stoke && uv sync
   ```
3. 重启 Hermes 或执行 `hermes reload-skills`

### 方式二：Hermes 命令行安装

```bash
hermes skill install https://github.com/birdilsss-byte/stoke/releases/latest/download/stoke-skill.zip
```

Hermes 会自动执行 `postinstall`：`cd $STOKE_HOME && uv sync && 验证导入`。

### 手动验证

```bash
cd ~/.hermes/skills/stoke && uv run python3 -c "from stoke import Stoke; print('OK')"
```

### 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `timeout: command not found` | macOS 默认无 GNU timeout | `brew install coreutils` |
| `numpy` 缺失 | 依赖未正确安装 | `uv sync` 会自动拉取，确认网络通畅 |
| Python 路径异常 | Hermes 沙盒环境隔离 | 用 `export STOKE_HOME=~/stoke` 指定路径 |
| `ModuleNotFoundError: stoke` | 包未安装 | `cd "$STOKE_HOME" && uv sync` |

---

## ⚠️ 限流铁律

| 数据源 | 最小间隔 | 说明 |
|--------|---------|------|
| mootdx | 不限流 | TCP 协议，本地解析 |
| akshare | **5 秒** | 东财/同花顺/巨潮，必须遵守 |
| legulegu | **1 秒** | 乐咕乐股 PE/PB，纯 requests 直连 |
| baostock | **1 秒** | 证券宝 HTTP，复权K线+财报+估值 |
| efinance | **0.5 秒** | 极速K线/龙虎榜/资金流/股东数据 |
| 腾讯直连 | **0.3 秒** | qt.gtimg.cn 实时行情+K线，毫秒级 |

**同一 Source 实例内调用自动限流。跨实例（akshare + 腾讯）需手动停顿。**

---

## 数据源速查

### 📈 mootdx（通达信 TCP）— 行情层

```python
from stoke.sources.mootdx_source import MootdxSource
m = MootdxSource()
```

| 方法 | 说明 | 示例 |
|------|------|------|
| `health_check()` | 连通性 | `m.health_check()` |
| `get_kline(symbol)` | 日K线，800条 | `m.get_kline("000001")` |
| `get_realtime(symbols)` | 实时行情（5档盘口） | `m.get_realtime(["000001","600000"])` |
| `get_stock_list()` | 全市场股票列表（27046只） | `m.get_stock_list()` |
| `get_f10(symbol)` | F10财务快照 | `m.get_f10("000001")` |

### 📰 akshare（东财/同花顺/巨潮/财联社）— 新闻+研报+公告+信号

```python
from stoke.sources.akshare_source import AKShareSource
a = AKShareSource()
```

| 方法 | 说明 | 层面 |
|------|------|------|
| `get_news(symbol)` | 个股新闻 | 新闻 |
| `get_cls_telegraph()` | 财联社电报（分钟级） | 新闻 |
| `get_research_report(symbol)` | 东财研报（含PDF+盈利预测） | 研报 |
| `get_announcements(symbol)` | 巨潮公告 | 公告 |
| `get_limit_up_pool(date)` | 涨停板 | 信号 |
| `get_strong_stocks(date)` | **强势涨停（含"入选理由"题材归因）** | 信号 |
| `get_concept_list()` | 概念板块列表 | 信号 |
| `get_industry_list()` | 行业板块列表 | 信号 |

### 💹 legulegu（乐咕乐股）— 估值层（纯 requests，零 akshare 依赖）

```python
from stoke.sources.legulegu_source import LeguleguSource
l = LeguleguSource()
```

| 方法 | 说明 | 示例 |
|------|------|------|
| `get_index_pe(name)` | 指数PE历史 | `l.get_index_pe("上证50")` |
| `get_market_pb()` | 全市场PB历史 | `l.get_market_pb()` |

### ⚡ tencent_direct（腾讯直连 qt.gtimg.cn）— 行情+K线+分钟K线+分时

```python
from stoke.sources.tencent_direct_source import TencentDirectSource
t = TencentDirectSource()
```

| 方法 | 说明 | 示例 |
|------|------|------|
| `get_realtime(symbols)` | A股实时行情（50+字段） | `t.get_realtime(["000001"])` |
| `get_kline(symbol)` | K线（日/周/月，前/后复权） | `t.get_kline("600519")` |
| **`get_market_realtime(codes)`** | **跨市场行情（港股/美股/指数/ETF）** | `t.get_market_realtime(["sh000001","hk00700","usAAPL"])` |
| **`get_brief_info(codes)`** | **简要信息（12字段轻量级）** | `t.get_brief_info(["sh600519","hk00700"])` |
| **`get_tick_analysis(symbol)`** | **盘口大单/小单比率** | `t.get_tick_analysis("sh600519")` |
| **`get_minute_kline(symbol, freq)`** | **分钟K线（m5/m15/m30/m60）** | `t.get_minute_kline("sh600519","m5",240)` |
| **`get_intraday_line(symbol)`** | **当日分时线（价格/均价/成交量）** | `t.get_intraday_line("sh600519")` |
| **`get_intraday_mline(symbol)`** | **当日分钟K线（1分钟OHLCV）** | `t.get_intraday_mline("sh600519")` |
| **`get_fqkline(symbol, freq, adjust)`** | **复权K线（后复权hfq独立端点）** | `t.get_fqkline("sh600519","day","hfq")` |

### 🔬 efinance 扩展能力（efinance_source）

| 方法 | 说明 | 示例 |
|------|------|------|
| `get_realtime_all()` | 全市场实时快照 | `e.get_realtime_all()` |
| `get_capital_flow(symbol)` | 个股资金流（主力/大单/中单） | `e.get_capital_flow("600519")` |
| `get_sector_members(symbol)` | 股票所属板块 | `e.get_sector_members("600519")` |

### 📊 baostock 扩展能力（baostock_source）

| 方法 | 说明 | 示例 |
|------|------|------|
| `get_kline_with_valuation(symbol)` | K线+PE/PB/PS/PCF估值 | `b.get_kline_with_valuation("sh.600000")` |
| `get_profit_data(symbol, year, q)` | 季度利润（ROE/净利率/EPS） | `b.get_profit_data("sh.600000", 2025, 1)` |
| `get_index_constituents(name)` | 指数成分股 | `b.get_index_constituents("沪深300")` |

---

## 统一入口（Stoke 门面类）

所有数据源通过一个类访问，无需记忆哪个接口来自哪个源：

```python
from stoke import Stoke
s = Stoke()

s.realtime(["000001"])       # 实时行情     → mootdx
s.kline("000001")            # K线          → mootdx
s.news("000001")             # 个股新闻     → akshare
s.research("000001")         # 研报         → akshare
s.limit_up()                 # 涨停板       → akshare
s.strong_stocks()            # 强势涨停     → akshare
s.index_pe("上证50")          # PE估值       → legulegu
s.market_pb()                # PB估值       → legulegu
s.realtime_all()             # 全市场快照   → efinance
s.kline_with_valuation("sh.600000")  # K线+估值 → baostock
```

### FallbackStoke（多源自动备份）

```python
from stoke import FallbackStoke
s = FallbackStoke()  # 自动前导探路，5 秒内检测各源健康状态

s.kline("000001")     # mootdx → efinance → baostock → 腾讯直连（4 级）
s.realtime(["000001"]) # mootdx → 腾讯直连 → 新浪直连 → efinance（4 级）
```

akshare 不可用时，新闻/研报/涨停等独占方法返回空 DataFrame + warning，不阻塞。

各底层 Source 仍可直接访问：`s.mootdx.get_kline(...)`、`s.akshare.get_news(...)`。

## 常用查询模板

### 查实时行情（统一入口）
```bash
cd "$STOKE_HOME" && uv run python3 -c "
from stoke import Stoke
s = Stoke()
df = s.realtime(['000001', '600000', '000858'])
print(df[['code', 'price', 'open', 'high', 'low', 'vol', 'amount']].to_string())
"
```

### 查K线
```bash
cd "$STOKE_HOME" && uv run python3 -c "
from stoke import Stoke
s = Stoke()
df = s.kline('000001')
print(df.tail(5)[['open', 'close', 'high', 'low', 'volume']].to_string())
"
```

### 查今日强势涨停（含题材归因）
```bash
cd "$STOKE_HOME" && uv run python3 -c "
from stoke import Stoke
s = Stoke()
df = s.strong_stocks()
print(df[['代码', '名称', '涨跌幅', '入选理由', '所属行业']].head(20).to_string())
"
```

### 查研报
```bash
cd "$STOKE_HOME" && uv run python3 -c "
from stoke import Stoke
s = Stoke()
df = s.research('000001')
print(df[['报告名称', '机构', '东财评级', '日期']].head(10).to_string())
"
```

### 查PE/PB估值
```bash
cd "$STOKE_HOME" && uv run python3 -c "
from stoke import Stoke
s = Stoke()
pe = s.index_pe('上证50')
pb = s.market_pb()
print(f'上证50 PE: {pe[\"滚动市盈率\"].iloc[-1]:.2f} (日期: {pe[\"日期\"].iloc[-1]})')
print(f'全市场 PB: {pb[\"middlePB\"].iloc[-1]:.2f} (日期: {pb[\"date\"].iloc[-1]})')
"
```

---

## 执行规则

1. **运行前先检测 STOKE_HOME**：优先用环境变量，其次查找本地克隆
2. **首次使用需安装**：`cd "$STOKE_HOME" && uv sync`
3. **akshare 查询必须单条执行**：每次调用自动 5 秒限流，不能并行
4. **结果中有中文时**：用 `to_string()` 而非直接 print DataFrame
5. **单次查询数据量过大时**：用 `.head(N)` 或 `.tail(N)` 截断
6. **日期格式**：`YYYYMMDD`，如 `20260518`。不传则默认今天
7. **股票代码**：mootdx 用纯数字（`"000001"`），akshare 也用纯数字

---

## 故障排查

| 问题 | 原因 | 解决 |
|------|------|------|
| `STOKE_HOME` 未设置 | 首次使用 | `export STOKE_HOME=/path/to/stoke` |
| `connection aborted` | 东财限流 | 等待 10 秒后重试 |
| `ModuleNotFoundError: stoke` | 包未安装 | `cd "$STOKE_HOME" && uv sync` |
| mootdx K线数据为空 | 非交易日 | 检查日期是否为交易日 |
| F10 返回异常 | pandas 3.0 兼容性问题 | 用 `a.get_research_report(symbol)` 获取财务数据替代 |

---

## 平台兼容性

基于 `agentskills.io` 开放标准，兼容 27+ 个 AI Agent 平台。

| 特性 | Claude Code | OpenClaw | Hermes |
|------|:--:|:--:|:--:|
| `name` / `description` 触发 | ✅ | ✅ | ✅ |
| `homepage` | — | ✅ | ✅ |
| `platforms` | — | ✅ | ✅ |
| `metadata.openclaw` | — | ✅ | — |
| `metadata.hermes` | — | — | ✅ |
| `requires: {}` | — | ✅ 零依赖 | — |
| `uv run` 执行 | ✅ | ✅ | ✅ |

**Hermes 安装路径：** `~/.hermes/skills/stoke/SKILL.md`
