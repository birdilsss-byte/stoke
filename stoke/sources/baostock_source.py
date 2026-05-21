"""
Baostock 数据源 — 证券宝 HTTP 协议

零注册、零 API Key，提供 A 股历史 K 线（含标准复权）、行业分类等数据。

与 mootdx 的差异：
  - 支持前复权 / 后复权（mootdx 不支持）
  - 提供证监会行业分类数据
  - HTTP 协议，速度比 mootdx TCP 慢，但比 akshare 快

⚠️ 每次查询前必须 login，查询后建议 logout。
本类提供自动懒登录 + 上下文管理器支持。
"""

import logging
from typing import Optional

import pandas as pd

from stoke.rate_limiter import RateLimiter
from stoke.config import RATE_LIMIT
from stoke.utils import retry_on_failure

logger = logging.getLogger(__name__)

# Baostock 复权类型
ADJUST_NONE = "1"   # 不复权
ADJUST_QFQ = "2"    # 前复权
ADJUST_HFQ = "3"    # 后复权


class BaostockSource:
    """Baostock 数据源，提供 A 股复权 K 线和行业分类"""

    def __init__(self, rate_limiter: Optional[RateLimiter] = None):
        self.limiter = rate_limiter or RateLimiter(interval=1.0)
        self._logged_in = False
        logger.info("BaostockSource 初始化，限流间隔 %.1f 秒", self.limiter.interval)

    def _ensure_login(self):
        """确保已登录，首次调用时自动登录；连接断开时自动重连"""
        import baostock as bs
        if self._logged_in:
            return
        lg = bs.login()
        if lg.error_code != "0":
            raise ConnectionError(f"Baostock 登录失败: {lg.error_msg}")
        self._logged_in = True
        logger.debug("Baostock 登录成功")

    def _reconnect(self):
        """强制重连（用于 Bad file descriptor 等连接异常）"""
        import baostock as bs
        try:
            bs.logout()
        except Exception:
            pass
        self._logged_in = False
        self._ensure_login()

    def _safe_call(self, fn, *args, **kwargs):
        """调用 baostock 函数，连接异常时自动重连一次"""
        try:
            return fn(*args, **kwargs)
        except OSError:
            logger.warning("Baostock 连接异常，尝试重连...")
            self._reconnect()
            return fn(*args, **kwargs)

    def health_check(self) -> bool:
        """连通性检查：登录 + 查询一只股票"""
        try:
            self._ensure_login()
            import baostock as bs
            rs = bs.query_history_k_data_plus(
                "sh.600000", "date,close",
                start_date="2026-05-20", end_date="2026-05-21",
                frequency="d", adjustflag="1",
            )
            ok = rs.next() is True
            logger.info("Baostock 健康检查 %s", "通过" if ok else "失败")
            return ok
        except Exception as e:
            logger.warning("Baostock 健康检查失败: %s", e)
            return False

    def close(self):
        """主动注销登录"""
        if self._logged_in:
            try:
                import baostock as bs
                bs.logout()
                self._logged_in = False
                logger.debug("Baostock 已注销")
            except Exception as e:
                logger.warning("Baostock 注销异常: %s", e)

    def __enter__(self):
        self._ensure_login()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # ---------- K 线（含复权） ----------

    @retry_on_failure()
    def get_kline(
        self,
        symbol: str,
        frequency: str = "d",
        start_date: str = "2025-01-01",
        end_date: str = "",
        adjust: str = "none",
    ) -> pd.DataFrame:
        """
        获取日 K 线数据（含复权支持）

        Args:
            symbol: 股票代码，如 'sh.600000' 或 'sz.000001'
            frequency: 周期，"d"=日线，"w"=周线，"m"=月线，"5"=5分钟，"15"=15分钟
            start_date: 起始日期 YYYY-MM-DD
            end_date: 截止日期 YYYY-MM-DD，默认今天
            adjust: 复权方式，"none"(不复权) / "qfq"(前复权) / "hfq"(后复权)

        Returns:
            DataFrame，含 date、open、high、low、close、volume、amount 列
        """
        adjust_map = {"none": "1", "qfq": "2", "hfq": "3"}
        adjustflag = adjust_map.get(adjust, "1")

        self._ensure_login()
        self.limiter.wait()

        import baostock as bs
        from datetime import date

        if not end_date:
            end_date = date.today().strftime("%Y-%m-%d")

        logger.info(
            "Baostock K 线: %s (adjust=%s, %s ~ %s)",
            symbol, adjust, start_date, end_date,
        )

        rs = self._safe_call(
            bs.query_history_k_data_plus,
            symbol,
            "date,open,high,low,close,volume,amount",
            start_date=start_date,
            end_date=end_date,
            frequency=frequency,
            adjustflag=adjustflag,
        )

        rows = []
        while rs.next():
            row = rs.get_row_data()
            if row and row[0]:
                rows.append(row)

        if not rows:
            logger.warning("Baostock K 线返回空: %s", symbol)
            return pd.DataFrame()

        df = pd.DataFrame(rows, columns=[
            "date", "open", "high", "low", "close", "volume", "amount",
        ])

        # 类型转换
        for col in ["open", "high", "low", "close", "amount"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").astype("int64")
        df["date"] = pd.to_datetime(df["date"])

        logger.info("Baostock K 线: %s 共 %d 条", symbol, len(df))
        return df

    # ---------- 行业分类 ----------

    @retry_on_failure()
    def get_stock_industry(self) -> pd.DataFrame:
        """
        全市场股票行业分类（证监会标准）

        Returns:
            DataFrame，含 updateDate、code、code_name、industry、industryClassification 列
        """
        self._ensure_login()
        self.limiter.wait()

        import baostock as bs
        logger.info("获取 Baostock 行业分类")
        rs = bs.query_stock_industry()

        rows = []
        while rs.next():
            row = rs.get_row_data()
            if row and row[0]:
                rows.append(row)

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows, columns=rs.fields)
        logger.info("Baostock 行业分类: %d 条", len(df))
        return df

    # ---------- 股票列表 ----------

    @retry_on_failure()
    def get_all_stock(self, day: str = "") -> pd.DataFrame:
        """
        获取全市场股票列表（含退市和已摘牌）

        Args:
            day: 交易日期 YYYY-MM-DD，默认最近交易日

        Returns:
            DataFrame，含 code、tradeStatus、code_name 列
        """
        self._ensure_login()
        self.limiter.wait()

        import baostock as bs
        from datetime import date

        if not day:
            from datetime import timedelta
            day = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")

        logger.info("获取 Baostock 股票列表: %s", day)
        rs = bs.query_all_stock(day=day)

        rows = []
        while rs.next():
            row = rs.get_row_data()
            if row and row[0]:
                rows.append(row)

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows, columns=rs.fields)
        logger.info("Baostock 股票列表: %d 条", len(df))
        return df
