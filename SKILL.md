---
name: stoke
description: |
  🔥 免费 A 股数据层 — 零 API Key、零注册、零付费，开箱即用。
  覆盖行情/研报/信号/新闻/基础数据/公告 6 大层面，14 个接口。
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
        - mootdx
        - akshare
        - pandas
        - requests
  hermes:
    tags: [stock, finance, a-share, market-data, quant, free, zero-api-key]
    category: finance
---

# Stoke — A股数据层技能

纯数据获取层，**零 API Key 依赖**，所有数据源免注册。兼容 **Claude Code** · **OpenClaw** · **Hermes**。

## 🔧 安装（macOS / Windows 通用）

**1. 克隆项目：**

```bash
git clone https://github.com/birdilsss-byte/stoke.git ~/stoke
cd ~/stoke && uv sync
```

**2. 设置 STOKE_HOME 环境变量：**

| 系统 | 命令 |
|------|------|
| macOS | `echo 'export STOKE_HOME=~/stoke' >> ~/.bashrc` |
| Windows PowerShell | `[Environment]::SetEnvironmentVariable('STOKE_HOME', "$env:USERPROFILE\stoke", 'User')` |
| Windows CMD | `setx STOKE_HOME "%USERPROFILE%\stoke"` |

环境变量只需设置一次，重启终端后生效。也可手动 `export` 当前会话立即使用。

---

## ⚠️ 限流铁律

| 数据源 | 最小间隔 | 说明 |
|--------|---------|------|
| mootdx | 不限流 | TCP 协议，本地解析 |
| akshare | **5 秒** | 东财/同花顺/巨潮，必须遵守 |
| 腾讯财经 | **3 秒** | lg 接口，较为宽松 |

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

### 💹 腾讯财经 — 估值层

```python
from stoke.sources.tencent_source import TencentSource
t = TencentSource()
```

| 方法 | 说明 | 示例 |
|------|------|------|
| `get_index_pe(name)` | 指数PE历史 | `t.get_index_pe("上证50")` |
| `get_market_pb()` | 全市场PB历史 | `t.get_market_pb()` |

---

## 常用查询模板

### 查实时行情
```bash
cd "$STOKE_HOME" && uv run python3 -c "
from stoke.sources.mootdx_source import MootdxSource
m = MootdxSource()
df = m.get_realtime(['000001', '600000', '000858'])
print(df[['code', 'price', 'open', 'high', 'low', 'vol', 'amount']].to_string())
"
```

### 查K线
```bash
cd "$STOKE_HOME" && uv run python3 -c "
from stoke.sources.mootdx_source import MootdxSource
m = MootdxSource()
df = m.get_kline('000001')
print(df.tail(5)[['open', 'close', 'high', 'low', 'volume']].to_string())
"
```

### 查今日强势涨停（含题材归因）
```bash
cd "$STOKE_HOME" && uv run python3 -c "
from stoke.sources.akshare_source import AKShareSource
a = AKShareSource()
df = a.get_strong_stocks()
print(df[['代码', '名称', '涨跌幅', '入选理由', '所属行业']].head(20).to_string())
"
```

### 查研报
```bash
cd "$STOKE_HOME" && uv run python3 -c "
from stoke.sources.akshare_source import AKShareSource
a = AKShareSource()
df = a.get_research_report('000001')
print(df[['报告名称', '机构', '东财评级', '日期']].head(10).to_string())
"
```

### 查PE/PB估值
```bash
cd "$STOKE_HOME" && uv run python3 -c "
from stoke.sources.tencent_source import TencentSource
t = TencentSource()
pe = t.get_index_pe('上证50')
pb = t.get_market_pb()
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
