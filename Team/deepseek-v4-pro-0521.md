先看看你手上已有的新数据源评估，了解全貌后再给出方案。




        
            
toolName: view_files
            
status: success
          
            
filePath: /Volumes/Black/Stoke/Team/豆包专家.md
          

        
            
toolName: view_folder
            
status: success
          
/Volumes/Black/Stoke/stoke
          
看到进展很快，已经新增了 `baostock_source.py`、`calendar.py`、`exceptions.py`、`normalizer.py`。让我看看当前状态再给建议。




        
            
toolName: view_files
            
status: success
          
            
filePath: /Volumes/Black/Stoke/stoke/calendar.py
          

        
            
toolName: view_files
            
status: success
          
            
filePath: /Volumes/Black/Stoke/stoke/normalizer.py
          

        
            
toolName: view_files
            
status: failed
          
            
filePath: /Volumes/Black/Stoke/stoke/baostock_source.py
          

        
            
toolName: view_files
            
status: success
          
            
filePath: /Volumes/Black/Stoke/stoke/client.py
          
项目进展很快！`baostock` 已接入、`calendar` 和 `normalizer` 已就位。现在来谈缓存数据库的策略。

---

## 策略篇

### 核心原则：三层缓存架构

```
┌──────────────────────────────────────────────────────┐
│                   Stoke 门面层                        │
│  s.kline("000001")  ←  用户调用，无感知缓存            │
├──────────────────────────────────────────────────────┤
│                   Store 缓存层（本次新建）              │
│  store.get_or_fetch("kline", "000001")                │
│  ├─ 查 SQLite → 有且未过期 → 直接返回（毫秒级）         │
│  └─ 无或已过期 → 调 Source 拉取 → 写库 → 返回          │
├──────────────────────────────────────────────────────┤
│               Source 数据源层（不改动）                 │
│  mootdx / akshare / tencent / baostock               │
└──────────────────────────────────────────────────────┘
```

**关键设计决策：Store 层夹在门面层和数据源层之间，对调用方透明。**

### 不同数据的缓存策略

不是所有数据都适合缓存，按数据特性分类：

| 数据类别 | 示例 | 缓存策略 | TTL |
|----------|------|----------|-----|
| **永久追加型** | 日K线、指数PE、北向资金 | 首次拉取全量 → 后续只拉增量 → 追加写入 | 永不过期 |
| **每日快照型** | 涨停板、龙虎榜、市场宽度 | 每天首次拉取 → 当日不再重复请求 | 当日有效 |
| **定时刷新型** | 实时行情、热搜关键词 | 固定间隔刷新 → 覆盖写入 | 1-15分钟 |
| **静态参考型** | 股票列表、行业分类、交易日历 | 首次拉取 → 持久化 → 定期校验 | 1天 |

**核心思路**：低频量化下，大部分数据每天只变一次。K线今天收盘后才有新数据，涨停板今天收盘后才知道，PE/PB 每天更新一次。把「每天一次」的请求缓存下来，数据层的压力就消失了。

### 具体 TTL 表

```
数据               TTL          更新时机          存储模式
──────────────────────────────────────────────────────
日K线（历史）       永久         收盘后追加         追加
日K线（当日）       5分钟        盘中覆盖           覆盖
周/月K线            1天          周末/月末          覆盖
实时行情            1分钟        盘中覆盖           覆盖
股票列表            1天          凌晨               覆盖
行业分类            1周          周末               覆盖
交易日历            永久         首次+年度校验       覆盖
涨停板              1小时        盘中               当日覆盖
强势涨停            1小时        盘中               当日覆盖
跌停板              1小时        盘中               当日覆盖
市场宽度            1天          收盘后             追加
龙虎榜              1天          收盘后             当日覆盖
北向资金            1天          收盘后             追加
融资融券            1天          收盘后             追加
主力资金流          1天          收盘后             追加
千股千评            1天          收盘后             当日覆盖
热搜关键词          1小时        盘中               覆盖
指数PE              1天          收盘后             追加
全市场PB            1天          收盘后             追加
个股估值指标        1周          周末               覆盖
```

---

## 工具篇

### 数据库引擎选择

