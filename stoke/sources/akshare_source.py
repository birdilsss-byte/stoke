"""
akshare 数据源 — HTTP 协议封装

通过 akshare 库获取东财、同花顺、巨潮资讯网、财联社数据。
覆盖：新闻、研报、公告、涨停信号、概念/行业板块。

⚠️ 铁律：每次请求前调用 limiter.wait()，默认 5 秒间隔，
不可频繁调用否则东财封 IP。

每个 HTTP 接口自带自动重试（网络抖动时最多重试 3 次）。
"""

import logging
from typing import Optional
from datetime import datetime

import akshare as ak
import pandas as pd

from stoke.rate_limiter import RateLimiter
from stoke.config import RATE_LIMIT
from stoke.utils import retry_on_failure

logger = logging.getLogger(__name__)


class AKShareSource:
    """akshare 数据源，封装东财/同花顺/巨潮/财联社"""

    def __init__(self, rate_limiter: Optional[RateLimiter] = None):
        """
        Args:
            rate_limiter: 可选，默认 5 秒间隔
        """
        self.limiter = rate_limiter or RateLimiter(interval=RATE_LIMIT["akshare"])
        logger.info("AKShareSource 初始化，限流间隔 %.1f 秒", self.limiter.interval)

    def health_check(self) -> bool:
        """连通性检查：获取概念板块列表（接口轻量、稳定）"""
        try:
            data = ak.stock_board_concept_name_ths()
            ok = len(data) > 0
            logger.info("健康检查 %s", "通过" if ok else "失败(数据为空)")
            return ok
        except Exception as e:
            logger.warning("健康检查失败: %s", e)
            return False

    # ==================== 新闻层 ====================

    @retry_on_failure()
    def get_news(self, symbol: str) -> pd.DataFrame:
        """
        获取个股新闻（来源：东财）

        Args:
            symbol: 股票代码，如 '000001'

        Returns:
            DataFrame，含 新闻标题、发布时间、新闻内容 等列
        """
        self.limiter.wait()
        logger.info("获取个股新闻: %s", symbol)
        return ak.stock_news_em(symbol=symbol)

    @retry_on_failure()
    def get_cls_telegraph(self) -> pd.DataFrame:
        """
        获取财联社电报快讯（分钟级更新）

        Returns:
            DataFrame，含 标题、内容、发布时间 等列
        """
        self.limiter.wait()
        logger.info("获取财联社电报")
        return ak.stock_info_global_cls()

    # ==================== 研报层 ====================

    @retry_on_failure()
    def get_research_report(self, symbol: str) -> pd.DataFrame:
        """
        获取东财研报（含 PDF 下载链接和盈利预测）

        Args:
            symbol: 股票代码，如 '000001'

        Returns:
            DataFrame，含 报告名称、机构、评级、日期、PDF链接、
            2026/2027/2028 年盈利预测和市盈率 等列
        """
        self.limiter.wait()
        logger.info("获取东财研报: %s", symbol)
        return ak.stock_research_report_em(symbol=symbol)

    # ==================== 公告层 ====================

    @retry_on_failure()
    def get_announcements(self, symbol: str) -> pd.DataFrame:
        """
        获取巨潮公告

        Args:
            symbol: 股票代码，如 '000001'

        Returns:
            DataFrame，含 公告标题、公告类型、公告日期、网址 等列
        """
        self.limiter.wait()
        logger.info("获取巨潮公告: %s", symbol)
        return ak.stock_individual_notice_report(security=symbol)

    # ==================== 信号层（同花顺热点） ====================

    @retry_on_failure()
    def get_limit_up_pool(self, date: Optional[str] = None) -> pd.DataFrame:
        """
        获取涨停板股票池（来源：同花顺）

        Args:
            date: 日期（YYYYMMDD），默认今天

        Returns:
            DataFrame，含 代码、名称、涨跌幅、涨停统计、连板数、
            封板时间、炸板次数、所属行业 等列
        """
        if date is None:
            date = datetime.now().strftime("%Y%m%d")
        self.limiter.wait()
        logger.info("获取涨停板: %s", date)
        return ak.stock_zt_pool_em(date=date)

    @retry_on_failure()
    def get_strong_stocks(self, date: Optional[str] = None) -> pd.DataFrame:
        """
        获取强势涨停股（来源：同花顺热点）
        **含"入选理由"字段 — 独家题材归因**

        Args:
            date: 日期（YYYYMMDD），默认今天

        Returns:
            DataFrame，含 代码、名称、涨跌幅、换手率、量比、
            涨停统计、**入选理由**（题材归因）、所属行业 等列
        """
        if date is None:
            date = datetime.now().strftime("%Y%m%d")
        self.limiter.wait()
        logger.info("获取强势涨停股: %s", date)
        return ak.stock_zt_pool_strong_em(date=date)

    # ==================== 概念/行业板块 ====================

    @retry_on_failure()
    def get_concept_list(self) -> pd.DataFrame:
        """
        获取同花顺概念板块列表

        Returns:
            DataFrame，含 name（概念名）、code（概念代码）
        """
        self.limiter.wait()
        logger.info("获取概念板块列表")
        return ak.stock_board_concept_name_ths()

    @retry_on_failure()
    def get_industry_list(self) -> pd.DataFrame:
        """
        获取同花顺行业板块列表

        Returns:
            DataFrame，含 name（行业名）、code（行业代码）
        """
        self.limiter.wait()
        logger.info("获取行业板块列表")
        return ak.stock_board_industry_name_ths()

    # ==================== 辅助方法 ====================

    def get_today_str(self) -> str:
        """获取今天的日期字符串（YYYYMMDD）"""
        return datetime.now().strftime("%Y%m%d")
