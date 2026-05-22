"""
Stoke 本地缓存数据库

基于 SQLite，零额外依赖，单文件存储。
为时机层/发现层提供毫秒级数据读取，大幅减少对数据源的网络请求。

设计原则：
  - 对调用方透明：get_or_fetch() 自动判断缓存是否有效
  - 分级 TTL：不同数据不同时效，见 TTL 常量表
  - 幂等建表：IF NOT EXISTS，多次初始化安全
  - 拉取失败时自动回退旧缓存，容忍单次网络故障
"""

import re
import sqlite3
import logging
from datetime import datetime
from typing import Callable, Optional, List

import pandas as pd

from stoke.calendar import today_str

logger = logging.getLogger(__name__)

# ==================== TTL 配置（秒） ====================

TTL = {
    # K线
    "kline_daily":       300,   # 日K线：盘中 5 分钟刷新
    "kline_weekly":     86400,   # 周K线：1 天
    "kline_monthly":    86400,   # 月K线：1 天
    # 实时行情
    "realtime_snapshot":  60,    # 实时快照：1 分钟
    # 静态参考数据
    "stock_list":       86400,   # 股票列表：1 天
    "industry_list":   604800,   # 行业分类：1 周
    "stock_indicator": 604800,   # 个股估值指标：1 周
    # 每日快照数据（收盘后刷新一次即可）
    "market_breadth":   86400,
    "northbound_flow":  86400,
    "margin_trading":   86400,
    "fund_flow":        86400,
    "market_fund_flow": 86400,
    "index_pe":         86400,
    "market_pb":        86400,
    "dragon_tiger":     86400,
    "stock_comment":    86400,
    "market_volume":    86400,
    # 盘中高频更新（1 小时）
    "sector_rank":       3600,
    "strong_stocks":     3600,
    "hot_keywords":      3600,
    "limit_up":          3600,
    "limit_down":        3600,
    "sector_kline":      3600,
    # 永不过期（仅首次拉取）
    "permanent":            0,
}


_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

def _validate_identifier(name: str, context: str = "标识符") -> str:
    """校验 SQL 标识符（表名/列名），防止注入"""
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(f"非法{context}: {name!r}")
    return name