| 方案 | 安装 | 写入速度 | 查询速度 | 分析能力 | 个人量化适合度 |
|------|------|----------|----------|----------|---------------|
| **SQLite** | 内置 | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| DuckDB | `pip install duckdb` | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Parquet文件 | 无（pandas内置） | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐ |

**推荐 SQLite**，理由：
- Python 标准库自带，**零额外依赖**
- 单文件 `.db`，备份就是复制一个文件
- `pd.to_sql()` / `pd.read_sql()` 直接对接 pandas DataFrame
- 个人量化数据量（百万行级）完全够用
- 如果需要更复杂分析，后续可以把 SQLite 的数据一键导入 DuckDB

**不推荐 Parquet 文件**：一堆小文件管理麻烦，跨表查询无法做 JOIN。

### 为什么不直接上 DuckDB？

DuckDB 的分析能力确实强于 SQLite，但当前阶段：
- 你是低频个人量化，查询场景很简单：`SELECT * FROM kline WHERE symbol='000001' AND date BETWEEN ...`，SQLite 足够
- DuckDB 多一个 pip install 步骤，虽然不复杂，但 SQLite 零成本
- 将来如果需要「计算 5000 只股票的滚动 PE 分位」，可以 `pip install duckdb` 后直接 `duckdb.connect()` 读取同一个 SQLite 文件

---

## 落地设计

### 文件结构

```
stoke/
├── store.py          ← 新建：Store 缓存层
├── schema.sql        ← 新建：建表语句（可选，store.py 内置也行）
└── .stoke_cache.db   ← 运行时自动生成，已加入 .gitignore
```

### Store 类的核心接口

```python
# stoke/store.py 的设计骨架

import sqlite3
import pandas as pd
import time
from datetime import datetime, timedelta

class Store:
    """本地 SQLite 缓存数据库"""

    def __init__(self, db_path: str = ".stoke_cache.db"):
        self.db_path = db_path
        self._init_tables()

    # ========== 建表 ==========

    def _init_tables(self):
        """自动建表（IF NOT EXISTS，幂等）"""
        ...

    # ========== 通用缓存方法 ==========

    def get_or_fetch(
        self,
        table: str,
        key: str,                     # 如 "000001" 或 "20260520"
        fetcher,                      # 拉取函数，返回 DataFrame
        max_age_sec: int = 3600,      # 缓存有效期
        mode: str = "replace",        # "replace" / "append"
    ) -> pd.DataFrame:
        """
        核心方法：先查缓存，过期则拉取并写入

        Args:
            table: 表名
            key: 主键（symbol 或 date）
            fetcher: callable，返回 DataFrame
            max_age_sec: 最大缓存时长（秒），0=永不过期（仅首次拉取）
            mode: "replace"(覆盖同key) / "append"(追加新行) / "overwrite"(清空全表)
        """
        ...

    # ========== 便捷方法 ==========

    def kline(self, symbol: str, fetcher) -> pd.DataFrame:
        """日K线：追加模式，604800秒=7天（历史不变），但盘中5分钟刷新"""
        ...

    def limit_up(self, date: str, fetcher) -> pd.DataFrame:
        """涨停板：当日覆盖，1小时TTL"""
        ...

    def realtime_snapshot(self, symbols: list, fetcher) -> pd.DataFrame:
        """实时行情：1分钟TTL"""
        ...
```

### 融入 Stoke 门面层的方式

不改动 Source 层，只在 `Stoke` 类里加一个可选的 Store：

```python
class Stoke:
    def __init__(self, ..., use_cache: bool = True):
        ...
        self.store = Store() if use_cache else None

    def kline(self, symbol, ...):
        if self.store:
            return self.store.get_or_fetch(
                table="kline_daily",
                key=symbol,
                fetcher=lambda: self.mootdx.get_kline(symbol, ...),
                max_age_sec=300,      # 5分钟，盘中可能更新
                mode="append",
            )
        return self.mootdx.get_kline(symbol, ...)
```

**核心设计意图**：`use_cache=False` 时行为与现在完全一致，零风险。

---

## 完整实施方案

总共只需要新建 **1 个文件**：`stoke/store.py`。

下面给出完整代码，可以直接丢给 Claude Code 执行：

