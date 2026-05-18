"""
Stoke 统一入口

自动路由到正确的数据源，无需记忆哪个接口来自哪个源。
"""
import logging
from typing import Optional, List

import pandas as pd

from stoke.rate_limiter import RateLimiter
from stoke.sources.mootdx_source import MootdxSource
from stoke.sources.akshare_source import AKShareSource
from stoke.sources.tencent_source import TencentSource

logger = logging.getLogger(__name__)


class Stoke:
    """
    Stoke 统一入口，自动路由到正确的数据源。

    用法::

        from stoke import Stoke
        s = Stoke()

        # 行情
        df = s.realtime(["000001", "600000"])
        df = s.kline("000001")

        # 新闻/研报/公告/信号
        df = s.news("000001")
        df = s.limit_up()
        df = s.strong_stocks()

        # 估值
        df = s.index_pe("上证50")
        df = s.market_pb()
    """

    def __init__(
        self,
        mootdx_limiter: Optional[RateLimiter] = None,
        akshare_limiter: Optional[RateLimiter] = None,
        tencent_limiter: Optional[RateLimiter] = None,
    ):
        """
        Args:
            mootdx_limiter: mootdx 限流器（默认不限流）
            akshare_limiter: akshare 限流器（默认 5 秒）
            tencent_limiter: 腾讯限流器（默认 3 秒）
        """
        self.mootdx = MootdxSource(rate_limiter=mootdx_limiter)
        self.akshare = AKShareSource(rate_limiter=akshare_limiter)
        self.tencent = TencentSource(rate_limiter=tencent_limiter)
        logger.info("Stoke 统一入口初始化完成（mootdx + akshare + tencent）")

    # ==================== 健康检查 ====================

    def health_check(self) -> dict:
        """
        检查所有数据源连通性

        Returns:
            dict，如 {"mootdx": True, "akshare": True, "tencent": True}
        """
        result = {
            "mootdx": self.mootdx.health_check(),
            "akshare": self.akshare.health_check(),
            "tencent": self.tencent.health_check(),
        }
        status = "全部正常" if all(result.values()) else "部分异常"
        logger.info("全源健康检查: %s %s", result, status)
        return result

    # ==================== 行情（mootdx） ====================

    def realtime(self, symbols: List[str]) -> pd.DataFrame:
        """实时行情（含 5 档盘口）"""
        return self.mootdx.get_realtime(symbols)

    def kline(
        self,
        symbol: str,
        frequency: int = 9,
        start: int = 0,
        offset: int = 800,
    ) -> pd.DataFrame:
        """历史 K 线，默认日线 800 条"""
        return self.mootdx.get_kline(symbol, frequency, start, offset)

    def stock_list(self) -> pd.DataFrame:
        """全市场股票列表"""
        return self.mootdx.get_stock_list()

    def f10(self, symbol: str) -> Optional[dict]:
        """F10 财务快照"""
        return self.mootdx.get_f10(symbol)

    # ==================== 新闻 & 研报 & 公告（akshare） ====================

    def news(self, symbol: str) -> pd.DataFrame:
        """个股新闻"""
        return self.akshare.get_news(symbol)

    def telegraph(self) -> pd.DataFrame:
        """财联社电报快讯"""
        return self.akshare.get_cls_telegraph()

    def research(self, symbol: str) -> pd.DataFrame:
        """东财研报（含 PDF + 盈利预测）"""
        return self.akshare.get_research_report(symbol)

    def announcements(self, symbol: str) -> pd.DataFrame:
        """巨潮公告"""
        return self.akshare.get_announcements(symbol)

    # ==================== 信号（akshare） ====================

    def limit_up(self, date: Optional[str] = None) -> pd.DataFrame:
        """涨停板股票池"""
        return self.akshare.get_limit_up_pool(date)

    def strong_stocks(self, date: Optional[str] = None) -> pd.DataFrame:
        """强势涨停股（含题材归因）"""
        return self.akshare.get_strong_stocks(date)

    # ==================== 板块（akshare） ====================

    def concepts(self) -> pd.DataFrame:
        """概念板块列表"""
        return self.akshare.get_concept_list()

    def industries(self) -> pd.DataFrame:
        """行业板块列表"""
        return self.akshare.get_industry_list()

    # ==================== 估值（tencent） ====================

    def index_pe(self, index_name: str = "上证50") -> pd.DataFrame:
        """指数 PE 历史"""
        return self.tencent.get_index_pe(index_name)

    def market_pb(self) -> pd.DataFrame:
        """全市场 PB 历史"""
        return self.tencent.get_market_pb()
