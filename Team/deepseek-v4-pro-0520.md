# Stoke 数据层紧急调整清单

> 目标：为时机层/发现层奠定数据地基
> 执行方式：Claude Code 逐项实施，每完成一项运行对应测试验证

---

## 任务总览

| 序号 | 任务 | 类型 | 文件 | 预计耗时 |
|------|------|------|------|----------|
| 1 | 数据规范化层 | 新建 | `stoke/normalizer.py` | 中 |
| 2 | 自定义异常体系 | 新建 | `stoke/exceptions.py` | 短 |
| 3 | 交易日历模块 | 新建 | `stoke/calendar.py` | 中 |
| 4 | 行业板块行情 | 修改 | `stoke/sources/mootdx_source.py` | 中 |
| 5 | K 线复权支持 | 修改 | `stoke/sources/mootdx_source.py` | 短 |
| 6 | 市场宽度数据 | 修改 | `stoke/sources/akshare_source.py` | 中 |
| 7 | 个股估值数据 | 修改 | `stoke/sources/akshare_source.py` | 中 |
| 8 | 行业资金流 + 行业排名 | 修改 | `stoke/sources/akshare_source.py` | 中 |
| 9 | 时点规整：日期改为上一交易日 | 修改 | `stoke/sources/akshare_source.py` | 短 |
| 10 | 限流抖动改为减法模式 | 修改 | `stoke/rate_limiter.py` | 短 |
| 11 | 重试覆盖空 DataFrame 场景 | 修改 | `stoke/utils.py` | 短 |
| 12 | client.py 同步新增方法 | 修改 | `stoke/client.py` | 中 |
| 13 | 全量验证 | 测试 | `tests/` | 长（限流等待） |

---

## 1. 数据规范化层

**文件**：`stoke/normalizer.py`（新建）

**目的**：所有数据源返回前统一列名和日期格式，消除上层胶水代码。

**实现要求**：

```python
"""
数据规范化：统一列名映射 + 日期标准化

每个数据源返回 DataFrame 前调用 normalize()，确保时机层/发现层
消费到的数据列名和日期格式统一。
"""

import pandas as pd

# 源列名 → 统一中文列名
_COLUMN_MAP = {
    # mootdx K 线 → 统一
    "open": "开盘价",
    "close": "收盘价",
    "high": "最高价",
    "low": "最低价",
    "volume": "成交量",
    "amount": "成交额",
    "datetime": "日期",

    # akshare 涨停板相关
    "代码": "代码",
    "名称": "名称",
    "涨跌幅": "涨跌幅",
    "封板时间": "封板时间",
    "炸板次数": "炸板次数",
    "连板数": "连板数",
    "入选理由": "入选理由",
    "所属行业": "所属行业",

    # akshare 资金流（去掉"-净额"等冗余后缀）
    "主力净流入-净额": "主力净流入",
    "超大单净流入-净额": "超大单净流入",
    "大单净流入-净额": "大单净流入",
    "中单净流入-净额": "中单净流入",
    "小单净流入-净额": "小单净流入",

    # akshare 新闻/电报
    "新闻标题": "标题",
    "发布时间": "发布时间",
    "新闻内容": "内容",

    # tencent 估值
    "滚动市盈率": "PE_TTM",
    "静态市盈率": "PE_静态",
    "middlePB": "PB_中位数",
    "equalWeightAveragePB": "PB_等权均值",
    "指数点位": "指数点位",
    "date": "日期",
}

# 日期列关键词（用于自动识别并转 datetime）
_DATE_KEYWORDS = ["日期", "时间", "date", "datetime", "发布时间"]


def normalize(df: pd.DataFrame, source: str = "") -> pd.DataFrame:
    """
    统一列名 + 日期列标准化为 datetime64 类型

    Args:
        df: 原始 DataFrame
        source: 数据源标识（仅用于日志，可选 "mootdx"/"akshare"/"tencent"）

    Returns:
        规范化后的 DataFrame（副本）
    """
    df = df.copy()

    # 1. 列名映射
    df.rename(columns=_COLUMN_MAP, inplace=True)

    # 2. 日期列标准化
    for col in df.columns:
        col_lower = col.lower()
        if any(kw in col_lower for kw in _DATE_KEYWORDS):
            try:
                df[col] = pd.to_datetime(df[col])
            except (ValueError, TypeError):
                pass  # 不可解析的列保持原样

    return df
```