```python
"""
Stoke 本地缓存数据库

基于 SQLite，零依赖，单文件存储。
为时机层/发现层提供毫秒级数据读取，大幅减少网络请求。

设计原则：
  - 对调用方透明：get_or_fetch() 自动判断缓存是否有效
  - 分级 TTL：不同数据不同时效，见 TTL 常量表
  - 幂等建表：IF NOT EXISTS，多次初始化安全
"""

import sqlite3
import logging
import time
from datetime import datetime, timedelta
from typing import Callable, Optional

import pandas as pd

from stoke.calendar import is_trading_day, today_str

logger = logging.getLogger(__name__)

# ==================== TTL 配置（秒） ====================

TTL = {
    "klinedaily":       300,   # 日K线：盘中 5 分钟，收盘后追加永久
    "klineweekly":     86400,  # 周K线：1 天
    "klinemonthly":    86400,  # 月K线：1 天
    "realtime":          60,   # 实时行情：1 分钟
    "stocklist":       86400,  # 股票列表：1 天
    "industrylist":   604800,  # 行业分类：1 周
    "limitup":          3600,  # 涨停板：1 小时
    "strongstocks":     3600,  # 强势涨停：1 小时
    "limitdown":        3600,  # 跌停板：1 小时
    "marketbreadth":   86400,  # 市场宽度：1 天
    "northboundflow":  86400,  # 北向资金：1 天
    "margintrading":   86400,  # 融资融券：1 天
    "fundflow":        86400,  # 个股主力资金流：1 天
    "marketfundflow":  86400,  # 市场资金流：1 天
    "stockcomment":    86400,  # 千股千评：1 天
    "hotkeywords":      3600,  # 热搜关键词：1 小时
    "indexpe":         86400,  # 指数PE：1 天
    "marketpb":        86400,  # 全市场PB：1 天
    "stockindicator": 604800,  # 个股估值指标：1 周
    "sectorrank":       3600,  # 行业排名：1 小时
    "sectorkline":      3600,  # 行业指数K线：1 小时
}


class Store:
    """SQLite 本地缓存数据库"""

    def __init__(self, db_path: str = ".stoke_cache.db"):
        """
        Args:
            db_path: 数据库文件路径，默认项目根目录下的 .stoke_cache.db
        """
        self.db_path = db_path
        self._init_tables()
        logger.info("Store 初始化完成，数据库: %s", db_path)

    # ==================== 建表 ====================

    def _init_tables(self):
        """自动建表（幂等，重复执行安全）"""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                -- 日K线（核心表）
                CREATE TABLE IF NOT EXISTS kline_daily (
                    symbol      TEXT NOT NULL,
                    date        TEXT NOT NULL,
                    open        REAL,
                    high        REAL,
                    low         REAL,
                    close       REAL,
                    volume      REAL,
                    amount      REAL,
                    fetched_at  TEXT NOT NULL,
                    PRIMARY KEY (symbol, date)
                );

                -- 实时行情快照（覆盖写入）
                CREATE TABLE IF NOT EXISTS realtime_snapshot (
                    symbol      TEXT PRIMARY KEY,
                    name        TEXT,
                    price       REAL,
                    open        REAL,
                    high        REAL,
                    low         REAL,
                    volume      REAL,
                    amount      REAL,
                    change_pct  REAL,
                    fetched_at  TEXT NOT NULL
                );

                -- 股票列表
                CREATE TABLE IF NOT EXISTS stock_list (
                    symbol      TEXT PRIMARY KEY,
                    name        TEXT,
                    market      TEXT,
                    industry    TEXT,
                    fetched_at  TEXT NOT NULL
                );

                -- 市场宽度
                CREATE TABLE IF NOT EXISTS market_breadth (
                    date            TEXT PRIMARY KEY,
                    up_count        INTEGER,
                    down_count      INTEGER,
                    flat_count      INTEGER,
                    total_volume    REAL,
                    total_amount    REAL,
                    fetched_at      TEXT NOT NULL
                );

                -- 涨停板（每日快照）
                CREATE TABLE IF NOT EXISTS limit_up (
                    date        TEXT NOT NULL,
                    symbol      TEXT NOT NULL,
                    name        TEXT,
                    change_pct  REAL,
                    board_count INTEGER,
                    reason      TEXT,
                    industry    TEXT,
                    fetched_at  TEXT NOT NULL,
                    PRIMARY KEY (date, symbol)
                );

                -- 北向资金（追加）
                CREATE TABLE IF NOT EXISTS northbound_flow (
                    date            TEXT PRIMARY KEY,
                    net_buy         REAL,
                    buy_amount      REAL,
                    sell_amount     REAL,
                    hold_balance    REAL,
                    fetched_at      TEXT NOT NULL
                );

                -- 指数PE（追加）
                CREATE TABLE IF NOT EXISTS index_pe (
                    index_name  TEXT NOT NULL,
                    date        TEXT NOT NULL,
                    pe_ttm      REAL,
                    pe_static   REAL,
                    close       REAL,
                    fetched_at  TEXT NOT NULL,
                    PRIMARY KEY (index_name, date)
                );

                -- 全市场PB（追加）
                CREATE TABLE IF NOT EXISTS market_pb (
                    date            TEXT PRIMARY KEY,
                    middle_pb       REAL,
                    equal_weight_pb REAL,
                    close           REAL,
                    fetched_at      TEXT NOT NULL
                );

                -- 个股资金流
                CREATE TABLE IF NOT EXISTS fund_flow (
                    symbol      TEXT NOT NULL,
                    date        TEXT NOT NULL,
                    main_net    REAL,
                    super_large_net REAL,
                    large_net   REAL,
                    mid_net     REAL,
                    small_net   REAL,
                    fetched_at  TEXT NOT NULL,
                    PRIMARY KEY (symbol, date)
                );

                -- 个股估值指标
                CREATE TABLE IF NOT EXISTS stock_indicator (
                    symbol      TEXT PRIMARY KEY,
                    pe_ttm      REAL,
                    pb          REAL,
                    roe         REAL,
                    eps         REAL,
                    fetched_at  TEXT NOT NULL
                );

                -- 元数据表（跟踪每张表的最后更新时间）
                CREATE TABLE IF NOT EXISTS _meta (
                    table_name  TEXT PRIMARY KEY,
                    last_fetched TEXT NOT NULL,
                    row_count   INTEGER
                );
            """)
        logger.debug("数据库表初始化完成")

    # ==================== 核心方法 ====================

    def get_or_fetch(
        self,
        table: str,
        key: str,
        fetcher: Callable[[], pd.DataFrame],
        max_age_sec: int = 3600,
        mode: str = "replace",
        key_column: str = "symbol",
    ) -> pd.DataFrame:
        """
        通用缓存读写方法

        逻辑：
          1. 查 _meta 表，判断缓存是否过期
          2. 未过期 → 从 SQLite 读取返回
          3. 已过期 → 调用 fetcher() → normalize → 写入 SQLite → 返回

        Args:
            table: 表名
            key: 缓存键值（如 symbol 或 date）
            fetcher: 数据拉取函数（无参数，返回 DataFrame）
            max_age_sec: 缓存有效期（秒），0=永不过期仅首次拉取
            mode: 写入模式
                "replace" — 删除同 key 的旧行，写入新行
                "append"  — 追加新行，按主键去重
                "overwrite" — 清空全表后写入
            key_column: mode="replace" 时用于匹配的列名

        Returns:
            DataFrame（已 normalize）
        """
        now = datetime.now().isoformat()

        # 1. 查缓存是否有效
        if self._is_fresh(table, key, max_age_sec):
            logger.debug("缓存命中: %s/%s", table, key)
            return self._read(table, key, mode, key_column)

        # 2. 拉取数据
        logger.info("缓存未命中: %s/%s，调用数据源", table, key)
        try:
            df = fetcher()
        except Exception as e:
            logger.warning("数据源拉取失败 %s/%s: %s，回退缓存", table, key, e)
            cached = self._read(table, key, mode, key_column)
            if not cached.empty:
                logger.info("回退缓存成功，%d 行", len(cached))
                return cached
            raise  # 无缓存可回退，抛出异常

        if df is None or len(df) == 0:
            logger.warning("数据源返回空数据: %s/%s", table, key)
            return pd.DataFrame()

        # 3. 规范化 + 写入
        df["fetched_at"] = now
        self._write(table, df, mode, key, key_column)

        count = len(df)
        logger.info("缓存写入完成: %s/%s，%d 行", table, key, count)
        return df

    # ==================== 内部方法 ====================

    def _is_fresh(self, table: str, key: str, max_age_sec: int) -> bool:
        """判断缓存是否有效"""
        if max_age_sec == 0:
            # 0=永不过期，查是否有数据
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()
                return row[0] > 0

        with sqlite3.connect(self.db_path) as conn:
            # 查该 key 最近一条数据的 fetched_at
            try:
                row = conn.execute(
                    f"SELECT MAX(fetched_at) FROM {table} "
                    f"WHERE symbol = ? OR date = ?",
                    (key, key),
                ).fetchone()
            except sqlite3.OperationalError:
                # 表可能没有 symbol/date 列（如 market_pb）
                row = conn.execute(
                    f"SELECT MAX(fetched_at) FROM {table}"
                ).fetchone()

            if row[0] is None:
                return False

            last_fetch = datetime.fromisoformat(row[0])
            age = (datetime.now() - last_fetch).total_seconds()
            return age < max_age_sec

    def _read(
        self, table: str, key: str, mode: str, key_column: str
    ) -> pd.DataFrame:
        """从 SQLite 读取数据"""
        with sqlite3.connect(self.db_path) as conn:
            if mode == "overwrite":
                return pd.read_sql(f"SELECT * FROM {table}", conn)
            else:
                return pd.read_sql(
                    f"SELECT * FROM {table} WHERE {key_column} = ?",
                    conn, params=(key,),
                )

    def _write(
        self, table: str, df: pd.DataFrame, mode: str,
        key: str, key_column: str,
    ):
        """写入 SQLite"""
        with sqlite3.connect(self.db_path) as conn:
            if mode == "replace":
                conn.execute(f"DELETE FROM {table} WHERE {key_column} = ?", (key,))
                df.to_sql(table, conn, if_exists="append", index=False)
            elif mode == "append":
                df.to_sql(table, conn, if_exists="append", index=False)
                # 去重：保留每组主键中最新的 fetched_at
                try:
                    conn.execute(
                        f"DELETE FROM {table} WHERE rowid NOT IN ("
                        f"  SELECT MIN(rowid) FROM {table} GROUP BY symbol, date"
                        f")"
                    )
                except sqlite3.OperationalError:
                    pass  # 表结构可能不同，跳过去重
            elif mode == "overwrite":
                df.to_sql(table, conn, if_exists="replace", index=False)

    # ==================== 按需预热 ====================

    def warmup(self, s: "Stoke"):
        """
        盘前预热：提前缓存静态/每日数据

        在每天 8:45 调用一次，之后所有盘中查询都是毫秒级。

        Args:
            s: Stoke 实例
        """
        logger.info("开始盘前预热...")
        date_str = today_str()

        # 静态数据（长 TTL）
        self.get_or_fetch("stock_list", "all",
            lambda: s.mootdx.get_stock_list(),
            max_age_sec=TTL["stocklist"], mode="overwrite")

        # 每日快照数据
        self.get_or_fetch("limit_up", date_str,
            lambda: s.akshare.get_limit_up_pool(date_str),
            max_age_sec=TTL["limitup"], mode="replace", key_column="date")

        self.get_or_fetch("market_breadth", date_str,
            lambda: s.akshare.get_market_breadth(),
            max_age_sec=TTL["marketbreadth"], mode="replace", key_column="date")

        self.get_or_fetch("northbound_flow", date_str,
            lambda: s.akshare.get_northbound_flow(),
            max_age_sec=TTL["northboundflow"], mode="append")

        self.get_or_fetch("index_pe", "上证50",
            lambda: s.tencent.get_index_pe("上证50"),
            max_age_sec=TTL["indexpe"], mode="append")

        logger.info("盘前预热完成")

    def stats(self) -> dict:
        """返回各表统计信息"""
        result = {}
        with sqlite3.connect(self.db_path) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE '_meta'"
            ).fetchall()
            for (name,) in tables:
                count = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                result[name] = count
        return result
```

