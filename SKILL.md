---
name: stoke
description: |
  A股量化数据层，覆盖行情/研报/信号/新闻/基础数据/公告 6 大层面。
  当用户提到"股票"、"行情"、"K线"、"涨停"、"强势股"、"研报"、"PE"、"PB"、"估值"、
  "个股新闻"、"公告"、"题材"、"概念板块"、"行业板块"、"财联社"、"电报"、"A股"时触发。
  也用于查某只股票的实时价格、历史K线、财务研报、新闻公告等。
metadata:
  openclaw:
    emoji: 📈
    requires: {}
---

# Stoke — A股数据层技能

纯数据获取层，**零 API Key 依赖**，所有数据源免注册。

项目路径：`/Volumes/Black/Stoke/`
运行方式：`uv run python3 -c "..."` （必须在项目根目录执行）

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
| `get_stock_list()` | 全市场股票列表 | `m.get_stock_list()` |
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
cd /Volumes/Black/Stoke && uv run python3 -c "
from stoke.sources.mootdx_source import MootdxSource
m = MootdxSource()
df = m.get_realtime(['000001', '600000', '000858'])
print(df[['code', 'price', 'open', 'high', 'low', 'vol', 'amount']].to_string())
"
```

### 查K线
```bash
cd /Volumes/Black/Stoke && uv run python3 -c "
from stoke.sources.mootdx_source import MootdxSource
m = MootdxSource()
df = m.get_kline('000001')
# 显示最近5条
print(df.tail(5)[['open', 'close', 'high', 'low', 'volume']].to_string())
"
```

### 查今日强势涨停（含题材归因）
```bash
cd /Volumes/Black/Stoke && uv run python3 -c "
from stoke.sources.akshare_source import AKShareSource
a = AKShareSource()
df = a.get_strong_stocks()
print(df[['代码', '名称', '涨跌幅', '入选理由', '所属行业']].head(20).to_string())
"
```

### 查研报
```bash
cd /Volumes/Black/Stoke && uv run python3 -c "
from stoke.sources.akshare_source import AKShareSource
a = AKShareSource()
df = a.get_research_report('000001')
print(df[['报告名称', '机构', '东财评级', '日期']].head(10).to_string())
"
```

### 查PE/PB估值
```bash
cd /Volumes/Black/Stoke && uv run python3 -c "
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

1. **运行前先 cd 到项目根目录**：`cd /Volumes/Black/Stoke`
2. **akshare 查询必须单条执行**：每次调用自动 5 秒限流，不能并行
3. **结果中有中文时**：用 `to_string()` 而非直接 print DataFrame，避免编码问题
4. **单次查询数据量过大时**：用 `.head(N)` 或 `.tail(N)` 截断显示
5. **日期格式**：`YYYYMMDD`，如 `20260518`。不传则默认今天
6. **股票代码**：mootdx 用纯数字（`"000001"`），akshare 也用纯数字（`"000001"`）

---

## 故障排查

| 问题 | 原因 | 解决 |
|------|------|------|
| `connection aborted` | 东财限流触发 | 等待 10 秒后重试 |
| `ModuleNotFoundError: stoke` | 包未安装 | `cd /Volumes/Black/Stoke && uv pip install -e .` |
| mootdx K线数据为空 | 非交易日 | 检查日期是否为交易日 |
| F10 返回异常 | pandas 3.0 兼容 | 暂时用 akshare 替代 |
