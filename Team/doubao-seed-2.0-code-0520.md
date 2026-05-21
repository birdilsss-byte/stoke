# Stoke 数据层深度审核报告

> 审核日期：2026-05-20
> 审核范围：数据层全部源码（11 文件）+ 测试套件（6 文件）
> 审核视角：面向时机层、发现层开发的数据层就绪度分析

---

## 一、项目现状总览

### 1.1 架构结构

```
stoke/                            # Python 包 v1.3.0
├── __init__.py                   # 导出 Stoke 统一入口
├── client.py                     # Stoke 门面类（231 行，40+ 方法）
├── config.py                     # 全局配置（仅限流间隔 + 日志级别）
├── rate_limiter.py               # 统一限流器（带随机抖动）
├── utils.py                      # 自动重试装饰器（指数退避）
└── sources/
    ├── mootdx_source.py          # 通达信 TCP：K线、实时行情、股票列表、F10
    ├── akshare_source.py         # HTTP：新闻/研报/公告/涨停/资金流/情绪/板块（426 行）
    └── tencent_source.py         # 腾讯估值：指数PE、全市场PB
```

### 1.2 已有能力矩阵

| 数据层面 | 接口数 | 数据源 | 状态 |
|----------|--------|--------|------|
| 行情 | 4（K线/实时/股票列表/F10） | mootdx | ✅ 稳定 |
| 新闻 | 2（个股新闻/财联社电报） | akshare | ✅ 稳定 |
| 研报 | 1（东财研报） | akshare | ✅ 稳定 |
| 公告 | 1（巨潮公告） | akshare | ✅ 稳定 |
| 信号 | 2（涨停板/强势涨停） | akshare | ✅ 稳定 |
| 板块 | 2（概念/行业列表） | akshare | ✅ 稳定 |
| 资金流 | 7（北向/龙虎榜/融资融券/市场资金流/个股资金流） | akshare | ✅ 稳定 |
| 情绪 | 11（东财热度/雪球热度/千股千评/关注指数/跌停） | akshare | ✅ 稳定 |
| 估值 | 2（指数PE/全市场PB） | tencent | ✅ 稳定 |
| **合计** | **32 接口，9 大层面** | 3 数据源 | |

### 1.3 工程质量评估

| 维度 | 评分 | 说明 |
|------|------|------|
| 限流机制 | ⭐⭐⭐⭐⭐ | 每个数据源独立限流器 + 随机抖动，铁律执行 |
| 重试机制 | ⭐⭐⭐⭐ | 指数退避重试 + 网络异常识别，mootdx 有重连逻辑 |
| 日志系统 | ⭐⭐⭐ | 关键节点有日志，但未输出到文件、无可观测性 |
| 测试覆盖 | ⭐⭐⭐⭐ | 40 项压力测试 + HTML 报告 + 跨平台验收 |
| 错误处理 | ⭐⭐⭐ | 有 try/except 但无自定义异常类、无降级策略 |
| 配置管理 | ⭐⭐ | 全部硬编码，无环境变量/配置文件支持 |

---

## 二、数据层核心问题诊断

### 问题 1：无数据规范化层 → 时机层/发现层无法直接消费

**现象**：不同数据源返回的 DataFrame 列名、日期格式、数据类型各自为政。

```python
# mootdx K 线列名（英文）
kline.columns = ['open', 'close', 'high', 'low', 'volume', 'datetime', ...]

# akshare 涨停板列名（中文）
limit_up.columns = ['代码', '名称', '涨跌幅', '封板时间', ...]

# akshare 资金流列名（中文，但不同接口命名风格不同）
fund_flow.columns = ['日期', '主力净流入-净额', '超大单净流入-净额', ...]

# tencent PE 列名（英文 + 中文混合）
pe.columns = ['日期', '指数点位', '滚动市盈率', 'equalWeightAveragePE', ...]
```

**对时机层的影响**：
- 时机层需要将 PE 估值 + 市场资金流 + 情绪评分合并成综合判断信号，列名不统一意味着每次都要写映射代码
- 日期字段格式不一致（`datetime`, `日期`, `date`, `时间`），无法直接 merge

**对发现层的影响**：
- 发现层需要对全市场股票做多维度筛选（PE < 20 + 资金流入 > 0 + 情绪上升），每换一个接口就要重写筛选条件

---

### 问题 2：akshare 5 秒限流是发现层的致命瓶颈

**现象**：akshare 每个请求间隔 5 秒，扫描全市场 5000+ 只股票需要约 7 小时。

