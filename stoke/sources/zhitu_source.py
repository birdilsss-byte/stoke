
"""
智兔数服数据源 — 免费 REST API（每日 200 次请求）

官网: https://www.zhituapi.com
Base URL: https://api.zhituapi.com/hs
Token 申请: https://www.zhituapi.com/gettoken.html

优势：
  - RESTful JSON API，比通达信 TCP 协议更易对接
  - 实时行情一站返回 PE/PB/市值/换手率
  - 免费版 200 次/日，低频量化绰绰有余
  - 无需实名认证

使用前需设置环境变量:
  export ZHITU_API_TOKEN="your_token"
  测试 Token: ZHITU_TOKEN_LIMIT_TEST（仅限 000001）
"""

import os
import logging
from typing import Optional, List

import requests
import pandas as pd

from stoke.rate_limiter import RateLimiter
from stoke.utils import retry_on_failure

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.zhituapi.com/hs"


class ZhituSource:
    """智兔数服 REST API 数据源"""

    def __init__(
        self,
        token: Optional[str] = None,
        base_url: Optional[str] = None,
        rate_limiter: Optional[RateLimiter] = None,
    ):
        self.token = token or os.environ.get("ZHITU_API_TOKEN", "")
        self.base_url = base_url or DEFAULT_BASE_URL
        self.limiter = rate_limiter or RateLimiter(interval=1.0)
        self._session = requests.Session()

        if not self.token:
            logger.warning(
                "智兔数服 Token 未设置！请设置环境变量 ZHITU_API_TOKEN。"
                "测试 Token: ZHITU_TOKEN_LIMIT_TEST（仅限 000001）。"
                "申请地址: https://www.zhituapi.com/gettoken.html"
            )
        else:
            logger.info("智兔数服初始化，Base URL: %s", self.base_url)

    @staticmethod
    def _to_api_code(symbol: str) -> str:
        """6 位代码 → 智兔 API 格式（000001.SZ / 600000.SH）"""
        if "." in symbol:
            return symbol
        suffix = "SH" if symbol.startswith("6") else "SZ"
        return f"{symbol}.{suffix}"

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        """GET 请求封装，自动附加 token"""
        if not self.token:
            raise RuntimeError("智兔数服 Token 未设置")
        params = params or {}
        params["token"] = self.token
        url = f"{self.base_url}{path}"
        logger.debug("智兔请求: %s", url)
        resp = self._session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def health_check(self) -> bool:
        """连通性检查：获取 000001 实时数据"""
        try:
            data = self._get("/latest/ma/000001/d")
            ok = isinstance(data, dict) and len(data) > 0
            logger.info("智兔数服 健康检查 %s", "通过" if ok else "失败")
            return ok
        except Exception as e:
            logger.warning("智兔数服 健康检查失败: %s", e)
            return False

    # ---------- 股票列表 ----------

    @retry_on_failure()
    def get_stock_list(self) -> pd.DataFrame:
        """
        全市场 A 股股票列表

        Returns:
            DataFrame，含 code、name 等列
        """
        self.limiter.wait()
        logger.info("智兔数服 获取股票列表")
        data = self._get("/list/all")
        if isinstance(data, list):
            return pd.DataFrame(data)
        return pd.DataFrame()

    # ---------- 实时行情 ----------

    @retry_on_failure()
    def get_realtime(self, symbol: str) -> dict:
        """
        实时行情快照（含 PE/PB/市值/换手率）

        Args:
            symbol: 6 位股票代码，如 '000001'

        Returns:
            dict，含 最新价、涨跌幅、PE、PB、总市值、换手率、
            分时 MA 数据等
        """
        self.limiter.wait()
        logger.info("智兔数服 实时行情: %s", symbol)
        code = self._to_api_code(symbol)
        return self._get(f"/latest/ma/{code}/d")

    @retry_on_failure()
    def get_realtime_batch(self, symbols: List[str]) -> pd.DataFrame:
        """
        多股票实时行情（一次请求）

        Args:
            symbols: 股票代码列表，如 ['000001', '600000']

        Returns:
            DataFrame，含多只股票的实时快照
        """
        self.limiter.wait()
        codes = ",".join(symbols)
        logger.info("智兔数服 批量实时行情: %d 只", len(symbols))
        data = self._get("/custom/ssjymore", {"stock_codes": codes})
        if isinstance(data, list):
            return pd.DataFrame(data)
        return pd.DataFrame()

    # ---------- 历史 K 线 ----------

    @retry_on_failure()
    def get_kline(
        self,
        symbol: str,
        start_date: str = "20250101",
        end_date: str = "",
        days: int = 100,
    ) -> pd.DataFrame:
        """
        历史日 K 线数据

        Args:
            symbol: 6 位股票代码
            start_date: 起始日期 YYYYMMDD
            end_date: 截止日期 YYYYMMDD
            days: 获取天数

        Returns:
            DataFrame，含 OHLCV 等列
        """
        self.limiter.wait()
        logger.info("智兔数服 K 线: %s (%s ~ %s)", symbol, start_date, end_date or "today")
        code = self._to_api_code(symbol)
        params = {"st": start_date}
        if end_date:
            params["et"] = end_date
        data = self._get(f"/history/{code}/d/{days}", params)
        if isinstance(data, list):
            return pd.DataFrame(data)
        return pd.DataFrame()

    # ---------- 技术指标 ----------

    @retry_on_failure()
    def get_macd(
        self,
        symbol: str,
        start_date: str = "20250101",
        end_date: str = "",
        days: int = 100,
    ) -> pd.DataFrame:
        """MACD 指标历史"""
        self.limiter.wait()
        code = self._to_api_code(symbol)
        params = {"st": start_date}
        if end_date:
            params["et"] = end_date
        return pd.DataFrame(
            self._get(f"/history/macd/{code}/d/{days}", params)
        )

    @retry_on_failure()
    def get_kdj(
        self,
        symbol: str,
        start_date: str = "20250101",
        end_date: str = "",
        days: int = 100,
    ) -> pd.DataFrame:
        """KDJ 指标历史"""
        self.limiter.wait()
        code = self._to_api_code(symbol)
        params = {"st": start_date}
        if end_date:
            params["et"] = end_date
        return pd.DataFrame(
            self._get(f"/history/kdj/{symbol}/d/{days}", params)
        )