**注意**：
- 这是一个**非侵入式工具函数**，不改动任何 Source 类的内部逻辑
- 调用方（时机层/发现层）自行决定是否调用 `normalize()`
- 当前阶段不强制在各 Source 内部调用，后续可逐步接入

---

## 2. 自定义异常体系

**文件**：`stoke/exceptions.py`（新建）

**目的**：区分类别异常，上层可以做差异化处理（重试 vs 跳过 vs 告警）。

```python
"""
Stoke 自定义异常体系

上层（时机层/发现层）可按异常类型决定处理策略：
  - NetworkError   → 等待后重试
  - DataEmptyError → 可能非交易日，跳过
  - RateLimitError → 排队等待
"""


class StokeError(Exception):
    """Stoke 所有异常的基类"""
    pass


class NetworkError(StokeError):
    """网络连接异常（可重试）"""
    pass


class DataEmptyError(StokeError):
    """数据返回为空（可能非交易日或无数据）"""
    pass


class RateLimitError(StokeError):
    """触发限流（需延长等待）"""
    pass


class SourceNotReadyError(StokeError):
    """数据源不可用（health_check 失败）"""
    pass
```

---

## 3. 交易日历模块

**文件**：`stoke/calendar.py`（新建）

**目的**：所有日期逻辑基于交易日而非自然日，消除周末/节假日误判。

**数据来源**：akshare `tool_trade_date_hist_sina()` 返回历年交易日列表。

```python
"""
A 股交易日历

提供交易日判断、上一交易日计算等功能。
数据来源：新浪财经交易日历（通过 akshare 获取），首次加载后缓存在本地。
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

_CACHE: Optional[set] = None


def _load_trading_days() -> set:
    """加载交易日历（首次网络请求，后续用内存缓存）"""
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    try:
        import akshare as ak
        df = ak.tool_trade_date_hist_sina()
        _CACHE = set(
            pd.to_datetime(df["trade_date"]).dt.date.tolist()
        )
        logger.info("交易日历加载完成，共 %d 个交易日", len(_CACHE))
    except Exception as e:
        logger.error("交易日历加载失败: %s，降级为周一至周五判断", e)
        _CACHE = set()  # 失败时用空集合触发降级逻辑
    return _CACHE


def is_trading_day(d: Optional[date] = None) -> bool:
    """判断是否为交易日"""
    if d is None:
        d = date.today()

    trading_days = _load_trading_days()
    if trading_days:
        return d in trading_days
    # 降级：未加载成功时，用周一至周五粗略判断
    return d.weekday() < 5


def today_str() -> str:
    """返回今天的 YYYYMMDD 字符串（如果是非交易日，返回最近交易日）"""
    d = date.today()
    while not is_trading_day(d):
        d = d - timedelta(days=1)
    return d.strftime("%Y%m%d")


def prev_trading_day(d: Optional[date] = None) -> date:
    """返回上一个交易日"""
    if d is None:
        d = date.today()
    d = d - timedelta(days=1)
    while not is_trading_day(d):
        d = d - timedelta(days=1)
    return d


def trading_days_between(start: date, end: date) -> list[date]:
    """返回两个日期之间的所有交易日（含起止）"""
    trading_days = _load_trading_days()
    if trading_days:
        return sorted([d for d in trading_days if start <= d <= end])
    # 降级
    result = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            result.append(d)
        d = d + timedelta(days=1)
    return result
```

---

## 4. mootdx 新增：行业板块 K 线 + 板块成分股

**文件**：`stoke/sources/mootdx_source.py`（修改）

**改动点**：在类中添加两个新方法。

**关键知识**：
- 通达信板块代码规则：行业板块以 `880` 开头（如 `880471`=银行），概念板块以 `886` 开头
- `client.bars()` 对板块代码同样有效，直接取 K 线
- `client.block()` 可获取板块成分股列表

