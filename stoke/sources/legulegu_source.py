"""
乐咕乐股数据源 — 纯 requests 直连，零 akshare 依赖

提供：指数 PE 历史、全市场 PB 历史。
端点: legulegu.com/api/，MD5 token 认证。
"""

import logging
from hashlib import md5
from datetime import datetime
from typing import Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup

from stoke.rate_limiter import RateLimiter
from stoke.config import RATE_LIMIT
from stoke.utils import retry_on_failure

logger = logging.getLogger(__name__)

# 指数名 → legulegu 代码映射
INDEX_MAP = {
    "上证50": "000016.SH",
    "沪深300": "000300.SH",
    "上证380": "000009.SH",
    "创业板50": "399673.SZ",
    "中证500": "000905.SH",
    "上证180": "000010.SH",
    "深证红利": "399324.SZ",
    "深证100": "399330.SZ",
    "中证1000": "000852.SH",
    "上证红利": "000015.SH",
    "中证100": "000903.SH",
    "中证800": "000906.SH",
}


def _make_token() -> str:
    """生成 legulegu API token（当前日期的 MD5）"""
    return md5(datetime.now().date().isoformat().encode()).hexdigest()


def _get_session_with_csrf(referer: str) -> tuple:
    """获取带 CSRF token 的 session"""
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    })
    r = session.get(referer, timeout=10)
    soup = BeautifulSoup(r.text, "html.parser")
    csrf_tag = soup.find(name="meta", attrs={"name": "_csrf"})
    if csrf_tag:
        session.headers["X-CSRF-Token"] = csrf_tag.attrs["content"]
    return session, r.cookies


class LeguleguSource:
    """乐咕乐股估值数据源 — 纯 requests 直连"""

    def __init__(self, rate_limiter: Optional[RateLimiter] = None):
        self.limiter = rate_limiter or RateLimiter(interval=RATE_LIMIT.get("legulegu", 1.0))
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        })
        logger.info("LeguleguSource 初始化，限流间隔 %.1f 秒", self.limiter.interval)

    def health_check(self) -> bool:
        """连通性检查：获取全市场 PB"""
        try:
            df = self.get_market_pb()
            ok = len(df) > 0
            logger.info("Legulegu 健康检查 %s", "通过" if ok else "失败(数据为空)")
            return ok
        except Exception as e:
            logger.warning("Legulegu 健康检查失败: %s", e)
            return False

    # ---------- 指数 PE ----------

    @retry_on_failure()
    def get_index_pe(self, index_name: str = "上证50") -> pd.DataFrame:
        """
        获取指数 PE（市盈率）历史

        Args:
            index_name: 指数名称，如 "上证50"、"沪深300"

        Returns:
            DataFrame，含 日期、指数点位、静态市盈率、滚动市盈率等列
        """
        self.limiter.wait()

        index_code = INDEX_MAP.get(index_name)
        if not index_code:
            raise ValueError(f"不支持的指数: {index_name}，可选: {list(INDEX_MAP.keys())}")

        logger.info("获取指数 PE: %s (%s)", index_name, index_code)

        session, cookies = _get_session_with_csrf(
            "https://legulegu.com/stockdata/sz50-ttm-lyr"
        )
        token = _make_token()

        r = session.get(
            "https://legulegu.com/api/stockdata/index-basic-pe",
            params={"token": token, "indexCode": index_code},
            cookies=cookies,
            timeout=15,
        )
        data = r.json()

        if "data" not in data:
            logger.warning("Legulegu 指数 PE 返回无 data 字段: %s", index_name)
            return pd.DataFrame()

        df = pd.DataFrame(data["data"])
        df["date"] = pd.to_datetime(df["date"], utc=True).dt.tz_convert(
            "Asia/Shanghai"
        ).dt.date

        # 标准化列名
        col_map = {
            "date": "日期",
            "close": "指数",
            "lyrPe": "等权静态市盈率",
            "addLyrPe": "静态市盈率",
            "middleLyrPe": "静态市盈率中位数",
            "ttmPe": "等权滚动市盈率",
            "addTtmPe": "滚动市盈率",
            "middleTtmPe": "滚动市盈率中位数",
        }
        keep_cols = [c for c in col_map if c in df.columns]
        df = df[keep_cols].rename(columns={k: v for k, v in col_map.items() if k in keep_cols})

        logger.info("Legulegu 指数 PE: %s 共 %d 条", index_name, len(df))
        return df

    # ---------- 全市场 PB ----------

    @retry_on_failure()
    def get_market_pb(self) -> pd.DataFrame:
        """
        获取全市场 PB（市净率）历史

        Returns:
            DataFrame，含 date、middlePB、equalWeightAveragePB、close 等列
        """
        self.limiter.wait()
        logger.info("获取全市场 PB")

        session, cookies = _get_session_with_csrf(
            "https://legulegu.com/stockdata/all-pb"
        )
        token = _make_token()

        r = session.get(
            "https://legulegu.com/api/stock-data/market-index-pb",
            params={"marketId": "ALL", "token": token},
            cookies=cookies,
            timeout=15,
        )
        data = r.json()

        if "data" not in data:
            logger.warning("Legulegu 全市场 PB 返回无 data 字段")
            return pd.DataFrame()

        df = pd.DataFrame(data["data"])
        df["date"] = pd.to_datetime(df["date"], utc=True).dt.tz_convert(
            "Asia/Shanghai"
        ).dt.date

        if "weightingAveragePB" in df.columns:
            df = df.drop(columns=["weightingAveragePB"])

        logger.info("Legulegu 全市场 PB: %d 条", len(df))
        return df