```python
# 发现层理想逻辑：扫描 5000 只股票，每只查资金流 + 热度
for symbol in all_stocks:          # 5000 次
    fund = s.individual_fund_flow(symbol)   # 5s
    hot = s.hot_detail(symbol)              # 5s
# 总耗时: 5000 × 10s = 50,000s ≈ 14 小时 ← 不可用
```

**根本原因**：发现层需要的是**横截面快照**（同一时刻全市场的数据），而当前接口都是**逐个查询**的。

**解决方案方向**：
- 寻找支持批量查询的替代接口（如东财全市场资金流排行表）
- 用通达信 TCP 批量取行情，只在必要时用 akshare
- 预缓存日终数据，发现层只读缓存

---

### 问题 3：缺少行业/板块行情数据 → 时机层无法做行业轮动

**现象**：当前只有 `get_concept_list()` 和 `get_industry_list()` 返回板块名称列表，但没有板块指数的 K 线/行情数据。

**时机层的核心需求**：
```
判断建仓时机 = 大盘环境(PE分位+资金流) × 行业轮动(板块相对强度) × 情绪(热度+关注度)
                  ✅ 已有                    ❌ 缺失                    ✅ 部分有
```

**缺失的数据**：
- 申万一级/二级行业指数日 K 线（含涨跌幅、成交额）
- 行业相对强度排名（每日各行业涨跌幅排序）
- 概念板块热度排行
- 行业资金流入流出排名

---

### 问题 4：缺少市场宽度数据 → 时机层的"大盘环境判断"缺一半

**现象**：PE/PB 估值 + 市场资金流能判断估值水位和资金方向，但缺少市场内在结构数据。

**时机层需要的、但当前缺失的数据**：

| 数据 | 用途 | 当前状态 |
|------|------|----------|
| 涨跌家数（上涨/下跌/平盘） | 市场温度计 | ❌ 缺失 |
| 创 N 日新高/新低家数 | 趋势强度 | ❌ 缺失 |
| 均线多头排列占比 | 中期趋势 | ❌ 缺失 |
| 成交额总量（沪深合计） | 量能判断 | ❌ 缺失 |
| 涨停/跌停家数趋势 | 极端情绪 | ⚠️ 有单日，无历史趋势 |
| 北向资金实时流向 | 聪明钱方向 | ⚠️ 有历史日数据，无盘中实时 |

---

### 问题 5：情绪数据碎片化 → 无法合成统一情绪指标

**现象**：情绪数据分散在 11 个不同接口中，来自不同平台（东财热度、雪球热度、千股千评），口径不一致。

```python
# 当前：11 个独立接口，各自为政
s.hot_detail("000001")        # 东财：新晋粉丝/铁杆粉丝比例
s.hot_latest("000001")        # 东财：最新排名
s.hot_realtime("000001")      # 东财：盘中实时排名
s.hot_keywords()              # 东财：热搜关键词
s.xueqiu_hot()                # 雪球：热度排行
s.stock_comment_all()         # 千股千评：综合得分
s.stock_desire("000001")      # 参与意愿
s.stock_focus("000001")       # 关注指数
s.limit_up()                  # 涨停（情绪极端）
s.limit_down()                # 跌停（恐慌）
```

**问题**：
- 各接口的评分尺度和范围不同（有的是排名、有的是比例、有的是得分），无法直接加权合成
- 没有统一的「情绪温度计」（0-100 的标准化指标）
- 缺少历史情绪面板数据（只能看今天，无法回溯历史情绪拐点）

---

### 问题 6：没有交易日历 → 时机层的信号判断会出错

**现象**：代码中用 `datetime.now()` 获取当天日期，但不判断是否为交易日。

```python
# akshare_source.py 中的问题
def get_limit_up_pool(self, date: Optional[str] = None):
    if date is None:
        date = datetime.now().strftime("%Y%m%d")  # 周六也返回日期！
```

**对时机层的影响**：
- 判断「连续 N 日资金流入」时，如果包含周末/节假日，会误判中断
- K 线数据中周末无数据，但代码没有跳过非交易日的概念
- 回测时需要知道哪些日期是交易日，否则会产生错误的收益率计算

---

### 问题 7：F10 财务数据不可靠 → 基础数据层面有缺口

