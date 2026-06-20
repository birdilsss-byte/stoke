"""
CninfoSource — 东财公告列表（替代巨潮 cninfo 直连）

数据源: np-anotice-stock.eastmoney.com (HTTP, 零鉴权)
覆盖: 沪深北交所个股公告列表 + 公告详情页 + 公告 PDF 下载

说明: 原设计对接巨潮 cninfo.com.cn 直连 API，但该 API 已不稳定（2026-06
      实测返回 500）。转而使用东财公告 API——这也是 akshare 底层实际使用的
      接口，与 store.py 中现有 announcements 表同源但更可控。

参考: akshare stock_fundamental/stock_notice.py
"""

import logging
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

from stoke.config import RATE_LIMIT
from stoke.rate_limiter import RateLimiter
from stoke.utils import retry_on_failure

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_NOTICE_API = "https://np-anotice-stock.eastmoney.com/api/security/ann"
_NOTICE_DETAIL_URL = "https://data.eastmoney.com/notices/detail/"

# 公告类型映射
_REPORT_MAP = {
    "全部": "0",
    "重大事项": "1",
    "财务报告": "2",
    "融资公告": "3",
    "风险提示": "4",
    "资产重组": "5",
    "信息变更": "6",
    "持股变动": "7",
}


class CninfoSource:
    """东财公告列表数据源"""

    def __init__(self, rate_limiter: Optional[RateLimiter] = None):
        self.limiter = rate_limiter or RateLimiter(interval=RATE_LIMIT.get("cninfo", 1.0))
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": _UA})
        logger.info("CninfoSource 初始化完成，限流 %.1fs", self.limiter.interval)

    # ==================== 连通性检查 ====================

    def health_check(self) -> bool:
        """查平安银行公告，验证连通性"""
        try:
            df = self.get_announcements("000001", page_size=5)
            ok = not df.empty
            logger.info("CninfoSource 健康检查 %s", "通过" if ok else "失败")
            return ok
        except Exception as e:
            logger.warning("CninfoSource 健康检查失败: %s", e)
            return False

    # ==================== 公告列表 ====================

    @retry_on_failure()
    def get_announcements(self, symbol: str,
                          page_size: int = 100,
                          page_num: int = 1,
                          report_type: str = "全部",
                          begin_date: str = "",
                          end_date: str = "") -> pd.DataFrame:
        """
        东财个股公告列表。

        Args:
            symbol: 6 位股票代码
            page_size: 每页条数（默认 100）
            page_num: 页码
            report_type: 公告类型
            begin_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD

        Returns:
            DataFrame 列:
            title         -- 公告标题
            noticeDate    -- 公告日期
            artCode       -- 公告编码
            stockList     -- 股票列表
            noticeType    -- 公告类型
            url           -- 东财公告详情 URL
        """
        self.limiter.wait()
        f_node = _REPORT_MAP.get(report_type, "0")
        params = {
            "sr": "-1",
            "page_size": str(page_size),
            "page_index": str(page_num),
            "ann_type": "A",
            "client_source": "web",
            "f_node": f_node,
            "s_node": "0",
            "stock_list": symbol,
        }
        if begin_date:
            params["begin_time"] = begin_date
        if end_date:
            params["end_time"] = end_date

        logger.info("获取公告列表: %s (page=%d, type=%s)", symbol, page_num, report_type)
        try:
            r = self._session.get(
                _NOTICE_API, params=params, timeout=15,
                headers={"Referer": "https://data.eastmoney.com/"},
            )
            d = r.json()
            data = d.get("data") or {}
            items = data.get("list") or []
        except Exception as e:
            logger.warning("公告列表请求失败 %s: %s", symbol, e)
            return pd.DataFrame()

        if not items:
            logger.info("公告列表: %s 无数据", symbol)
            return pd.DataFrame()

        records = []
        for item in items:
            art_code = item.get("art_code", "")
            codes = item.get("codes") or []
            code = codes[0].get("code", symbol) if codes else symbol
            records.append({
                "title": item.get("title", ""),
                "noticeDate": str(item.get("notice_date", ""))[:10],
                "artCode": art_code,
                "noticeType": item.get("columns", [{}])[0].get("column_name", "")
                           if item.get("columns") else "",
                "url": f"{_NOTICE_DETAIL_URL}{code}/{art_code}.html" if art_code else "",
            })

        df = pd.DataFrame(records)
        logger.info("公告列表: %s %d 条", symbol, len(df))
        return df

    # ==================== 公告详情 ====================

    @retry_on_failure()
    def get_announcement_detail(self, symbol: str,
                                art_code: str) -> str:
        """
        获取公告详情页 HTML。

        Args:
            symbol: 6 位股票代码
            art_code: 公告编码

        Returns:
            公告详情页 HTML 字符串
        """
        self.limiter.wait()
        url = f"{_NOTICE_DETAIL_URL}{symbol}/{art_code}.html"
        logger.info("获取公告详情: %s", url)
        try:
            r = self._session.get(
                url, timeout=15,
                headers={"Referer": "https://data.eastmoney.com/"},
            )
            if r.status_code == 200 and len(r.text) > 200:
                logger.info("公告详情: %s (%d 字符)", art_code, len(r.text))
                return r.text
            return ""
        except Exception as e:
            logger.warning("公告详情获取失败 %s: %s", art_code, e)
            return ""

    # ==================== 公告 PDF 下载 ====================

    def download_announcement_pdf(self, url: str,
                                  target_dir: str = "./announcements") -> Optional[str]:
        """
        下载公告 PDF。

        不走 @retry_on_failure。

        Args:
            url: 公告详情 URL（从 get_announcements 获得的 url 列）
            target_dir: 下载目录

        Returns:
            下载文件的本地路径，失败返回 None
        """
        if not url:
            logger.warning("download_announcement_pdf: url 为空")
            return None

        fname = url.split("/")[-1].replace(".html", ".pdf") if "/" in url else "announcement.pdf"
        target = Path(target_dir) / fname
        if target.exists():
            logger.info("公告 PDF 已存在: %s", target)
            return str(target)

        logger.info("下载公告: %s", url)
        try:
            self.limiter.wait()
            r = self._session.get(
                url, timeout=60,
                headers={"Referer": "https://data.eastmoney.com/"},
            )
            if r.status_code == 200 and len(r.content) >= 512:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(r.content)
                logger.info("公告下载成功: %s (%d KB)", target, len(r.content) // 1024)
                return str(target)
            else:
                logger.warning("公告下载失败: HTTP %d", r.status_code)
                return None
        except Exception as e:
            logger.warning("公告下载异常: %s", e)
            return None