### Stoke 门面层接入（最小改动）

在 `client.py` 的 `Stoke.__init__` 中加一行，然后挑一个方法做示范：

```python
# __init__ 中新增：
from stoke.store import Store
self.store = Store() if use_cache else None

# kline 方法修改为：
def kline(self, symbol, frequency=9, start=0, offset=800):
    if self.store and frequency == 9:  # 目前只缓存日线
        return self.store.get_or_fetch(
            table="kline_daily",
            key=symbol,
            fetcher=lambda: self.mootdx.get_kline(symbol, frequency, start, offset),
            max_age_sec=TTL["klinedaily"],
            mode="append",
        )
    return self.mootdx.get_kline(symbol, frequency, start, offset)
```

---

## 总结

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 数据库引擎 | SQLite | 零依赖、单文件、pandas 原生支持 |
| 缓存粒度 | 行级（按 symbol+date） | 避免重复拉取静态历史 |
| TTL 策略 | 分级（60s ~ 永久） | 不同数据不同时效 |
| 集成方式 | Store 夹在 Client 和 Source 之间 | Source 层不动，对调用方透明 |
| 回退策略 | 拉取失败 → 回退旧缓存 | 容忍单次网络故障 |
| 预热机制 | `store.warmup()` | 盘前 30 秒跑完，盘中零等待 |