```python
# 在 MootdxSource 类中新增以下方法

# ---------- 板块行情 ----------

def get_sector_kline(
    self,
    sector_code: str,
    frequency: int = 9,
    start: int = 0,
    offset: int = 800,
) -> pd.DataFrame:
    """
    获取行业/概念板块指数 K 线

    通达信板块代码规则：
    - 行业板块: 以 '880' 开头，如 '880471' = 银行
    - 概念板块: 以 '886' 开头

    Args:
        sector_code: 板块代码，如 '880471'
        frequency: K 线周期，9=日线，7=周线，6=月线
        start: 起始位置（0=最新）
        offset: 获取条数，默认 800

    Returns:
        DataFrame，与 get_kline 结构一致
    """
    self.limiter.wait()
    logger.info("获取板块 K 线: %s (frequency=%d)", sector_code, frequency)
    return self._call(
        "get_sector_kline",
        self.client.bars,
        symbol=sector_code,
        frequency=frequency,
        start=start,
        offset=offset,
    )


def get_sector_members(self, sector_code: str) -> pd.DataFrame:
    """
    获取板块成分股列表

    Args:
        sector_code: 板块代码，如 '880471'

    Returns:
        DataFrame，含 code、name 等成分股信息
    """
    self.limiter.wait()
    logger.info("获取板块成分股: %s", sector_code)
    return self._call(
        "get_sector_members",
        self.client.block,
        symbol=sector_code,
    )
```

**验证方法**：
```bash
uv run python3 -c "
from stoke.sources.mootdx_source import MootdxSource
m = MootdxSource()
df = m.get_sector_kline('880471')        # 银行板块
print(df.tail(5)[['open','close','high','low','volume']].to_string())
print()
members = m.get_sector_members('880471') # 银行成分股
print(members.head(10).to_string())
"
```

---

## 5. mootdx 修改：K 线复权支持

**文件**：`stoke/sources/mootdx_source.py`（修改）

**改动点**：给 `get_kline` 增加 `adjust` 参数。

**关键知识**：mootdx 通过 `Quotes.factory(market=...)` 区分复权类型：
- `market="std"` → 不复权
- `market="qfq"` → 前复权
- `market="hfq"` → 后复权

**实现方案**：为复权需求创建独立的 client 实例。

```python
# 修改 MootdxSource 类：

def __init__(self, rate_limiter=None):
    self.limiter = rate_limiter or RateLimiter(interval=RATE_LIMIT["mootdx"])
    self._client: Optional[Quotes] = None
    self._client_qfq: Optional[Quotes] = None  # 前复权客户端
    self._client_hfq: Optional[Quotes] = None  # 后复权客户端
    logger.info("MootdxSource 初始化，限流间隔 %.1f 秒", self.limiter.interval)


def _get_client(self, adjust: str = "none") -> Quotes:
    """根据复权类型返回对应客户端"""
    if adjust == "qfq":
        if self._client_qfq is None:
            self._client_qfq = Quotes.factory(market="qfq")
            logger.debug("mootdx 前复权客户端已创建")
        return self._client_qfq
    elif adjust == "hfq":
        if self._client_hfq is None:
            self._client_hfq = Quotes.factory(market="hfq")
            logger.debug("mootdx 后复权客户端已创建")
        return self._client_hfq
    else:
        return self.client  # 默认不复权


# 修改 get_kline 签名，增加 adjust 参数：
def get_kline(
    self,
    symbol: str,
    frequency: int = 9,
    start: int = 0,
    offset: int = 800,
    adjust: str = "none",
) -> pd.DataFrame:
    """
    获取日 K 线数据

    Args:
        symbol: 股票代码
        frequency: K 线周期，9=日线，7=周线，6=月线
        start: 起始位置（0=最新）
        offset: 获取条数，默认 800
        adjust: 复权方式，"none"(不复权) / "qfq"(前复权) / "hfq"(后复权)

    Returns:
        DataFrame
    """
    self.limiter.wait()
    logger.info(
        "获取 K 线: %s (frequency=%d, offset=%d, adjust=%s)",
        symbol, frequency, offset, adjust,
    )
    client = self._get_client(adjust)
    return self._call(
        "get_kline",
        client.bars,
        symbol=symbol,
        frequency=frequency,
        start=start,
        offset=offset,
    )


# 同时修改 get_sector_kline 也支持复权：
def get_sector_kline(
    self,
    sector_code: str,
    frequency: int = 9,
    start: int = 0,
    offset: int = 800,
    adjust: str = "none",
) -> pd.DataFrame:
    """
    获取行业/概念板块指数 K 线

    Args:
        sector_code: 板块代码，如 '880471'
        frequency: K 线周期
        start: 起始位置（0=最新）
        offset: 获取条数
        adjust: 复权方式（板块指数一般不复权，参数保留以备后用）
    """
    self.limiter.wait()
    logger.info("获取板块 K 线: %s (frequency=%d)", sector_code, frequency)
    client = self._get_client(adjust)
    return self._call(
        "get_sector_kline",
        client.bars,
        symbol=sector_code,
        frequency=frequency,
        start=start,
        offset=offset,
    )
```

