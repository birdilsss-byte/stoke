"""
StokeCached — 带 SQLite 缓存的 Stoke 包装器

覆写 12 个高频方法加缓存 + 故障降级直连。
其余 36 个方法通过 __getattr__ 自动透传到裸 Stoke。
"""

import logging
from typing import Optional

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
        logger.info("StokeCached 初始化完成（缓存已开启）")

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
            try:
                return self.store.get_or_fetch(
                    "kline_daily", symbol, _fetch,
                    max_age_sec=STORE_TTL["klinedaily"], mode="append",
                )
            except Exception:
                logger.warning("缓存故障，降级直连 kline(%s)", symbol)
        return self._s.mootdx.get_kline(symbol, frequency, start, offset)

    def limit_up(self, date: Optional[str] = None) -> pd.DataFrame:
        real_date = date or today_str()
        try:
            return self.store.get_or_fetch(
                "limit_up", real_date,
                lambda: self._s.akshare.get_limit_up_pool(real_date),
                max_age_sec=STORE_TTL["limitup"], mode="replace", key_column="date",
                column_map={"代码": "symbol", "名称": "name", "涨跌幅": "change_pct",
                            "连板数": "board_count", "所属行业": "industry"},
            )
        except Exception:
            logger.warning("缓存故障，降级直连 limit_up")
        return self._s.akshare.get_limit_up_pool(date)

    def strong_stocks(self, date: Optional[str] = None) -> pd.DataFrame:
        real_date = date or today_str()
        try:
            return self.store.get_or_fetch(
                "strong_stocks", real_date,
                lambda: self._s.akshare.get_strong_stocks(real_date),
                max_age_sec=STORE_TTL["strongstocks"], mode="replace", key_column="date",
                column_map={"代码": "symbol", "名称": "name", "涨跌幅": "change_pct",
                            "入选理由": "reason", "所属行业": "industry"},
            )
        except Exception:
            logger.warning("缓存故障，降级直连 strong_stocks")
        return self._s.akshare.get_strong_stocks(date)

    def sector_rank(self) -> pd.DataFrame:
        real_date = today_str()
        try:
            return self.store.get_or_fetch(
                "sector_rank", real_date,
                lambda: self._s.akshare.get_sector_rank(),
                max_age_sec=STORE_TTL["sector_rank"], mode="replace", key_column="date",
                column_map={"名称": "sector_name", "涨跌幅": "change_pct"},
            )
        except Exception:
            logger.warning("缓存故障，降级直连 sector_rank")
        return self._s.akshare.get_sector_rank()

    def market_breadth(self) -> pd.DataFrame:
        real_date = today_str()
        try:
            return self.store.get_or_fetch(
                "market_breadth", real_date,
                lambda: self._s.akshare.get_market_breadth(),
                max_age_sec=STORE_TTL["marketbreadth"], mode="replace", key_column="date",
            )
        except Exception:
            logger.warning("缓存故障，降级直连 market_breadth")
        return self._s.akshare.get_market_breadth()

    def market_volume(self) -> pd.DataFrame:
        try:
            return self.store.get_or_fetch(
                "market_volume", today_str(),
                lambda: self._s.akshare.get_market_volume(),
                max_age_sec=STORE_TTL["market_volume"], mode="append", key_column="date",
                column_map={"日期": "date", "上证-收盘价": "sh_close", "上证-涨跌幅": "sh_change",
                            "深证-收盘价": "sz_close", "深证-涨跌幅": "sz_change",
                            "主力净流入-净额": "main_net"},
            )
        except Exception:
            logger.warning("缓存故障，降级直连 market_volume")
        return self._s.akshare.get_market_volume()

    def northbound_flow(self) -> pd.DataFrame:
        try:
            return self.store.get_or_fetch(
                "northbound_flow", today_str(),
                lambda: self._s.akshare.get_northbound_flow(),
                max_age_sec=STORE_TTL["northboundflow"], mode="append", key_column="date",
                column_map={"日期": "date", "当日成交净买额": "net_buy",
                            "买入成交额": "buy_amount", "卖出成交额": "sell_amount",
                            "持股市值": "hold_balance"},
            )
        except Exception:
            logger.warning("缓存故障，降级直连 northbound_flow")
        return self._s.akshare.get_northbound_flow()

    def dragon_tiger(self) -> pd.DataFrame:
        real_date = today_str()
        try:
            return self.store.get_or_fetch(
                "dragon_tiger", real_date,
                lambda: self._s.efinance.get_daily_billboard(),
                max_age_sec=STORE_TTL["dragon_tiger"], mode="replace", key_column="date",
                column_map={"股票代码": "symbol", "股票名称": "name",
                            "龙虎榜净买额": "net_buy_amount", "涨跌幅": "change_pct",
                            "换手率": "turnover", "解读": "reason"},
            )
        except Exception:
            logger.warning("缓存故障，降级直连 dragon_tiger")
        return self._s.efinance.get_daily_billboard()

    def hot_keywords(self) -> pd.DataFrame:
        try:
            return self.store.get_or_fetch(
                "hot_keywords", today_str(),
                lambda: self._s.akshare.get_hot_keywords(),
                max_age_sec=STORE_TTL["hotkeywords"], mode="replace", key_column="date",
                column_map={"概念名称": "concept_name", "股票代码": "symbol", "热度": "heat"},
            )
        except Exception:
            logger.warning("缓存故障，降级直连 hot_keywords")
        return self._s.akshare.get_hot_keywords()

    def stock_comment_all(self) -> pd.DataFrame:
        try:
            return self.store.get_or_fetch(
                "stock_comment", today_str(),
                lambda: self._s.akshare.get_stock_comment_all(),
                max_age_sec=STORE_TTL["stock_comment"], mode="replace", key_column="date",
                column_map={"代码": "symbol", "名称": "name", "综合得分": "score",
                            "主力成本": "main_cost", "关注指数": "focus_index"},
            )
        except Exception:
            logger.warning("缓存故障，降级直连 stock_comment_all")
        return self._s.akshare.get_stock_comment_all()

    def index_pe(self, index_name: str = "上证50") -> pd.DataFrame:
        try:
            return self.store.get_or_fetch(
                "index_pe", index_name,
                lambda: self._s.tencent.get_index_pe(index_name),
                max_age_sec=STORE_TTL["indexpe"], mode="append", key_column="index_name",
                column_map={"日期": "date", "指数": "index_name",
                            "滚动市盈率": "pe_ttm", "静态市盈率": "pe_static"},
            )
        except Exception:
            logger.warning("缓存故障，降级直连 index_pe(%s)", index_name)
        return self._s.tencent.get_index_pe(index_name)

    def market_pb(self) -> pd.DataFrame:
        try:
            return self.store.get_or_fetch(
                "market_pb", today_str(),
                lambda: self._s.tencent.get_market_pb(),
                max_age_sec=STORE_TTL["marketpb"], mode="append", key_column="date",
            )
        except Exception:
            logger.warning("缓存故障，降级直连 market_pb")
        return self._s.tencent.get_market_pb()

    # ===== 透传：其余 36 个方法自动代理到裸 Stoke =====

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._s, name)