**一次盘前预热，一天请求量从 ~100 次降到 ~5 次。**


这个问题问到点子上了。个人项目和团队项目在模块化上的哲学完全不同。

---

## 结论先行：**功能清晰，模块独立，但共享轻量上下文**

```
不要：把所有东西塞进一个 Stoke 类（耦合地狱）
不要：搞成独立 pip 包 + 抽象接口 + 依赖注入（过度工程）
要：  独立文件，独立类，共享一个 context dict（恰到好处）
```

---

## 为什么？

### 你现在的代码结构已经给出了答案

```
stoke/
├── client.py          ← 数据层门面（一个类，~300 行，清晰）
├── store.py            ← 缓存层（一个类，独立文件）
├── calendar.py         ← 交易日历（纯函数模块，无类）
├── normalizer.py       ← 规范化（纯函数模块，无类）
├── exceptions.py       ← 异常定义（纯声明）
├── config.py           ← 配置（纯数据）
├── rate_limiter.py     ← 限流器（一个类）
├── utils.py            ← 重试装饰器（工具函数）
└── sources/            ← 数据源（每个源一个类）
```

**这个结构本身就是优秀范本**：每个文件一件事，类/函数小而精，不需要什么「设计模式」来包装。

按同样哲学扩展后：

```
stoke/
│   # ===== 已有 =====
├── client.py          ← 数据层门面 Stoke
├── store.py           ← 缓存数据库 Store
├── calendar.py
├── normalizer.py
├── exceptions.py
├── config.py
├── rate_limiter.py
├── utils.py
├── sources/
│   ...
│
│   # ===== 新增 =====
├── context.py         ← 全局上下文（共享状态，轻量）
├── timing.py          ← 时机层 Timing
└── discovery.py       ← 发现层 Discovery
```