---

## 6. akshare 新增：市场宽度数据

**文件**：`stoke/sources/akshare_source.py`（修改）

**改动点**：新增涨跌家数、市场成交额统计接口。

```python
# 在 AKShareSource 类中新增方法

# ==================== 市场宽度 ====================

@retry_on_failure()
def get_market_breadth(self) -> pd.DataFrame:
    """
    市场宽度数据：上证/深证涨跌家数

    Returns:
        DataFrame，含 日期、上涨家数、下跌家数、平盘家数 等列
    """
    self.limiter.wait()
    logger.info("获取市场宽度数据")
    return ak.stock_zh_index_daily(symbol="sh000001")


@retry_on_failure()
def get_market_volume(self) -> pd.DataFrame:
    """
    沪深两市每日总成交额

    Returns:
        DataFrame，含 日期、上证成交额、深证成交额、沪深总成交额 等列
    """
    self.limiter.wait()
    logger.info("获取市场成交额数据")
    # 取上证指数日线数据中包含成交额
    return ak.stock_zh_index_daily(symbol="sh000001")
```

---

## 7. akshare 新增：个股估值数据

**文件**：`stoke/sources/akshare_source.py`（修改）

**改动点**：新增个股 PE/PB 等核心财务指标接口。

**备选方案**（按优先级排列）：
1. `ak.stock_a_lg_indicator(symbol)` — 腾讯财经个股指标（PE/PB/ROE/营收增速），推荐首选
2. `ak.stock_yjbb_em(symbol)` — 东财业绩报表，备用
3. `ak.stock_financial_analysis_indicator(symbol)` — 东财财务分析指标，备用

```python
# 在 AKShareSource 类中新增方法

# ==================== 个股估值 ====================

@retry_on_failure()
def get_stock_indicator(self, symbol: str) -> pd.DataFrame:
    """
    个股核心指标：PE、PB、ROE、EPS、营收增速等

    数据来源：腾讯财经（通过 akshare 封装）

    Args:
        symbol: 股票代码，如 '000001'

    Returns:
        DataFrame，含 股票代码、市盈率、市净率、ROE、每股收益、
        营业收入同比增长率、净利润同比增长率 等列
    """
    self.limiter.wait()
    logger.info("获取个股核心指标: %s", symbol)
    return ak.stock_a_lg_indicator(symbol=symbol)
```

**验证方法**：
```bash
uv run python3 -c "
from stoke.sources.akshare_source import AKShareSource
a = AKShareSource()
df = a.get_stock_indicator('000001')
print(df.head(20).to_string())
"
```

**如果 `stock_a_lg_indicator` 不可用**，尝试备选：
```python
# 备选方案（注释掉，按需启用）
# return ak.stock_yjbb_em(symbol=symbol)
```

---

## 8. akshare 新增：行业资金流 + 行业排名

**文件**：`stoke/sources/akshare_source.py`（修改）

**改动点**：新增行业涨跌幅排名 + 行业资金流向接口。

```python
# 在 AKShareSource 类中新增方法

# ==================== 行业轮动数据 ====================

@retry_on_failure()
def get_sector_rank(self) -> pd.DataFrame:
    """
    当日行业板块涨跌幅排名

    数据来源：同花顺

    Returns:
        DataFrame，含 行业名称、涨跌幅、领涨股 等列
    """
    self.limiter.wait()
    logger.info("获取行业涨跌幅排名")
    return ak.stock_board_industry_index_ths()


@retry_on_failure()
def get_sector_fund_flow(self) -> pd.DataFrame:
    """
    行业资金流入流出排名

    数据来源：东方财富

    Returns:
        DataFrame，含 行业名称、主力净流入、超大单净流入 等列
    """
    self.limiter.wait()
    logger.info("获取行业资金流排名")
    return ak.stock_sector_fund_flow_rank()
```

