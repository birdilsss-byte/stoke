"""
akshare 数据源 — HTTP 协议封装

通过 akshare 库获取东财、同花顺、巨潮资讯网、财联社数据。
覆盖：新闻、研报、公告、涨停信号、概念/行业板块、
资金流（北向资金、龙虎榜、融资融券、主力资金）、
情绪（股吧热度、舆情评分、千股千评、跌停）、
筹码（主力成本）。

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
from stoke.calendar import today_str as cal_today_str

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
            date = cal_today_str()
        self.limiter.wait()
        logger.info("获取涨停板: %s", date)
        return ak.stock_zt_pool_em(date=date)

    @retry_on_failure()
    def get_strong_stocks(self, date: Optional[str] = None) -> pd.DataFrame:
        """
        获取强势涨停股（来源：同花顺热点）
        **含"入选理由"字段 — 独家题材归因**

        Args:
            date: 日期（YYYYMMDD），默认最近交易日

        Returns:
            DataFrame，含 代码、名称、涨跌幅、换手率、量比、
            涨停统计、**入选理由**（题材归因）、所属行业 等列
        """
        if date is None:
            date = cal_today_str()
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

    # ==================== 资金流：北向资金 ====================

    @retry_on_failure()
    def get_northbound_flow(self) -> pd.DataFrame:
        """
        北向资金历史每日成交净买额

        Returns:
            DataFrame，含 日期、当日成交净买额、买入/卖出成交额、
            历史累计净买额、持股市值、领涨股 等列
        """
        self.limiter.wait()
        logger.info("获取北向资金历史数据")
        return ak.stock_hsgt_hist_em(symbol="北向资金")

    # ==================== 资金流：龙虎榜 ====================

    @retry_on_failure()
    def get_dragon_tiger(self) -> pd.DataFrame:
        """
        龙虎榜营业部上榜资金统计（今日）

        Returns:
            DataFrame，含 营业部名称、今日最高操作、金额、累计参与金额 等列
        """
        self.limiter.wait()
        logger.info("获取龙虎榜资金统计")
        return ak.stock_lh_yyb_capital()

    # ==================== 资金流：融资融券 ====================

    @retry_on_failure()
    def get_margin_shanghai(self) -> pd.DataFrame:
        """
        上海市场融资融券余额（历史每日）

        Returns:
            DataFrame，含 日期、融资余额、融资买入额、融券余量、融资融券余额 等列
        """
        self.limiter.wait()
        logger.info("获取沪市融资融券余额")
        return ak.stock_margin_sse()

    @retry_on_failure()
    def get_margin_shenzhen(self) -> pd.DataFrame:
        """
        深圳市场融资融券余额（最新）

        Returns:
            DataFrame，含 融资买入额、融资余额、融券余量、融券余额、融资融券余额 等列
        """
        self.limiter.wait()
        logger.info("获取深市融资融券余额")
        return ak.stock_margin_szse()

    # ==================== 资金流：主力资金 ====================

    @retry_on_failure()
    def get_market_fund_flow(self) -> pd.DataFrame:
        """
        市场整体资金流（上证 + 深证）

        Returns:
            DataFrame，含 日期、上证/深证-收盘价、主力净流入、超大单/大单/中单/小单净流入 等列
        """
        self.limiter.wait()
        logger.info("获取市场整体资金流")
        return ak.stock_market_fund_flow()

    @retry_on_failure()
    def get_individual_fund_flow(self, symbol: str) -> pd.DataFrame:
        """
        个股主力资金流向（含超大单/大单/中单/小单细分）

        Args:
            symbol: 股票代码，如 '000001'

        Returns:
            DataFrame，含 日期、收盘价、主力净流入-净额/占比、
            超大单/大单/中单/小单净流入 等列
        """
        # 自动判断市场：6xxxxx → sh，0xxxxx/3xxxxx → sz
        market = "sh" if symbol.startswith("6") else "sz"
        self.limiter.wait()
        logger.info("获取个股主力资金流向: %s (%s)", symbol, market)
        return ak.stock_individual_fund_flow(stock=symbol, market=market)

    # ==================== 情绪：股吧热度（东财主力） ====================

    @staticmethod
    def _add_market_prefix(symbol: str) -> str:
        """为 6 位股票代码添加市场前缀（SZ/SH）"""
        return f"SH{symbol}" if symbol.startswith("6") else f"SZ{symbol}"

    @retry_on_failure()
    def get_hot_detail(self, symbol: str) -> pd.DataFrame:
        """
        【主力】东方财富个股热度详情 — 含粉丝结构和新晋/铁杆粉丝比例

        可量化情绪正负向：新晋粉丝多 = 短期热度上升，
        铁杆粉丝多 = 长期持有者占比高。

        Args:
            symbol: 股票代码，如 '000001'

        Returns:
            DataFrame，含 时间、排名、新晋粉丝、铁杆粉丝 等列
        """
        full_symbol = self._add_market_prefix(symbol)
        self.limiter.wait()
        logger.info("获取东财个股热度详情: %s (%s)", symbol, full_symbol)
        return ak.stock_hot_rank_detail_em(symbol=full_symbol)

    @retry_on_failure()
    def get_hot_latest(self, symbol: str) -> pd.DataFrame:
        """
        东方财富个股最新排名

        Args:
            symbol: 股票代码，如 '000001'

        Returns:
            DataFrame，含 排名、排名变化 等 key-value
        """
        full_symbol = self._add_market_prefix(symbol)
        self.limiter.wait()
        logger.info("获取东财个股最新排名: %s", symbol)
        return ak.stock_hot_rank_latest_em(symbol=full_symbol)

    @retry_on_failure()
    def get_hot_realtime(self, symbol: str) -> pd.DataFrame:
        """
        东方财富个股当天实时排名变动（每 10 分钟）

        Args:
            symbol: 股票代码，如 '000001'

        Returns:
            DataFrame，含 时间、排名 等列
        """
        full_symbol = self._add_market_prefix(symbol)
        self.limiter.wait()
        logger.info("获取东财个股实时排名变动: %s", symbol)
        return ak.stock_hot_rank_detail_realtime_em(symbol=full_symbol)

    @retry_on_failure()
    def get_hot_keywords(self) -> pd.DataFrame:
        """
        热搜关键词（概念题材维度）

        Returns:
            DataFrame，含 时间、股票代码、概念名称、概念代码、热度 等列
        """
        self.limiter.wait()
        logger.info("获取热搜关键词")
        return ak.stock_hot_keyword_em()

    # ==================== 情绪：雪球热度（备选） ====================

    @retry_on_failure()
    def get_xueqiu_hot(self, mode: str = "最热门") -> pd.DataFrame:
        """
        【备选】雪球沪深股市热度排行榜

        整合三个维度：讨论热度、交易热度、关注热度

        Args:
            mode: "最热门" 或 "本周新增"

        Returns:
            DataFrame，含 股票代码、股票简称、关注、最新价 等列
        """
        self.limiter.wait()
        logger.info("获取雪球热度排行榜: %s", mode)
        return ak.stock_hot_tweet_xq(symbol=mode)

    # ==================== 情绪：舆情评分 ====================

    @retry_on_failure()
    def get_stock_comment_all(self) -> pd.DataFrame:
        """
        全市场千股千评（含情绪综合得分、主力成本、关注指数）

        Returns:
            DataFrame（全市场约 5000+ 行）含 代码、名称、综合得分、
            主力成本、关注指数、上升/下降排名 等列
        """
        self.limiter.wait()
        logger.info("获取全市场千股千评")
        return ak.stock_comment_em()

    @retry_on_failure()
    def get_stock_desire(self, symbol: str) -> pd.DataFrame:
        """
        个股参与意愿评分

        Args:
            symbol: 股票代码，如 '000001'

        Returns:
            DataFrame，含 日期、参与意愿、5日均值、变化 等列
        """
        self.limiter.wait()
        logger.info("获取个股参与意愿: %s", symbol)
        return ak.stock_comment_detail_scrd_desire_em(symbol=symbol)

    @retry_on_failure()
    def get_stock_focus(self, symbol: str) -> pd.DataFrame:
        """
        个股用户关注指数

        Args:
            symbol: 股票代码，如 '000001'

        Returns:
            DataFrame，含 交易日、用户关注指数 等列
        """
        self.limiter.wait()
        logger.info("获取个股关注指数: %s", symbol)
        return ak.stock_comment_detail_scrd_focus_em(symbol=symbol)

    # ==================== 情绪：跌停股 ====================

    @retry_on_failure()
    def get_limit_down_pool(self, date: Optional[str] = None) -> pd.DataFrame:
        """
        跌停板股票池

        Args:
            date: 日期（YYYYMMDD），默认今天

        Returns:
            DataFrame，含 代码、名称、涨跌幅、封单资金、连续跌停、
            开板次数、所属行业 等列
        """
        if date is None:
            date = cal_today_str()
        self.limiter.wait()
        logger.info("获取跌停板: %s", date)
        return ak.stock_zt_pool_dtgc_em(date=date)

    # ==================== 板块行情 ====================

    @retry_on_failure()
    def get_sector_kline(self, symbol: str = "银行",
                         start_date: str = "20250101",
                         end_date: str = "") -> pd.DataFrame:
        """
        行业板块指数 K 线（来源：同花顺）

        Args:
            symbol: 行业板块名称，如 '银行'、'半导体'
            start_date: 起始日期（YYYYMMDD）
            end_date: 截止日期（YYYYMMDD），默认最近交易日

        Returns:
            DataFrame，含 日期、开盘价、最高价、最低价、收盘价、成交量、成交额
        """
        if not end_date:
            end_date = cal_today_str()
        self.limiter.wait()
        logger.info("获取行业板块指数 K 线: %s (%s ~ %s)", symbol, start_date, end_date)
        return ak.stock_board_industry_index_ths(
            symbol=symbol, start_date=start_date, end_date=end_date
        )

    @retry_on_failure()
    def get_sector_rank(self) -> pd.DataFrame:
        """
        行业板块当日涨跌幅排名（来源：东方财富）

        Returns:
            DataFrame，含 排名、板块名称、板块代码、最新价、涨跌幅、
            总市值、换手率、上涨家数、下跌家数、领涨股票 等列
        """
        self.limiter.wait()
        logger.info("获取行业涨跌幅排名")
        return ak.stock_board_industry_name_em()

    # ==================== 市场宽度 ====================

    @retry_on_failure()
    def get_market_breadth(self) -> pd.DataFrame:
        """
        市场宽度：上证指数日线（含成交额）

        Returns:
            DataFrame，含 date、open、high、low、close、volume
        """
        self.limiter.wait()
        logger.info("获取市场宽度数据")
        return ak.stock_zh_index_daily(symbol="sh000001")

    @retry_on_failure()
    def get_market_volume(self) -> pd.DataFrame:
        """
        沪深两市每日成交额（含主力资金细分）

        Returns:
            DataFrame，含 日期、上证/深证收盘价和涨跌幅、主力净流入、各类型单净流入 等列
        """
        self.limiter.wait()
        logger.info("获取市场成交额数据")
        return ak.stock_market_fund_flow()