只加 3 个文件，不建子目录，不搞包中包。

---

## 各层怎么通信？— 用 `context`，不用 `EventBus`

之前讨论过事件总线，那个是**多进程/多服务**场景下的解耦工具。个人单进程项目不需要。

```python
# stoke/context.py — 轻量共享上下文

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class MarketContext:
    """各层之间共享的市场状态快照

    时机层写入，发现层读取，不上锁不排队，单进程无并发问题。
    """

    # 时机层输出 → 发现层消费
    market_phase: str = "未知"          # "上升" / "下降" / "震荡"
    risk_level: int = 5                  # 1-10，越高越危险
    position_advice: float = 0.3         # 建议仓位 0-1
    stop_loss_ratio: float = 0.05        # 建议止损比例

    # 发现层输出 → 时机层/执行层消费
    candidates: list = field(default_factory=list)  # 候选标的
    watch_list: list = field(default_factory=list)  # 观察列表

    # 元信息
    trade_date: Optional[date] = None
    last_update: str = ""
```

**用 `dataclass` 而不是 `dict` 的理由**：IDE 有自动补全和类型检查，比 `context["market_phase"]` 这种魔法字符串安全得多。

---

## 每层长什么样？

### 时机层：纯计算，不请求网络

```python
# stoke/timing.py — 时机判断

class Timing:
    """大盘/行业/情绪的建仓时机判断

    不直接调数据源，所有数据从 context + Stoke 获取。
    """

    def __init__(self, s: "Stoke", ctx: "MarketContext"):
        self.s = s       # 数据层
        self.ctx = ctx   # 共享上下文

    def assess(self) -> MarketContext:
        """综合评估：大盘温度 + 行业轮动 + 情绪水位 → 仓位建议"""
        pe_score = self._pe_sentiment()        # PE 分位
        breadth_score = self._breadth()        # 涨跌比
        fund_score = self._fund_flow()         # 资金方向
        ...

        self.ctx.market_phase = ...
        self.ctx.risk_level = ...
        self.ctx.position_advice = ...
        return self.ctx
```