**验证方法**：
```bash
uv run python3 -c "
from stoke.sources.akshare_source import AKShareSource
a = AKShareSource()
rank = a.get_sector_rank()
print('=== 行业涨跌幅排名（前10名）===')
print(rank.head(10).to_string())

fund = a.get_sector_fund_flow()
print()
print('=== 行业资金流排名 ===')
print(fund.head(10).to_string())
"
```

**如果 `stock_sector_fund_flow_rank` 不可用**，尝试备选 `ak.stock_sector_fund_flow_summary()`。

---

## 9. akshare 修改：时点规整 — 日期默认用最近交易日

**文件**：`stoke/sources/akshare_source.py`（修改）

**改动点**：`get_limit_up_pool`、`get_strong_stocks`、`get_limit_down_pool` 中 `date` 默认值改用交易日历。

当前代码问题：
```python
# ❌ 当前：datetime.now() 周六也会返回日期
if date is None:
    date = datetime.now().strftime("%Y%m%d")
```

修改为：
```python
# ✅ 修改后：自动回退到最近交易日
from stoke.calendar import today_str  # 顶部新增导入

if date is None:
    date = today_str()
```

**涉及的方法**（共 3 处）：
1. `get_limit_up_pool` (~L103-L104)
2. `get_strong_stocks` (~L124-L125)
3. `get_limit_down_pool` (~L382-L383)

---

## 10. 限流器微调：抖动改为减法模式

**文件**：`stoke/rate_limiter.py`（修改）

**问题**：当前逻辑在 `elapsed < interval` 时额外加 0.1~0.5 秒抖动，导致实际间隔总是 > interval，akshare 的 5 秒变成 5.1~5.5 秒，10 次请求累积多等 1~5 秒。

**改动**：将额外抖动改为内部消化的随机因子，确保平均间隔 ≈ interval：

```python
# 修改 wait() 方法中的抖动逻辑
# 当前（L31-L33）：
#   sleep_time = self.interval - elapsed + random.uniform(0.1, 0.5)

# 改为：抖动在 interval 范围内消化，不超过 interval
def wait(self):
    """等待足够的时间以确保满足间隔要求"""
    if self.interval <= 0:
        return

    current_time = time.time()
    elapsed = current_time - self.last_request_time

    if elapsed < self.interval:
        # 抖动在剩余等待时间内消化，不额外延长
        remaining = self.interval - elapsed
        jitter = random.uniform(-0.3, 0.3) * min(remaining, 1.0)
        sleep_time = max(0, remaining + jitter)
        logger.debug("限流等待 %.2f 秒", sleep_time)
        time.sleep(sleep_time)

    self.last_request_time = time.time()
```

---

## 11. 重试逻辑扩展：覆盖空 DataFrame

**文件**：`stoke/utils.py`（修改）

**问题**：`retry_on_failure` 只重试网络异常，但 akshare 有时返回空 DataFrame 而非抛异常，导致发现层拿到空数据后误判。

**改动**：增加可选参数，允许空 DataFrame 也触发重试：

```python
# 在 retry_on_failure 签名中增加 retry_on_empty 参数

def retry_on_failure(max_retries: int = 3, base_delay: float = 1.0,
                     retry_on_empty: bool = False):
    """
    自动重试装饰器

    Args:
        max_retries: 最多重试次数
        base_delay: 首次重试前等待秒数
        retry_on_empty: 是否在返回空 DataFrame 时也重试
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            import pandas as pd
            last_exc = None
            for attempt in range(max_retries):
                try:
                    result = func(*args, **kwargs)
                    # 空 DataFrame 检查
                    if retry_on_empty and isinstance(result, pd.DataFrame) and len(result) == 0:
                        if attempt < max_retries - 1:
                            delay = base_delay * (2 ** attempt)
                            logger.warning(
                                "%s 返回空数据(第 %d/%d 次)，%.1f 秒后重试",
                                func.__name__, attempt + 1, max_retries, delay,
                            )
                            time.sleep(delay)
                            continue
                    return result
                except _RETRYABLE as e:
                    last_exc = e
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            "%s 失败(第 %d/%d 次): %s，%.1f 秒后重试",
                            func.__name__, attempt + 1, max_retries, e, delay,
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            "%s 已重试 %d 次，放弃: %s",
                            func.__name__, max_retries, e,
                        )
                        raise
                except Exception:
                    raise
            raise last_exc
        return wrapper
    return decorator
```

---

## 12. client.py 同步新增方法

**文件**：`stoke/client.py`（修改）