class Store:
    """SQLite 本地缓存数据库"""

    def __init__(self, db_path: str = ".stoke_cache.db"):
        self.db_path = db_path
        self._init_tables()
        logger.info("Store 初始化完成，数据库: %s", db_path)

    # ==================== 建表 ====================

    def _init_tables(self):
        """自动建表（幂等，多次执行安全）"""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                -- 日K线（核心表，追加模式）
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
                CREATE INDEX IF NOT EXISTS idx_kline_symbol
                    ON kline_daily(symbol);
                CREATE INDEX IF NOT EXISTS idx_kline_date
                    ON kline_daily(date);

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

                -- 市场宽度 / 上证指数日线（OHLCV）
                CREATE TABLE IF NOT EXISTS market_breadth (
                    date        TEXT PRIMARY KEY,
                    open        REAL,
                    high        REAL,
                    low         REAL,
                    close       REAL,
                    volume      REAL,
                    fetched_at  TEXT NOT NULL
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
                CREATE INDEX IF NOT EXISTS idx_limitup_date
                    ON limit_up(date);

                -- 北向资金（追加模式）
                CREATE TABLE IF NOT EXISTS northbound_flow (
                    date            TEXT PRIMARY KEY,
                    net_buy         REAL,
                    buy_amount      REAL,
                    sell_amount     REAL,
                    hold_balance    REAL,
                    fetched_at      TEXT NOT NULL
                );

                -- 指数PE（追加模式）
                CREATE TABLE IF NOT EXISTS index_pe (
                    index_name  TEXT NOT NULL,
                    date        TEXT NOT NULL,
                    pe_ttm      REAL,
                    pe_static   REAL,
                    close       REAL,
                    fetched_at  TEXT NOT NULL,
                    PRIMARY KEY (index_name, date)
                );
                CREATE INDEX IF NOT EXISTS idx_pe_index
                    ON index_pe(index_name);

                -- 全市场PB（追加模式）
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
                CREATE INDEX IF NOT EXISTS idx_fund_symbol
                    ON fund_flow(symbol);

                -- 行业板块日线
                CREATE TABLE IF NOT EXISTS sector_kline (
                    sector_name TEXT NOT NULL,
                    date        TEXT NOT NULL,
                    open        REAL,
                    high        REAL,
                    low         REAL,
                    close       REAL,
                    volume      REAL,
                    amount      REAL,
                    fetched_at  TEXT NOT NULL,
                    PRIMARY KEY (sector_name, date)
                );

                -- 龙虎榜（每日快照）
                CREATE TABLE IF NOT EXISTS dragon_tiger (
                    date            TEXT NOT NULL,
                    symbol          TEXT NOT NULL,
                    name            TEXT,
                    net_buy_amount  REAL,
                    change_pct      REAL,
                    turnover        REAL,
                    reason          TEXT,
                    fetched_at      TEXT NOT NULL,
                    PRIMARY KEY (date, symbol)
                );

                -- 千股千评（每日快照）
                CREATE TABLE IF NOT EXISTS stock_comment (
                    date        TEXT NOT NULL,
                    symbol      TEXT NOT NULL,
                    name        TEXT,
                    score       REAL,
                    main_cost   REAL,
                    focus_index REAL,
                    fetched_at  TEXT NOT NULL,
                    PRIMARY KEY (date, symbol)
                );
                CREATE INDEX IF NOT EXISTS idx_stock_comment_date
                    ON stock_comment(date);

                -- 行业排名（每日快照）
                CREATE TABLE IF NOT EXISTS sector_rank (
                    date        TEXT NOT NULL,
                    sector_name TEXT NOT NULL,
                    rank        INTEGER,
                    change_pct  REAL,
                    fetched_at  TEXT NOT NULL,
                    PRIMARY KEY (date, sector_name)
                );

                -- 强势涨停股（每日快照）
                CREATE TABLE IF NOT EXISTS strong_stocks (
                    date        TEXT NOT NULL,
                    symbol      TEXT NOT NULL,
                    name        TEXT,
                    change_pct  REAL,
                    reason      TEXT,
                    industry    TEXT,
                    fetched_at  TEXT NOT NULL,
                    PRIMARY KEY (date, symbol)
                );

                -- 热搜关键词（每日快照）
                CREATE TABLE IF NOT EXISTS hot_keywords (
                    date        TEXT NOT NULL,
                    concept_name TEXT NOT NULL,
                    symbol      TEXT,
                    heat        REAL,
                    fetched_at  TEXT NOT NULL,
                    PRIMARY KEY (date, concept_name)
                );

                -- 市场成交额（追加模式）
                CREATE TABLE IF NOT EXISTS market_volume (
                    date        TEXT PRIMARY KEY,
                    sh_close    REAL,
                    sh_change   REAL,
                    sz_close    REAL,
                    sz_change   REAL,
                    main_net    REAL,
                    fetched_at  TEXT NOT NULL
                );

                -- 交易记录（沉淀层）
                CREATE TABLE IF NOT EXISTS trades (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol          TEXT NOT NULL,
                    name            TEXT,
                    direction       TEXT NOT NULL,
                    quantity        INTEGER NOT NULL,
                    price           REAL NOT NULL,
                    strategy_name   TEXT NOT NULL,
                    order_date      TEXT NOT NULL,
                    fill_date       TEXT,
                    reason          TEXT,
                    exit_price      REAL,
                    exit_date       TEXT,
                    pnl_pct         REAL,
                    max_hold_days   INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_trades_strategy
                    ON trades(strategy_name);
                CREATE INDEX IF NOT EXISTS idx_trades_date
                    ON trades(order_date);

                -- 策略表现快照（沉淀层，每日）
                CREATE TABLE IF NOT EXISTS strategy_snapshots (
                    date            TEXT NOT NULL,
                    strategy_name   TEXT NOT NULL,
                    total_return    REAL,
                    sharpe          REAL,
                    max_drawdown    REAL,
                    win_rate        REAL,
                    trade_count     INTEGER,
                    PRIMARY KEY (date, strategy_name)
                );

                -- 元数据表（跟踪每张表的最后写入时间）
                CREATE TABLE IF NOT EXISTS _meta (
                    table_name  TEXT PRIMARY KEY,
                    last_write  TEXT NOT NULL
                );
            """)
        logger.debug("数据库 %d 张表初始化完成", self._table_count())

    # ==================== 核心方法 ====================

    def get_or_fetch(
        self,
        table: str,
        key: str,
        fetcher: Callable[[], pd.DataFrame],
        max_age_sec: int = 3600,
        mode: str = "replace",
        key_column: str = "symbol",
        column_map: Optional[dict] = None,
    ) -> pd.DataFrame:
        """
        通用缓存读写方法

        逻辑：
          1. 检查缓存是否存在且未过期
          2. 有效 → 从 SQLite 读取返回
          3. 过期/不存在 → 调用 fetcher() → 写库 → 返回
          4. fetcher 失败 → 回退旧缓存（容忍单次网络故障）

        Args:
            table: 表名
            key: 缓存键值（如 symbol 或 date）
            fetcher: 数据拉取函数（无参数，返回 DataFrame）
            max_age_sec: 缓存有效期（秒），0 = 永不过期仅首次拉取
            mode: "replace" — 删除同 key_column 的旧行，写入新行
                  "append"  — 追加新行，自动去重
                  "overwrite" — 清空全表后写入
            key_column: mode="replace" 时用于 WHERE 匹配的列名
            column_map: 源列名 → 库列名的映射 dict，如 {'代码': 'symbol', '名称': 'name'}

        Returns:
            DataFrame（已写入缓存的数据）
        """
        _validate_identifier(table, "表名")
        _validate_identifier(key_column, "列名")
        now = datetime.now().isoformat()

        # 日期 key 统一为 YYYY-MM-DD 格式（与存储格式一致）
        if key_column == "date" and isinstance(key, str) and len(key) == 8 and key.isdigit():
            key = f"{key[:4]}-{key[4:6]}-{key[6:]}"

        # 1. 缓存有效 → 直接返回（即使空也返回，不重复拉取）
        if self._is_fresh(table, key, max_age_sec, key_column):
            df = self._read(table, key, key_column, mode)
            logger.debug("缓存命中: %s/%s (%d 行)", table, key, len(df))
            return df

        # 2. 拉取数据
        logger.info("缓存未命中: %s/%s，调用数据源", table, key)
        try:
            df = fetcher()
        except Exception as e:
            logger.warning("数据源拉取失败 %s/%s: %s，尝试回退缓存", table, key, e)
            cached = self._read(table, key, key_column, mode)
            if not cached.empty:
                logger.info("回退缓存成功: %s/%s (%d 行)", table, key, len(cached))
                return cached
            raise

        if df is None or df.empty:
            logger.warning("数据源返回空数据: %s/%s", table, key)
            return pd.DataFrame()

        # 3. 列名映射 + 写入缓存
        df = df.copy()
        if column_map:
            df.rename(columns=column_map, inplace=True)
        # 日期列统一为 YYYY-MM-DD 字符串
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        # 自动补 date 列（如果表有 date 列但数据里没有）
        if "date" not in df.columns and key not in ("all", "today"):
            from datetime import date
            if isinstance(key, str) and len(key) == 8:
                df["date"] = f"{key[:4]}-{key[4:6]}-{key[6:]}"
            else:
                df["date"] = str(key)
        # 去重（避免主键冲突导致写入失败）
        if mode != "overwrite" and "date" in df.columns and "symbol" in df.columns:
            df = df.drop_duplicates(subset=["date", "symbol"], keep="first")
        elif mode != "overwrite" and "date" in df.columns:
            df = df.drop_duplicates(subset=["date"], keep="first")
        df["fetched_at"] = now
        self._write(table, df, mode, key, key_column)

        self._update_meta(table, now)
        logger.info("缓存写入: %s/%s (%d 行)", table, key, len(df))
        return df

    # ==================== 预热 ====================

    def warmup(self, s: "Stoke") -> List[str]:
        """
        盘前预热：提前缓存静态 + 每日快照数据

        在每天开盘前调用一次，之后所有查询走缓存。
        预期耗时：30-60 秒（取决于网络）。

        Args:
            s: Stoke 实例（用于调数据源方法）

        Returns:
            预热完成的表名列表
        """
        logger.info("========== 盘前预热开始 ==========")
        warmed = []
        real_date = today_str()  # 真实交易日，如 "20260521"

        # ---- 静态数据（长 TTL） ----
        try:
            logger.info("预热: 股票列表")
            self.get_or_fetch("stock_list", "all",
                lambda: s.mootdx.get_stock_list(),
                max_age_sec=TTL["stock_list"], mode="overwrite")
            warmed.append("stock_list")
        except Exception as e:
            logger.warning("预热失败 stock_list: %s", e)

        # ---- 每日快照数据（key 用真实日期） ----
        daily_tasks = [
            ("limit_up", real_date,
             lambda: s.akshare.get_limit_up_pool(real_date), "date", "replace",
             {"代码": "symbol", "名称": "name", "涨跌幅": "change_pct",
              "连板数": "board_count", "所属行业": "industry"}),
            ("market_breadth", real_date,
             lambda: s.akshare.get_market_breadth(), "date", "replace", None),
            ("northbound_flow", real_date,
             lambda: s.akshare.get_northbound_flow(), "date", "append",
             {"日期": "date", "当日成交净买额": "net_buy",
              "买入成交额": "buy_amount", "卖出成交额": "sell_amount",
              "持股市值": "hold_balance"}),
            ("market_pb", real_date,
             lambda: s.tencent.get_market_pb(), "date", "append", None),
            ("dragon_tiger", real_date,
             lambda: s.efinance.get_daily_billboard(), "date", "replace",
             {"股票代码": "symbol", "股票名称": "name", "上榜日期": "date",
              "龙虎榜净买额": "net_buy_amount", "涨跌幅": "change_pct",
              "换手率": "turnover", "解读": "reason"}),
            ("sector_rank", real_date,
             lambda: s.akshare.get_sector_rank(), "date", "replace",
             {"名称": "sector_name", "涨跌幅": "change_pct"}),
            ("strong_stocks", real_date,
             lambda: s.akshare.get_strong_stocks(real_date), "date", "replace",
             {"代码": "symbol", "名称": "name", "涨跌幅": "change_pct",
              "入选理由": "reason", "所属行业": "industry"}),
            ("hot_keywords", real_date,
             lambda: s.akshare.get_hot_keywords(), "date", "replace",
             {"概念名称": "concept_name", "股票代码": "symbol", "热度": "heat"}),
            ("stock_comment", real_date,
             lambda: s.akshare.get_stock_comment_all(), "date", "replace",
             {"代码": "symbol", "名称": "name", "综合得分": "score",
              "主力成本": "main_cost", "关注指数": "focus_index"}),
            ("market_volume", real_date,
             lambda: s.akshare.get_market_volume(), "date", "append",
             {"日期": "date", "上证-收盘价": "sh_close", "上证-涨跌幅": "sh_change",
              "深证-收盘价": "sz_close", "深证-涨跌幅": "sz_change",
              "主力净流入-净额": "main_net"}),
        ]

        for table_name, key, fetcher_fn, key_col, wr_mode, col_map in daily_tasks:
            try:
                logger.info("预热: %s (key=%s)", table_name, key)
                self.get_or_fetch(
                    table_name, key,
                    fetcher_fn,
                    max_age_sec=TTL.get(table_name, 86400),
                    mode=wr_mode, key_column=key_col,
                    column_map=col_map,
                )
                warmed.append(table_name)
            except Exception as e:
                logger.warning("预热失败 %s: %s", table_name, e)

        # ---- 估值数据（多指数） ----
        for idx_name in ["上证50", "沪深300"]:
            try:
                self.get_or_fetch(
                    "index_pe", idx_name,
                    lambda n=idx_name: s.tencent.get_index_pe(n),
                    max_age_sec=TTL["index_pe"], mode="append", key_column="index_name",
                    column_map={"日期": "date", "指数": "index_name",
                                "滚动市盈率": "pe_ttm", "静态市盈率": "pe_static"},
                )
                warmed.append(f"index_pe({idx_name})")
            except Exception as e:
                logger.warning("预热失败 index_pe(%s): %s", idx_name, e)

        logger.info("========== 盘前预热完成 (%d 项) ==========", len(warmed))
        return warmed

    # ==================== 统计 ====================

    def stats(self) -> dict:
        """返回各表行数和最后写入时间"""
        result = {}
        with sqlite3.connect(self.db_path) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE '\\_%' ESCAPE '\\'"
            ).fetchall()
            for (name,) in tables:
                count = conn.execute(
                    f"SELECT COUNT(*) FROM \"{name}\""
                ).fetchone()[0]
                result[name] = count
        return result

    # ==================== 内部方法 ====================

    def _is_fresh(
        self, table: str, key: str, max_age_sec: int, key_column: str
    ) -> bool:
        """判断缓存是否在有效期内"""
        with sqlite3.connect(self.db_path) as conn:
            if max_age_sec == 0:
                # 永不过期：只要表里有数据就算新鲜
                row = conn.execute(
                    f"SELECT COUNT(*) FROM \"{table}\""
                ).fetchone()
                return row[0] > 0

            if max_age_sec > 0:
                # 查全局最新 fetched_at（不过滤 key，因为每日快照表可能还没今天的数据）
                row = conn.execute(
                    f"SELECT MAX(fetched_at) FROM \"{table}\""
                ).fetchone()

                if row[0] is None:
                    return False

                last_fetch = datetime.fromisoformat(row[0])
                age = (datetime.now() - last_fetch).total_seconds()
                return age < max_age_sec

    def _read(
        self, table: str, key: str, key_column: str, mode: str
    ) -> pd.DataFrame:
        """从 SQLite 读取数据"""
        with sqlite3.connect(self.db_path) as conn:
            if mode == "overwrite" or key == "all":
                return pd.read_sql(f"SELECT * FROM \"{table}\"", conn)
            else:
                return pd.read_sql(
                    f"SELECT * FROM \"{table}\" WHERE \"{key_column}\" = ?",
                    conn, params=(key,),
                )

    def _write(
        self, table: str, df: pd.DataFrame, mode: str,
        key: str, key_column: str,
    ):
        """写入 SQLite，按模式处理旧数据。自动对齐 DataFrame 列到表结构。"""
        with sqlite3.connect(self.db_path) as conn:
            # 获取表的实际列名，只写入匹配的列
            table_cols = set(
                row[1] for row in conn.execute(
                    f"PRAGMA table_info(\"{table}\")"
                ).fetchall()
            )
            # 过滤：只保留表中存在的列 + fetched_at
            write_cols = [c for c in df.columns if c in table_cols]
            df_write = df[write_cols].copy()

            if mode == "replace":
                conn.execute(
                    f"DELETE FROM \"{table}\" WHERE \"{key_column}\" = ?", (key,)
                )
                df_write.to_sql(table, conn, if_exists="append", index=False)
            elif mode == "append":
                df_write.to_sql(table, conn, if_exists="append", index=False)
                # 去重：动态读取主键列，保留每组中 rowid 最小的行
                try:
                    pk_cols = self._pk_columns(conn, table)
                    group_clause = ", ".join(pk_cols)
                    conn.execute(
                        f"DELETE FROM \"{table}\" WHERE rowid NOT IN ("
                        f"  SELECT MIN(rowid) FROM \"{table}\" GROUP BY {group_clause}"
                        f")"
                    )
                except Exception:
                    pass  # 表结构可能不同，跳过去重
            elif mode == "overwrite":
                df_write.to_sql(table, conn, if_exists="replace", index=False)

    def _update_meta(self, table_name: str, now: str):
        """更新元数据表"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO _meta (table_name, last_write) VALUES (?, ?)",
                (table_name, now),
            )

    def _pk_columns(self, conn: sqlite3.Connection, table: str) -> list:
        """从 PRAGMA table_info 读取主键列名列表"""
        cols = []
        for row in conn.execute(f"PRAGMA table_info(\"{table}\")"):
            if row[5]:  # pk 字段非零即为主键列
                cols.append(row[1])
        return cols if cols else ["symbol", "date"]  # fallback

    def _table_count(self) -> int:
        """统计业务表数量"""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE '\\_%' ESCAPE '\\'"
            ).fetchone()
            return row[0]