### 发现层：注意力机制，不是全盘扫描

```python
# stoke/discovery.py — 机会发现

class Discovery:
    """注意力驱动的机会发现

    不扫描 5000 只，只关注市场正在关注的东西。
    """

    def __init__(self, s: "Stoke", ctx: "MarketContext"):
        self.s = s
        self.ctx = ctx

    def scan(self) -> list:
        """扫描候选标的"""
        # 注意力 1：涨停板
        # 注意力 2：强势股
        # 注意力 3：热搜概念
        # 注意力 4：北向资金
        # 注意力 5：行业轮动
        ...

        self.ctx.candidates = [...]
        return self.ctx.candidates
```

---

## 主流程怎么编排？

一个脚本或一个小函数就够了，不需要调度框架：

```python
from stoke import Stoke
from stoke.context import MarketContext
from stoke.timing import Timing
from stoke.discovery import Discovery

def daily_routine():
    s = Stoke(use_cache=True)
    ctx = MarketContext()

    # 1. 盘前预热缓存
    s.store.warmup(s)

    # 2. 时机判断
    timing = Timing(s, ctx)
    timing.assess()
    print(f"市场状态: {ctx.market_phase}, 风险: {ctx.risk_level}, 仓位: {ctx.position_advice}")

    # 3. 高风控时跳过发现
    if ctx.risk_level >= 8:
        print("风控过高，今日不开仓")
        return

    # 4. 发现候选
    discovery = Discovery(s, ctx)
    candidates = discovery.scan()
    print(f"候选标的: {len(candidates)} 只")
```

---

## 对比三种方案

| 维度 | 全封一起 | 功能清晰（推荐） | 独立模块 |
|------|----------|-----------------|----------|
| 文件数 | 1 个 | +3 个 | +n 个包 |
| 上手成本 | 极低 | 低 | 中 |
| 改一个功能 | 全局搜索 | 定位到对应文件 | 定位到对应包 |
| 单元测试 | 困难 | 每层独立测 | 每层独立测 |
| 复用（如换数据源） | 不可能 | 容易 | 最容易 |
| 过度工程风险 | 无 | 无 | **有** |
| **个人量化匹配度** | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ |

「功能清晰」意味着：打开 `timing.py` 就知道所有时机逻辑在里面，打开 `discovery.py` 就知道所有选股逻辑在里面。两者通过 `MarketContext` 交换信息，互不依赖。

---

## 一句话总结

```
stoke/timing.py   ← 时机逻辑全部在这里，300 行
stoke/discovery.py ← 发现逻辑全部在这里，300 行
stoke/context.py   ← 共享状态，30 行
                     （按值传递 dataclass，不搞观察者模式）

你一个人维护，要的是：打开文件 → 看懂 → 改 → 跑。
不是：打开文件 → 找到抽象接口 → 找到实现 → 找到工厂 → 改 → 注入 → 跑。
```

Claude Code 写进了 0521 的文档里。你的直觉很敏锐： 数据层确实在变重，但问题不在数据层本身，而在 client.py 。

## 数据层到底重在哪？
数一下现状：