**改动点**：在 `Stoke` 类中新增透传方法，与以上新增接口一一对应。

**需新增的方法清单**（按分组）：

```python
# ==================== 板块行情（mootdx） ====================

def sector_kline(
    self, sector_code: str, frequency: int = 9,
    start: int = 0, offset: int = 800, adjust: str = "none",
) -> pd.DataFrame:
    """行业/概念板块指数 K 线"""
    return self.mootdx.get_sector_kline(sector_code, frequency, start, offset, adjust)

def sector_members(self, sector_code: str) -> pd.DataFrame:
    """板块成分股列表"""
    return self.mootdx.get_sector_members(sector_code)


# ==================== K 线复权 ====================

def kline_adjusted(
    self, symbol: str, frequency: int = 9,
    start: int = 0, offset: int = 800, adjust: str = "qfq",
) -> pd.DataFrame:
    """复权 K 线（默认前复权）"""
    return self.mootdx.get_kline(symbol, frequency, start, offset, adjust)


# ==================== 市场宽度（akshare） ====================

def market_breadth(self) -> pd.DataFrame:
    """市场涨跌家数"""
    return self.akshare.get_market_breadth()

def market_volume(self) -> pd.DataFrame:
    """沪深两市成交额"""
    return self.akshare.get_market_volume()


# ==================== 个股估值（akshare） ====================

def stock_indicator(self, symbol: str) -> pd.DataFrame:
    """个股核心指标：PE/PB/ROE"""
    return self.akshare.get_stock_indicator(symbol)


# ==================== 行业轮动（akshare） ====================

def sector_rank(self) -> pd.DataFrame:
    """行业涨跌幅排名"""
    return self.akshare.get_sector_rank()

def sector_fund_flow(self) -> pd.DataFrame:
    """行业资金流排名"""
    return self.akshare.get_sector_fund_flow()
```

**插入位置**：建议在各分组注释区间末尾插入，保持代码整洁。

---

## 13. 全量验证

完成以上所有修改后，逐步验证：

```bash
# 1. 交易日历
uv run python3 -c "
from stoke.calendar import is_trading_day, today_str, prev_trading_day
print('今天是交易日？', is_trading_day())
print('最近交易日:', today_str())
print('上一交易日:', prev_trading_day())
"

# 2. 行业板块 K 线
uv run python3 -c "
from stoke import Stoke
s = Stoke()
df = s.sector_kline('880471')
print('银行板块K线:', df.tail(5)[['open','close','high','low']].to_string())
"

# 3. 市场宽度
uv run python3 -c "
from stoke import Stoke
s = Stoke()
df = s.market_breadth()
print('市场宽度(最新5行):')
print(df.tail(5).to_string())
"

# 4. 个股估值
uv run python3 -c "
from stoke import Stoke
s = Stoke()
df = s.stock_indicator('000001')
print('平安银行核心指标:')
print(df.to_string())
"

# 5. 行业排名
uv run python3 -c "
from stoke import Stoke
s = Stoke()
rank = s.sector_rank()
print('行业涨跌幅排名(前10):')
print(rank.head(10).to_string())
"

# 6. 复权K线
uv run python3 -c "
from stoke import Stoke
s = Stoke()
raw = s.kline('000001', offset=5)
adj = s.kline_adjusted('000001', offset=5)
print('不复权最后5条 close:')
print(raw[['close']].tail(5).to_string())
print()
print('前复权最后5条 close:')
print(adj[['close']].tail(5).to_string())
"

# 7. 跨平台验收
uv run python3 tests/test_cross_platform.py
```

---

## 实施顺序建议

```
第 1 步：任务 2（异常体系）+ 任务 3（交易日历）
          → 这两个是纯新建文件，无依赖，先建好

第 2 步：任务 4（行业板块）+ 任务 5（K线复权）
          → mootdx_source.py 修改，不走网络，立刻验证

第 3 步：任务 6（市场宽度）+ 任务 7（个股估值）+ 任务 8（行业排名）
          → akshare_source.py 修改，注意 5 秒限流，慢慢测

第 4 步：任务 1（规范化层）
          → 纯新建，最后建立，不影响已有功能

第 5 步：任务 9（时点规整）+ 任务 10（抖动）+ 任务 11（重试）
          → 小修改，快速过

第 6 步：任务 12（client.py）+ 任务 13（验证）
          → 汇总 + 全量回归
```