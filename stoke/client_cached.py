"""
StokeCached — 带 SQLite 缓存的 Stoke 包装器

覆写 12 个高频方法加缓存 + 故障降级直连。
其余 36 个方法通过 __getattr__ 自动透传到裸 Stoke。
"""

import logging
import time
from typing import Optional, Callable

import pandas as pd

from stoke.config import setup_logging
from stoke.client import Stoke as StokeRaw
from stoke.store import Store, TTL as STORE_TTL
from stoke.calendar import today_str

setup_logging()
logger = logging.getLogger(__name__)


class StokeCached:
    """带缓存的 Stoke 包装器"""

    def __init__(self, stoke: Optional[StokeRaw] = None):
        self._s = stoke or StokeRaw()
        self.store = Store()
        self._degraded_at: float = 0.0
        logger.info("StokeCached 初始化完成（缓存已开启）")

    @property
    def raw(self) -> StokeRaw:
        """暴露裸 Stoke 实例，供 runner 等需要直接访问源的场景"""
        return self._s

    def _cached_call(
        self,
        table: str,
        key: str,
        fetcher: Callable[[], pd.DataFrame],
        fallback: Callable[[], pd.DataFrame],
        max_age_sec: int,
        mode: str,
        key_column: str = "symbol",
        column_map: Optional[dict] = None,
    ) -> pd.DataFrame:
        """缓存读写 + 故障自动降级，30 秒后自动重试缓存"""
        if self._degraded_at:
            if time.time() - self._degraded_at < 30:
                return fallback()
            logger.info("降级超时已过，重试缓存 %s", table)
            self._degraded_at = 0.0
        try:
            return self.store.get_or_fetch(
                table, key, fetcher,
                max_age_sec=max_age_sec, mode=mode,
                key_column=key_column, column_map=column_map,
            )
        except Exception:
            logger.exception("缓存故障，降级直连 %s", table)
            self._degraded_at = time.time()
            return fallback()

    # ===== 12 个缓存方法 =====

    def kline(self, symbol: str, frequency: int = 9,
              start: int = 0, offset: int = 800) -> pd.DataFrame:
        if frequency == 9:
            def _fetch():
                df = self._s.mootdx.get_kline(symbol, frequency, start, offset)
                if not df.empty:
                    df["symbol"] = symbol
                    if "datetime" in df.columns:
                        df["date"] = pd.to_datetime(df["datetime"]).dt.strftime("%Y-%m-%d")
                return df
            return self._cached_call(
                "kline_daily", symbol, _fetch,
                lambda: self._s.mootdx.get_kline(symbol, frequency, start, offset),
                max_age_sec=STORE_TTL["kline_daily"], mode="append",
            )
        return self._s.mootdx.get_kline(symbol, frequency, start, offset)

    def limit_up(self, date: Optional[str] = None) -> pd.DataFrame:
        real_date = date or today_str()
        return self._cached_call(
            "limit_up", real_date,
            lambda: self._s.akshare.get_limit_up_pool(real_date),
            lambda: self._s.akshare.get_limit_up_pool(date),
            max_age_sec=STORE_TTL["limit_up"], mode="replace", key_column="date",
            column_map={},
        )

    def strong_stocks(self, date: Optional[str] = None) -> pd.DataFrame:
        real_date = date or today_str()
        return self._cached_call(
            "strong_stocks", real_date,
            lambda: self._s.akshare.get_strong_stocks(real_date),
            lambda: self._s.akshare.get_strong_stocks(date),
            max_age_sec=STORE_TTL["strong_stocks"], mode="replace", key_column="date",
            column_map={},
        )

    def sector_rank(self) -> pd.DataFrame:
        real_date = today_str()
        return self._cached_call(
            "sector_rank", real_date,
            lambda: self._s.akshare.get_sector_rank(),
            lambda: self._s.akshare.get_sector_rank(),
            max_age_sec=STORE_TTL["sector_rank"], mode="replace", key_column="date",
            column_map={"名称": "sector_name", "涨跌幅": "change_pct"},
        )

    def market_breadth(self) -> pd.DataFrame:
        real_date = today_str()
        return self._cached_call(
            "market_breadth", real_date,
            lambda: self._s.akshare.get_market_breadth(),
            lambda: self._s.akshare.get_market_breadth(),
            max_age_sec=STORE_TTL["market_breadth"], mode="replace", key_column="date",
        )

    def market_volume(self) -> pd.DataFrame:
        return self._cached_call(
            "market_volume", today_str(),
            lambda: self._s.akshare.get_market_volume(),
            lambda: self._s.akshare.get_market_volume(),
            max_age_sec=STORE_TTL["market_volume"], mode="append", key_column="date",
            column_map={"日期": "date", "上证-收盘价": "sh_close", "上证-涨跌幅": "sh_change",
                        "深证-收盘价": "sz_close", "深证-涨跌幅": "sz_change",
                        "主力净流入-净额": "main_net"},
        )

    def northbound_flow(self) -> pd.DataFrame:
        return self._cached_call(
            "northbound_flow", today_str(),
            lambda: self._s.akshare.get_northbound_flow(),
            lambda: self._s.akshare.get_northbound_flow(),
            max_age_sec=STORE_TTL["northbound_flow"], mode="append", key_column="date",
            column_map={"日期": "date", "当日成交净买额": "net_buy",
                        "买入成交额": "buy_amount", "卖出成交额": "sell_amount",
                        "持股市值": "hold_balance"},
        )

    def dragon_tiger(self) -> pd.DataFrame:
        real_date = today_str()
        return self._cached_call(
            "dragon_tiger", real_date,
            lambda: self._s.efinance.get_daily_billboard(),
            lambda: self._s.efinance.get_daily_billboard(),
            max_age_sec=STORE_TTL["dragon_tiger"], mode="replace", key_column="date",
            column_map={"股票代码": "symbol", "股票名称": "name",
                        "龙虎榜净买额": "net_buy_amount", "涨跌幅": "change_pct",
                        "换手率": "turnover", "解读": "reason"},
        )

    def hot_keywords(self) -> pd.DataFrame:
        return self._cached_call(
            "hot_keywords", today_str(),
            lambda: self._s.akshare.get_hot_keywords(),
            lambda: self._s.akshare.get_hot_keywords(),
            max_age_sec=STORE_TTL["hot_keywords"], mode="replace", key_column="date",
            column_map={"概念名称": "concept_name", "股票代码": "symbol", "热度": "heat"},
        )

    def stock_comment_all(self) -> pd.DataFrame:
        return self._cached_call(
            "stock_comment", today_str(),
            lambda: self._s.akshare.get_stock_comment_all(),
            lambda: self._s.akshare.get_stock_comment_all(),
            max_age_sec=STORE_TTL["stock_comment"], mode="replace", key_column="date",
            column_map={"代码": "symbol", "名称": "name", "综合得分": "score",
                        "主力成本": "main_cost", "关注指数": "focus_index"},
        )

    def index_pe(self, index_name: str = "上证50") -> pd.DataFrame:
        return self._cached_call(
            "index_pe", index_name,
            lambda: self._s.legulegu.get_index_pe(index_name),
            lambda: self._s.legulegu.get_index_pe(index_name),
            max_age_sec=STORE_TTL["index_pe"], mode="append", key_column="index_name",
        )

    def market_pb(self) -> pd.DataFrame:
        return self._cached_call(
            "market_pb", today_str(),
            lambda: self._s.legulegu.get_market_pb(),
            lambda: self._s.legulegu.get_market_pb(),
            max_age_sec=STORE_TTL["market_pb"], mode="append", key_column="date",
        )

    # ===== 透传：其余 36 个方法自动代理到裸 Stoke =====

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._s, name)