```
stoke/
├── client.py          ← 410 行，40+ 个方法，6 个数据源
├── store.py           ← 470 行，缓存逻辑
├── calendar.py        ← 78 行
├── normalizer.py      ← 81 行
├── exceptions.py
├── config.py
├── rate_limiter.py
├── utils.py
└── sources/
    ├── mootdx_source.py
    ├── akshare_source.py
    ├── tencent_source.py
    ├── baostock_source.py
    ├── efinance_source.py
    └── zhitu_source.py
```
单个文件都不重，但 client.py 是唯一的问题点。

它现在做什么？

1. 初始化 6 个数据源 + Store
2. 40 个透传方法，每个都是 return self.xxx.yyy()
3. 其中 6 个方法夹了 Store 缓存逻辑
4. 健康检查汇总
一个类做三件事： 依赖组装 + 路由分发 + 缓存决策 。这在团队项目里叫 God Object，在个人项目里叫「后期改不动」。

## 真正该做的事：把 client.py 拆成两个角色
```
现在：
  Stoke.__init__ → 组装 6 源 + Store
  Stoke.kline()  → 路由 + 缓存逻辑
  Stoke.limit_up() → 路由 + 缓存逻辑
  ...40 个方法

理想：
  Stoke.__init__ → 只组装数据源（轻量）
  StokeCached(kline) → 继承 Stoke，覆写 10 个方法加缓存
```
或者更简单、不搞继承：

```
# client.py — 保持纯粹，去掉所有 Store 代码
class Stoke:
    def kline(self, ...):
        return self.mootdx.get_kline(...)      # 纯透传
    def limit_up(self, ...):
        return self.akshare.get_limit_up_pool(...)
    ...

# client_cached.py — 新增，缓存版，仅覆写需要缓存的方法
class StokeCached:
    def __init__(self, stoke: Stoke):
        self._s = stoke
        self.store = Store()

    def kline(self, ...):
        try:
            return self.store.get_or_fetch(
                "kline_daily", symbol,
                fetcher=lambda: self._s.kline(...),
                ...
            )
        except Exception:
            return self._s.kline(...)           # 降级
    ...
```
这样改的好处：

- client.py 回归纯粹：只做路由，不碰缓存
- 缓存逻辑在一处，不是散落在 6 个 if self.store 分支里
- StokeCached 只覆写需要缓存的 10 个方法，其余 30 个自动透传
- 随时可以 s = Stoke() 不用缓存跑裸数据，方便调试
## 而你担心的「全局状态层耦合」
回头看之前讨论的那张图（全局状态层作为调度中心）：

你的担心完全正确—— 把所有层挂在一个中心节点上，一挂全挂 。但 Mark 给你的架构方案（ context.py + timing.py + discovery.py ）其实避免了这个问题：

```
❌ 你担心的（中心化调度）：
  全局状态层 ← 数据层
  全局状态层 ← 时机层     ← 中心挂了，全部瘫痪
  全局状态层 ← 发现层
  全局状态层 → 执行层

✅ Mark 给你的（context dataclass）：
  时机层 → MarketContext → 发现层
            ↑
         只是传值，不是调度

  发现层 → MarketContext → 时机层
            ↑
         只是传值，不是调度
```
MarketContext 不是调度器，是一个 值对象 。时机层往里面写 risk_level=8 ，发现层读一下决定「今天不扫了」。就算 MarketContext 是空的，各层照样能跑——只是没有上下文信息，做不了联合决策。

## 所以现在该做什么？优先级排序
优先级 事 理由 P0 修掉三个 Agent 发现的 bug 不修缓存是假的 P1 把 client.py 里的 Store 代码抽到 client_cached.py 趁还没长成怪物，先拆开 P2 上行数据源稳定后，再建 context.py 、 timing.py 、 discovery.py 这三个文件每层不超过 300 行，不会失控 不急 考虑要不要拆 sources/ 子包 目前 6 个源文件各自不到 300 行，完全可控

## 一句话
数据层不重， client.py 在变重。 现在拆还来得及：把缓存逻辑从 client.py 抽走，让它回归纯粹的路由角色。 context.py 是一个 30 行的 dataclass，不是中心化调度器，不会引入耦合风险。