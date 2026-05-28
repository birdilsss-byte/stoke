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
from stoke.sources.baostock_source import BaostockSource
from stoke.sources.efinance_source import EFinanceSource
from stoke.exceptions import NetworkError, DataEmptyError, SourceNotReadyError

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

        # 新闻/研报/公告/信号/情绪
        df = s.news("000001")
        df = s.limit_up()
        df = s.strong_stocks()
        df = s.limit_down()  # 跌停
        df = s.stock_comment_all()  # 千股千评（含主力成本、情绪评分）

        # 资金流
        df = s.northbound_flow()  # 北向资金
        df = s.dragon_tiger()  # 龙虎榜
        df = s.margin_shanghai()  # 融资融券
        df = s.individual_fund_flow("000001")  # 个股主力资金
        df = s.market_fund_flow()  # 市场整体资金流

        # 热度（东财主力 + 雪球备选）
        df = s.hot_detail("000001")  # 东财热度：新晋/铁杆粉丝比例
        df = s.xueqiu_hot()  # 雪球全市场热度排行榜
        df = s.hot_keywords()  # 热搜关键词

        # 板块数据
        df = s.sector_kline("银行")  # 行业板块指数 K 线
        df = s.sector_rank()  # 行业涨跌幅排名
        df = s.sector_members("沪深300")  # 板块成分股

        # 市场宽度
        df = s.market_breadth()  # 上证指数日线
        df = s.market_volume()  # 沪深成交额

        # 估值
        df = s.index_pe("上证50")
        df = s.market_pb()
    """

    def __init__(
        self,
        mootdx_limiter: Optional[RateLimiter] = None,
        akshare_limiter: Optional[RateLimiter] = None,
        tencent_limiter: Optional[RateLimiter] = None,
        baostock_limiter: Optional[RateLimiter] = None,
        efinance_limiter: Optional[RateLimiter] = None,
    ):
        """
        纯路由 Stoke — 只组装 5 个数据源，不做缓存。

        Args:
            mootdx_limiter: mootdx 限流器（默认不限流）
            akshare_limiter: akshare 限流器（默认 5 秒）
            tencent_limiter: 腾讯限流器（默认 3 秒）
            baostock_limiter: baostock 限流器（默认 1 秒）
            efinance_limiter: efinance 限流器（默认 0.5 秒）

        需要缓存？用 StokeCached： from stoke.client_cached import StokeCached
        """
        self.mootdx = MootdxSource(rate_limiter=mootdx_limiter)
        self.akshare = AKShareSource(rate_limiter=akshare_limiter)
        self.tencent = TencentSource(rate_limiter=tencent_limiter)
        self.baostock = BaostockSource(rate_limiter=baostock_limiter)
        self.efinance = EFinanceSource(rate_limiter=efinance_limiter)
        logger.info("Stoke 初始化完成（5 源，纯路由）")

    @staticmethod
    def _safe_call(method_name: str, fn, *args, **kwargs):
        """统一错误包装：数据源异常 → Stoke 异常，上层可分类处理"""
        try:
            result = fn(*args, **kwargs)
            if isinstance(result, pd.DataFrame) and result.empty:
                logger.warning("%s 返回空 DataFrame", method_name)
            return result
        except (ConnectionError, TimeoutError, OSError) as e:
            logger.error("%s 网络异常: %s", method_name, e)
            raise NetworkError(f"{method_name} 网络异常: {e}") from e
        except SourceNotReadyError:
            raise
        except Exception as e:
            logger.error("%s 异常: %s", method_name, e)
            raise

    # ==================== 健康检查 ====================

    def health_check(self) -> dict:
        """
        检查所有数据源连通性

        Returns:
            dict，如 {"mootdx": True, "akshare": True, "tencent": True}
        """
        result = {
            "mootdx": self._safe_call("mootdx.health_check", self.mootdx.health_check),
            "akshare": self._safe_call("akshare.health_check", self.akshare.health_check),
            "tencent": self._safe_call("tencent.health_check", self.tencent.health_check),
            "baostock": self._safe_call("baostock.health_check", self.baostock.health_check),
            "efinance": self._safe_call("efinance.health_check", self.efinance.health_check),
        }
        status = "全部正常" if all(result.values()) else "部分异常"
        logger.info("全源健康检查: %s %s", result, status)
        return result

    # ==================== 行情（mootdx） ====================

    def realtime(self, symbols: List[str]) -> pd.DataFrame:
        """实时行情（含 5 档盘口）"""
        return self._safe_call("realtime", self.mootdx.get_realtime, symbols)

    def kline(
        self,
        symbol: str,
        frequency: int = 9,
        start: int = 0,
        offset: int = 800,
    ) -> pd.DataFrame:
        """历史 K 线，默认日线 800 条"""
        return self._safe_call("kline", self.mootdx.get_kline, symbol, frequency, start, offset)

    def stock_list(self) -> pd.DataFrame:
        """全市场股票列表"""
        return self._safe_call("stock_list", self.mootdx.get_stock_list)

    def f10(self, symbol: str) -> Optional[dict]:
        """F10 财务快照"""
        return self._safe_call("f10", self.mootdx.get_f10, symbol)

    # ==================== 新闻 & 研报 & 公告（akshare） ====================

    def news(self, symbol: str) -> pd.DataFrame:
        """个股新闻"""
        return self._safe_call("news", self.akshare.get_news, symbol)

    def telegraph(self) -> pd.DataFrame:
        """财联社电报快讯"""
        return self._safe_call("telegraph", self.akshare.get_cls_telegraph)

    def research(self, symbol: str) -> pd.DataFrame:
        """东财研报（含 PDF + 盈利预测）"""
        return self._safe_call("research", self.akshare.get_research_report, symbol)

    def announcements(self, symbol: str) -> pd.DataFrame:
        """巨潮公告"""
        return self._safe_call("announcements", self.akshare.get_announcements, symbol)

    # ==================== 信号（akshare） ====================

    def limit_up(self, date: Optional[str] = None) -> pd.DataFrame:
        """涨停板股票池"""
        return self._safe_call("limit_up", self.akshare.get_limit_up_pool, date)

    def strong_stocks(self, date: Optional[str] = None) -> pd.DataFrame:
        """强势涨停股（含题材归因）"""
        return self._safe_call("strong_stocks", self.akshare.get_strong_stocks, date)

    # ==================== 估值（tencent） ====================

    def index_pe(self, index_name: str = "上证50") -> pd.DataFrame:
        """指数 PE 历史"""
        return self._safe_call("index_pe", self.tencent.get_index_pe, index_name)

    def market_pb(self) -> pd.DataFrame:
        """全市场 PB 历史"""
        return self._safe_call("market_pb", self.tencent.get_market_pb)

    # ==================== 板块数据（mootdx + akshare） ====================

    def concepts(self) -> pd.DataFrame:
        """概念板块列表"""
        return self._safe_call("concepts", self.akshare.get_concept_list)

    def industries(self) -> pd.DataFrame:
        """行业板块列表"""
        return self._safe_call("industries", self.akshare.get_industry_list)

    def sector_members(self, sector_name: str) -> pd.DataFrame:
        """
        板块/指数成分股（通达信 block 数据库）

        Args:
            sector_name: 板块名称，如 '沪深300'、'创业板指'
        """
        return self._safe_call("sector_members", self.mootdx.get_sector_members, sector_name)

    def sector_kline(self, symbol: str = "银行",
                     start_date: str = "20250101",
                     end_date: str = "") -> pd.DataFrame:
        """
        行业板块指数 K 线

        Args:
            symbol: 行业板块名称，如 '银行'、'半导体'
            start_date: 起始日期（YYYYMMDD）
            end_date: 截止日期，默认最近交易日
        """
        return self._safe_call("sector_kline", self.akshare.get_sector_kline, symbol, start_date, end_date)

    def sector_rank(self) -> pd.DataFrame:
        """行业板块当日涨跌幅排名"""
        return self._safe_call("sector_rank", self.akshare.get_sector_rank)

    # ==================== 市场宽度（akshare） ====================

    def market_breadth(self) -> pd.DataFrame:
        """市场宽度：上证指数日线"""
        return self._safe_call("market_breadth", self.akshare.get_market_breadth)

    def market_volume(self) -> pd.DataFrame:
        """沪深两市每日成交额"""
        return self._safe_call("market_volume", self.akshare.get_market_volume)

    # ==================== 资金流（akshare） ====================

    def northbound_flow(self) -> pd.DataFrame:
        """北向资金历史每日成交净买额"""
        return self._safe_call("northbound_flow", self.akshare.get_northbound_flow)

    def dragon_tiger(self) -> pd.DataFrame:
        """龙虎榜营业部资金统计"""
        return self._safe_call("dragon_tiger", self.efinance.get_daily_billboard)

    def margin_shanghai(self) -> pd.DataFrame:
        """上海市场融资融券余额"""
        return self._safe_call("margin_shanghai", self.akshare.get_margin_shanghai)

    def margin_shenzhen(self) -> pd.DataFrame:
        """深圳市场融资融券余额"""
        return self._safe_call("margin_shenzhen", self.akshare.get_margin_shenzhen)

    def market_fund_flow(self) -> pd.DataFrame:
        """市场整体资金流（上证+深证）"""
        return self._safe_call("market_fund_flow", self.akshare.get_market_fund_flow)

    def individual_fund_flow(self, symbol: str) -> pd.DataFrame:
        """个股主力资金流向（含超大单/大单/中单/小单细分）"""
        return self._safe_call("individual_fund_flow", self.akshare.get_individual_fund_flow, symbol)

    # ==================== 情绪：热度（akshare 东财主力） ====================

    def hot_detail(self, symbol: str) -> pd.DataFrame:
        """【主力】东方财富个股热度详情（含新晋/铁杆粉丝比例、排名趋势）"""
        return self.akshare.get_hot_detail(symbol)

    def hot_latest(self, symbol: str) -> pd.DataFrame:
        """东方财富个股最新排名"""
        return self.akshare.get_hot_latest(symbol)

    def hot_realtime(self, symbol: str) -> pd.DataFrame:
        """东方财富个股当天实时排名变动（每 10 分钟）"""
        return self.akshare.get_hot_realtime(symbol)

    def hot_keywords(self) -> pd.DataFrame:
        """热搜关键词（概念题材维度）"""
        return self.akshare.get_hot_keywords()

    # ==================== 情绪：雪球热度（备选） ====================

    def xueqiu_hot(self, mode: str = "最热门") -> pd.DataFrame:
        """雪球沪深股市热度排行榜（讨论/交易/关注）"""
        return self.akshare.get_xueqiu_hot(mode)

    # ==================== 情绪：舆情评分（akshare） ====================

    def stock_comment_all(self) -> pd.DataFrame:
        """全市场千股千评"""
        return self.akshare.get_stock_comment_all()

    def stock_desire(self, symbol: str) -> pd.DataFrame:
        """个股参与意愿评分"""
        return self.akshare.get_stock_desire(symbol)

    def stock_focus(self, symbol: str) -> pd.DataFrame:
        """个股用户关注指数"""
        return self.akshare.get_stock_focus(symbol)

    # ==================== 情绪：跌停（akshare） ====================

    def limit_down(self, date: Optional[str] = None) -> pd.DataFrame:
        """跌停板股票池"""
        return self.akshare.get_limit_down_pool(date)

    # ==================== K 线复权（baostock） ====================

    def kline_baostock(
        self,
        symbol: str,
        frequency: str = "d",
        start_date: str = "2025-01-01",
        end_date: str = "",
        adjust: str = "none",
    ) -> pd.DataFrame:
        """
        获取复权 K 线（baostock，1 秒限流）

        Args:
            symbol: 如 'sh.600000' 或 'sz.000001'
            frequency: "d"(日), "w"(周), "m"(月), "5"(5分钟), "15"(15分钟)
            start_date: YYYY-MM-DD
            end_date: YYYY-MM-DD，默认今天
            adjust: "none"(不复权) / "qfq"(前复权) / "hfq"(后复权)
        """
        return self.baostock.get_kline(
            symbol, frequency, start_date, end_date, adjust,
        )

    def stock_industry(self) -> pd.DataFrame:
        """全市场股票行业分类（证监会标准）"""
        return self._safe_call("stock_industry", self.baostock.get_stock_industry)

    def all_stock(self, day: str = "") -> pd.DataFrame:
        """全市场股票列表（含退市/摘牌），day 默认最近交易日"""
        return self._safe_call("all_stock", self.baostock.get_all_stock, day)

    # ==================== K 线极速版（efinance） ====================

    def kline_efinance(
        self, symbol: str,
        start_date: str = "20250101",
        end_date: str = "",
    ) -> pd.DataFrame:
        """
        极速日 K 线（efinance，~0.3s，比 akshare 快 15 倍）

        Args:
            symbol: 6 位代码，如 '600519'
            start_date: YYYYMMDD
            end_date: YYYYMMDD，默认今天
        """
        return self.efinance.get_kline(symbol, start_date, end_date)

    def daily_billboard(self) -> pd.DataFrame:
        """今日龙虎榜 — 同 dragon_tiger()，保留别名兼容"""
        return self.dragon_tiger()

    def top10_holders(self, symbol: str) -> pd.DataFrame:
        """十大股东（efinance 独有）"""
        return self._safe_call("top10_holders", self.efinance.get_top10_holders, symbol)

    def holder_number(self, symbol: str) -> pd.DataFrame:
        """股东人数变化趋势（efinance 独有）"""
        return self._safe_call("holder_number", self.efinance.get_holder_number, symbol)

    def company_info(self, symbol: str) -> pd.DataFrame:
        """公司基本信息（efinance 独有）"""
        return self._safe_call("company_info", self.efinance.get_company_info, symbol)