**现象**：[mootdx_source.py:L106-L108](file:///Volumes/Black/Stoke/stoke/sources/mootdx_source.py#L106-L108) 明确标注了 pandas 3.0 兼容性问题。

```python
# 文档中自带的警告
"""
⚠️ 当前版本与 pandas 3.0 有兼容性问题，
某些字段可能返回 DataFrame 而非预期类型。
"""
```

**对发现层的影响**：
- 发现层的中线低吸高抛策略需要 PE、PB、ROE、营收增速等财务指标做基本面筛选
- F10 不可靠时，只能依赖腾讯的指数 PE（全市场级别，非个股级别）
- **个股估值数据完全缺失** ← 这是中线策略的基石

---

### 问题 8：K 线数据缺少复权处理 → 回测结果会有偏差

**现象**：mootdx 获取的 K 线是原始价格，没有复权（前复权/后复权）。

**对发现层的影响**：
- 中线策略看历史 K 线找支撑/压力位时，未复权的价格在除权除息日会发生跳空
- 计算技术指标（均线、MACD）时，除权缺口会导致假信号
- 通达信 TCP 协议**支持复权 K 线**（通过设置参数），但当前没有暴露这个选项

---

### 问题 9：缺少技术指标计算 → 发现层需要自己实现

**现象**：当前数据层**只提供原始数据**（这是设计原则），但对于发现层来说，MA、MACD、RSI、布林带等技术指标是刚需。

**权衡**：保持数据层纯净 vs 为上层提供便利。建议在数据层之上加一个薄的指标计算工具模块，而不是在 Source 层做。

---

### 问题 10：没有横截面数据获取能力 → 发现层效率极低

**现象**：要筛选「PE < 20 且主力资金连续 3 日流入的股票」，当前需要：
1. 先取全市场股票列表
2. 逐个查 PE（但没有个股 PE 接口！）
3. 逐个查资金流（每只 5 秒）

**发现层的正确做法**：一次性获取全市场某一天的横截面数据（类似 Excel 的一张表，行=股票，列=指标），然后在内存中筛选。

---

## 三、针对时机层 & 发现层的优化建议

### 建议总览

| 编号 | 优化项 | 紧迫度 | 影响范围 |
|------|--------|--------|----------|
| A | 数据规范化层（列名 + 日期统一） | 🔴 极高 | 时机层 + 发现层 |
| B | 行业板块行情数据 | 🔴 极高 | 时机层 |
| C | 市场宽度数据 | 🔴 极高 | 时机层 |
| D | 个股估值数据 | 🔴 极高 | 发现层 |
| E | 交易日历模块 | 🟡 高 | 时机层 + 发现层 |
| F | K线复权支持 | 🟡 高 | 发现层 |
| G | 情绪合成指标 | 🟡 高 | 时机层 |
| H | 横截面数据批量获取 | 🟡 高 | 发现层 |
| I | 技术指标计算模块 | 🟢 中 | 发现层 |
| J | 数据缓存层 | 🟢 中 | 全局效率 |
| K | 配置外部化 | 🟢 低 | 运维 |
| L | 自定义异常体系 | 🟢 低 | 稳定性 |

---

### 建议 A：数据规范化层（极高优先级）

**目标**：所有接口返回的 DataFrame 使用统一的列名规范和日期格式，时机层/发现层直接消费。

**具体方案**：

```python
# stoke/normalizer.py
"""数据规范化：统一列名映射 + 日期标准化"""

_COLUMN_MAP = {
    # mootdx K线 → 统一名称
    "open":     "开盘价",
    "close":    "收盘价",
    "high":     "最高价",
    "low":      "最低价",
    "volume":   "成交量",
    "amount":   "成交额",
    "datetime": "日期",

    # akshare 资金流 → 统一名称
    "主力净流入-净额":    "主力净流入",
    "超大单净流入-净额":  "超大单净流入",
    # ... 更多映射
}

def normalize(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """统一列名 + 日期转 datetime 类型"""
    df = df.copy()
    df.rename(columns=_COLUMN_MAP, inplace=True)

    # 自动检测日期列并标准化
    for col in df.columns:
        if any(kw in col for kw in ["日期", "时间", "date", "datetime"]):
            df[col] = pd.to_datetime(df[col])
    return df
```

**预期收益**：时机层/发现层代码不需要任何列名转换，大幅减少适配代码。

---

### 建议 B：行业板块行情数据（极高优先级）

**目标**：获取申万行业指数的 K 线数据和每日涨跌排名。

**实现路径**：

```python
# stoke/sources/mootdx_source.py 扩展
def get_sector_kline(self, sector_code: str, frequency: int = 9,
                     start: int = 0, offset: int = 800) -> pd.DataFrame:
    """
    获取行业板块指数 K 线

    通达信板块代码规则：
    - 行业板块: 以 '880' 开头，如 '880471' = 银行
    - 概念板块: 以 '886' 开头
    """
    self.limiter.wait()
    return self._call("get_sector_kline", self.client.bars,
                      symbol=sector_code, frequency=frequency,
                      start=start, offset=offset)
```

同时从 akshare 获取行业排名：

```python
# akshare 补充接口
def get_sector_rank(self) -> pd.DataFrame:
    """当日行业涨跌幅排名"""
    self.limiter.wait()
    return ak.stock_board_industry_index_ths()
```

**预期收益**：时机层可以直接计算行业相对强度，实现行业轮动策略。

---

### 建议 C：市场宽度数据（极高优先级）

**目标**：获取每日涨跌家数、新高新低家数等市场内部结构数据。

**实现路径**：
- 涨跌家数：可以从 mootdx 的 `get_stock_list()` + `get_realtime()` 中自算（取全市场行情后统计涨跌平），但效率低
- 更优方案：akshare 有 `ak.stock_zh_index_daily()` 可以取到上证/深证涨跌家数
- 通达信 TCP 协议支持直接获取市场统计

```python
# akshare 补充接口示例
def get_market_breadth(self) -> pd.DataFrame:
    """市场宽度：涨跌家数 + 新高新低"""
    self.limiter.wait()
    up_down = ak.stock_zh_index_daily(symbol="sh000001")
    return up_down[["date", "up_count", "down_count", "flat_count"]]
```

**预期收益**：时机层的「大盘环境判断」从 PE/PB 单一维度，扩展为估值 + 资金流 + 市场宽度的三维框架。

---

### 建议 D：个股估值数据（极高优先级）

**目标**：获取个股 PE/PB/ROE 等基本面指标，支持发现层的中线筛选。

**问题**：当前 F10 不可靠，腾讯只提供指数级 PE/PB，没有个股估值。

**备选方案**：

| 方案 | 数据源 | 可靠性 | 覆盖度 |
|------|--------|--------|--------|
| akshare `stock_a_lg_indicator()` | 腾讯财经 | ⭐⭐⭐⭐ | 全市场 |
| akshare `stock_yjbb_em()` | 东财业绩报表 | ⭐⭐⭐⭐ | 全市场 |
| akshare `stock_financial_analysis_indicator()` | 东财财务指标 | ⭐⭐⭐ | 全市场 |

```python
# AKShareSource 新增
def get_stock_indicator(self, symbol: str) -> pd.DataFrame:
    """个股核心指标：PE、PB、ROE、营收增速等"""
    self.limiter.wait()
    return ak.stock_a_lg_indicator(symbol=symbol)
```

**预期收益**：发现层「扫全市场低估值股票」从不可用变为可用。

---

### 建议 E：交易日历模块（高优先级）

**目标**：提供交易日判断能力，所有日期相关逻辑基于交易日历而非自然日。

```python
# stoke/calendar.py
import pandas as pd

class TradingCalendar:
    """A 股交易日历"""

    def __init__(self):
        self._cache = None

    def _load(self):
        """从 mootdx 或 akshare 获取交易日历"""
        import akshare as ak
        self._cache = ak.tool_trade_date_hist_sina()

    def is_trading_day(self, date=None) -> bool:
        """判断是否为交易日"""
        ...

    def prev_trading_day(self, date=None) -> str:
        """上一个交易日"""
        ...

    def trading_days_between(self, start, end) -> list:
        """两个日期之间的交易日列表"""
        ...
```

**预期收益**：时机层「连续 N 日」的判断不会因为周末/节假日而出错。

---

### 建议 F：K 线复权支持（高优先级）

**目标**：获取前复权/后复权 K 线，消除除权除息对技术分析的影响。

```python
# MootdxSource.get_kline 扩展
def get_kline(self, symbol, frequency=9, start=0, offset=800,
              adjust: str = "none") -> pd.DataFrame:
    """
    Args:
        adjust: "none"(不复权) / "qfq"(前复权) / "hfq"(后复权)
    """
    # mootdx 支持通过 market 参数区分复权类型
    # market="std" → 不复权
    # 需要创建不同 market 的 client 实例
```

**预期收益**：发现层的中线趋势分析不再被除权缺口干扰。

---

### 建议 G：情绪合成指标（高优先级）

**目标**：将 11 个碎片化的情绪接口合成为一个 0-100 的情绪温度计。

**合成公式建议**：

```python
# stoke/sentiment.py
def sentiment_index(s: Stoke) -> float:
    """
    综合情绪指标（0=极度恐慌, 100=极度贪婪）

    权重设计：
    - 涨停家数占比:  20%
    - 跌停家数占比:  20%（反向）
    - 热搜关键词变化: 15%
    - 千股千评均分:   15%
    - 主力资金流向:   15%
    - 北向资金流向:   15%
    """
    ...
```

**预期收益**：时机层可以直接用「情绪 < 20 → 恐慌 → 建仓信号；情绪 > 80 → 贪婪 → 止盈信号」。

---

### 建议 H：横截面数据批量获取（高优先级）

**目标**：一次性获取全市场某一天的多维横截面数据，支持发现层高效筛选。

**核心思路**：不要逐个查个股，而是寻找支持「全市场一览表」的接口。

```python
# akshare 已支持的全市场接口（横截面）
ak.stock_comment_em()              # 千股千评（全市场）
ak.stock_a_lg_indicator()          # 全市场个股指标（逐只，但有批量版）
ak.stock_zh_a_spot_em()            # 全市场实时行情快照

# 发现层筛选示例
def screen_low_pe_high_fundflow(s: Stoke):
    """筛选低估值 + 资金流入股票"""
    indicators = s.akshare.get_all_stock_indicators()   # 全市场 PE/PB
    fundflow = s.akshare.get_all_fundflow_today()       # 全市场资金流排名
    merged = indicators.merge(fundflow, on="代码")
    return merged[(merged["市盈率"] < 20) & (merged["主力净流入"] > 0)]
```

**预期收益**：发现层扫描全市场从 14 小时降到分钟级。

---

### 建议 I：技术指标计算模块（中优先级）

**目标**：在数据层之上提供基础技术指标计算，降低发现层的实现成本。

```python
# stoke/indicators.py
import pandas as pd

def ma(df: pd.DataFrame, period: int, on: str = "收盘价") -> pd.Series:
    """移动平均线"""
    return df[on].rolling(period).mean()

def macd(df: pd.DataFrame, fast=12, slow=26, signal=9):
    """MACD 金叉死叉"""
    ...

def rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """相对强弱指标"""
    ...

def bollinger(df: pd.DataFrame, period=20, std=2):
    """布林带"""
    ...
```

---

### 建议 J：数据缓存层（中优先级）

**目标**：对不常变化的数据（股票列表、行业列表、交易日历、日 K 线历史）做本地缓存，减少网络请求。

```python
# stoke/cache.py
import json, os, time
from datetime import datetime

class FileCache:
    """简单的文件缓存"""

    def __init__(self, cache_dir: str = ".stoke_cache"):
        self.dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def get(self, key: str, max_age_sec: int = 3600):
        """读取缓存，超时返回 None"""
        path = os.path.join(self.dir, f"{key}.parquet")
        if not os.path.exists(path):
            return None
        if time.time() - os.path.getmtime(path) > max_age_sec:
            return None
        return pd.read_parquet(path)

    def set(self, key: str, df: pd.DataFrame):
        """写入缓存（parquet 格式，高效压缩）"""
        path = os.path.join(self.dir, f"{key}.parquet")
        df.to_parquet(path, index=False)
```

**特别说明**：设计原则是「不做缓存」，但对于发现层来说，全市场股票列表、行业列表等静态数据每天只需获取一次。建议作为**可选功能**，默认不开启。

---

### 建议 K：配置外部化（低优先级）

**目标**：支持从环境变量或 YAML 文件加载配置，便于不同环境（开发/生产）切换。

```python
# stoke/config.py 升级
import os, yaml

def load_config():
    config_path = os.environ.get("STOKE_CONFIG", "config.yaml")
    if os.path.exists(config_path):
        with open(config_path) as f:
            return yaml.safe_load(f)
    return {
        "rate_limit": {"mootdx": 0, "akshare": 5, "tencent": 3},
        "log_level": "INFO",
    }
```

---

### 建议 L：自定义异常体系（低优先级）

**目标**：区分网络异常、数据异常、限流异常，让上层（时机层/发现层）能做差异化处理。

```python
# stoke/exceptions.py
class StokeError(Exception): ...
class NetworkError(StokeError): ...       # 网络问题 → 可重试
class DataEmptyError(StokeError): ...     # 数据为空 → 可能非交易日
class RateLimitError(StokeError): ...     # 限流触发 → 需等待
class AuthError(StokeError): ...          # 鉴权失败 → 需检查
```

---

## 四、开发的优先级路线图

```
阶段一（数据层补全）              阶段二（时机层基础）            阶段三（发现层基础）
──────────────────────────────────────────────────────────────────────────
A 数据规范化                    基于规范化数据：                 基于横截面数据：
├─ 统一列名映射                   ├─ 大盘温度计                    ├─ 全市场低估值筛选
├─ 日期标准化                     │  = PE分位 + 资金流 +         │  = 个股PE/PB < 阈值
└─ 修改各 Source 返回前调用        │    市场宽度 + 情绪合成         │    + 资金流为正
                                 │                              │    + 技术面多头排列
B 行业板块行情                     ├─ 行业轮动信号                  │
├─ mootdx 扩展取板块K线            │  = 行业相对强度排名            ├─ 短线机会发现
└─ akshare 取行业排名              │    + 行业资金流入              │  = 涨停板题材归因
                                 │    + 行业情绪热度               │    + 量价异动
C 市场宽度数据                    │                              │    + 均线突破
├─ 涨跌家数                       ├─ 建仓/止盈信号规则             │
├─ 新高新低家数                    │  = 温度计 < 30 → 可建仓        │
└─ 成交额总量                     │  = 温度计 > 70 → 止盈          │

D 个股估值                        E 交易日历                      H 横截面批量
                                  F K线复权                       I 技术指标
                                  G 情绪合成                      J 数据缓存
```

---

## 五、代码级问题清单

以下是在逐行审查中发现的具体代码问题：

| # | 位置 | 问题 | 严重度 |
|---|------|------|--------|
| 1 | [config.py:L6-L10](file:///Volumes/Black/Stoke/stoke/config.py#L6-L10) | `RATE_LIMIT` 是模块级全局变量，无法在运行时动态调整 | 低 |
| 2 | [mootdx_source.py:L106-L108](file:///Volumes/Black/Stoke/stoke/sources/mootdx_source.py#L106-L108) | F10 与 pandas 3.0 兼容性问题未解决，文档中标注了 ⚠️ 但未处理 | 中 |
| 3 | [akshare_source.py:L103-L104](file:///Volumes/Black/Stoke/stoke/sources/akshare_source.py#L103-L104) | `get_limit_up_pool()` 和 `get_strong_stocks()` 中 `date` 默认用 `datetime.now()`，不判断交易日 | 中 |
| 4 | [rate_limiter.py:L31-L33](file:///Volumes/Black/Stoke/stoke/rate_limiter.py#L31-L33) | 抖动逻辑在 `elapsed < interval` 时会**额外加 0.1~0.5 秒**，导致实际间隔总是 > interval，对 akshare 来说 5s 变成 5.1~5.5s，累积效应明显 | 低 |
| 5 | [akshare_source.py:L265-L267](file:///Volumes/Black/Stoke/stoke/sources/akshare_source.py#L265-L267) | `_add_market_prefix()` 是静态方法但只处理 6 位代码，3 位 ETF 代码会出错 | 低 |
| 6 | [client.py](file:///Volumes/Black/Stoke/stoke/client.py) | 门面类方法全是透传，没有做任何参数校验（如股票代码格式检查） | 低 |
| 7 | [utils.py](file:///Volumes/Black/Stoke/stoke/utils.py) | `retry_on_failure` 只重试网络异常，但 akshare 有时返回空 DataFrame 而非异常，这种情况不会重试 | 中 |
| 8 | 全局 | 没有任何 `__repr__` 或 `__str__` 方法，调试时 print(source) 无有用信息 | 低 |

---

## 六、总结

**Stoke 数据层 v1.3.0 的定位是"免费数据调取层"，这个定位已经实现得非常扎实。** 32 个接口、3 个数据源、40 项压力测试、跨平台验证——作为数据层的 V1 阶段，工程质量超出预期。

**但要支撑时机层和发现层，数据层需要从"数据调取"升级为"数据服务"**。核心差距不在于接口数量（32 个已经很多），而在于三个结构性问题：

1. **数据不互通** — 各接口返回格式不同，上层需要大量胶水代码
2. **缺少基础构件** — 交易日历、复权 K 线、个股估值、市场宽度这四块是时机层的刚需
3. **效率不可用** — 5 秒限流让发现层的全市场扫描不可行，需要横截面接口 + 缓存策略

**建议按「建议总览」的优先级依次推进，先做 A/B/C/D 四项极高优先级（数据规范化 + 行业行情 + 市场宽度 + 个股估值），这四项到位后，时机层和发现层就有了坚实的数据地基。**