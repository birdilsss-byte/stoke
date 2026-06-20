"""
EastMoneySource — 东方财富研报直连

数据源: reportapi.eastmoney.com (HTTP 公开 JSON API, 无 Key)
覆盖: 个股研报列表 + 行业研报列表 + PDF 下载

限流: 本模块提供东财全局共享限流 _em_rate_limit()，
      datacenter_source 通过 import 引用，避免跨源请求间隔不够。

参考: a-stock-data V3.2.4 §2.1
"""

import logging
import random
import time
import re
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

from stoke.config import RATE_LIMIT
from stoke.rate_limiter import RateLimiter
from stoke.utils import retry_on_failure

logger = logging.getLogger(__name__)

# ==================== 东财族全局共享限流 ====================

EM_SESSION = requests.Session()
EM_SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
})
EM_MIN_INTERVAL = 1.5          # 东财请求最小间隔（秒）
_EM_LAST_CALL = [0.0]          # 模块级上次请求时间戳


def _em_rate_limit():
    """
    东财族全局共享限流（线程建议：调用方自行保证单线程）。

    所有 eastmoney.com 端点共用此限流，确保批量任务不会因
    跨 Source 调用（如同时调 eastmoney + datacenter）而触犯风控。
    """
    now = time.time()
    elapsed = now - _EM_LAST_CALL[0]
    if elapsed < EM_MIN_INTERVAL:
        sleep_time = EM_MIN_INTERVAL - elapsed + random.uniform(0, 0.5)
        time.sleep(sleep_time)
    _EM_LAST_CALL[0] = time.time()


_REPORT_API = "https://reportapi.eastmoney.com/report/list"
_PDF_TPL = "https://pdf.dfcfw.com/pdf/H3_{info_code}_1.pdf"


class EastMoneySource:
    """东方财富研报数据源"""

    def __init__(self, rate_limiter: Optional[RateLimiter] = None):
        self.limiter = rate_limiter or RateLimiter(interval=RATE_LIMIT.get("eastmoney", 1.5))
        logger.info("EastMoneySource 初始化完成，限流 %.1fs", self.limiter.interval)

    # ==================== 连通性检查 ====================

    def health_check(self) -> bool:
        """取茅台最新一篇研报，验证连通性"""
        try:
            df = self.get_research_reports("600519", max_pages=1)
            ok = not df.empty
            logger.info("EastMoney 健康检查 %s", "通过" if ok else "失败")
            return ok
        except Exception as e:
            logger.warning("EastMoney 健康检查失败: %s", e)
            return False

    # ==================== 个股研报 ====================

    @retry_on_failure()
    def get_research_reports(self, symbol: str, max_pages: int = 5) -> pd.DataFrame:
        """
        东方财富个股研报列表（含盈利预测和 PDF 编号）。

        Args:
            symbol: 6 位股票代码，如 '600519'
            max_pages: 最多查询页数

        Returns:
            DataFrame 列:
            infoCode          -- PDF 编号（用于下载）
            title             -- 报告标题
            publishDate       -- 发布日期 (YYYY-MM-DD)
            orgSName          -- 机构名称
            emRatingName      -- 评级（买入/增持/中性/减持/卖出）
            predictThisYearEps   -- 预测本年 EPS
            predictNextYearEps   -- 预测明年 EPS
            indvInduName      -- 个股所属行业
        """
        logger.info("获取个股研报: %s (最多 %d 页)", symbol, max_pages)
        all_records = []
        for page in range(1, max_pages + 1):
            params = {
                "industryCode": "*", "pageSize": "100", "industry": "*",
                "rating": "*", "ratingChange": "*",
                "beginTime": "2000-01-01", "endTime": "2030-01-01",
                "pageNo": str(page), "fields": "", "qType": "0",
                "orgCode": "", "code": symbol, "rcode": "",
                "p": str(page), "pageNum": str(page), "pageNumber": str(page),
            }
            _em_rate_limit()
            r = EM_SESSION.get(
                _REPORT_API, params=params, timeout=30,
                headers={"Referer": "https://data.eastmoney.com/"},
            )
            d = r.json()
            rows = d.get("data") or []
            if not rows:
                break
            all_records.extend(rows)
            total_page = d.get("TotalPage", 1) or 1
            if page >= total_page:
                break

        if not all_records:
            return pd.DataFrame()

        df = pd.DataFrame(all_records)
        # 提取关键列
        cols = ["infoCode", "title", "publishDate", "orgSName",
                "emRatingName", "predictThisYearEps", "predictNextYearEps",
                "indvInduName"]
        exist_cols = [c for c in cols if c in df.columns]
        df = df[exist_cols].copy()
        if "publishDate" in df.columns:
            df["publishDate"] = pd.to_datetime(
                df["publishDate"], errors="coerce"
            ).dt.strftime("%Y-%m-%d")
        logger.info("个股研报: %s %d 条", symbol, len(df))
        return df

    # ==================== 行业研报 ====================

    @retry_on_failure()
    def get_industry_reports(self, industry_code: str = "*",
                             max_pages: int = 5) -> pd.DataFrame:
        """
        东方财富行业研报列表。

        同个股研报端点 reportlist，仅 qType=1。
        industry_code="*" 拉全行业；传东财行业码（如 "1238"=IT服务Ⅱ）精确过滤。
        行业名/行业码在每条 record 的 industryName/industryCode 字段。

        Args:
            industry_code: 行业代码，"*" 表示全行业
            max_pages: 最多页数

        Returns:
            DataFrame 列:
            infoCode       -- PDF 编号
            title          -- 报告标题
            publishDate    -- 发布日期
            orgSName       -- 机构名称
            industryName   -- 行业名称
            industryCode   -- 东财行业代码
            emRatingName   -- 行业评级
        """
        logger.info("获取行业研报: 行业码=%s (最多 %d 页)", industry_code, max_pages)
        all_records = []
        for page in range(1, max_pages + 1):
            params = {
                "industryCode": industry_code, "pageSize": "100", "industry": "*",
                "rating": "*", "ratingChange": "*",
                "beginTime": "2024-01-01", "endTime": "2030-01-01",
                "pageNo": str(page), "fields": "", "qType": "1",
                "orgCode": "", "code": "", "rcode": "",
                "p": str(page), "pageNum": str(page), "pageNumber": str(page),
            }
            _em_rate_limit()
            r = EM_SESSION.get(
                _REPORT_API, params=params, timeout=30,
                headers={"Referer": "https://data.eastmoney.com/"},
            )
            d = r.json()
            rows = d.get("data") or []
            if not rows:
                break
            all_records.extend(rows)
            total_page = d.get("TotalPage", 1) or 1
            if page >= total_page:
                break

        if not all_records:
            return pd.DataFrame()

        df = pd.DataFrame(all_records)
        cols = ["infoCode", "title", "publishDate", "orgSName",
                "industryName", "industryCode", "emRatingName"]
        exist_cols = [c for c in cols if c in df.columns]
        df = df[exist_cols].copy()
        if "publishDate" in df.columns:
            df["publishDate"] = pd.to_datetime(
                df["publishDate"], errors="coerce"
            ).dt.strftime("%Y-%m-%d")
        logger.info("行业研报: %s %d 条", industry_code, len(df))
        return df

    # ==================== PDF 下载 ====================

    def download_report_pdf(self, info_code: str,
                            target_dir: str = "./reports") -> Optional[str]:
        """
        根据 infoCode 下载研报 PDF。

        不走 @retry_on_failure（文件 I/O 不适合通用重试），
        不返回 DataFrame（返回文件路径字符串）。

        Args:
            info_code: 从研报列表获得的 infoCode
            target_dir: 下载目录

        Returns:
            下载文件的本地路径，失败返回 None
        """
        if not info_code:
            logger.warning("download_report_pdf: info_code 为空")
            return None

        url = _PDF_TPL.format(info_code=info_code)
        fname = f"{info_code}.pdf"
        target = Path(target_dir) / fname
        if target.exists():
            logger.info("PDF 已存在: %s", target)
            return str(target)

        logger.info("下载研报 PDF: %s", url)
        _em_rate_limit()
        try:
            r = EM_SESSION.get(
                url, timeout=60,
                headers={"Referer": "https://data.eastmoney.com/"},
            )
            if r.status_code == 200 and len(r.content) >= 1024:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(r.content)
                logger.info("PDF 下载成功: %s (%d KB)", target, len(r.content) // 1024)
                return str(target)
            else:
                logger.warning("PDF 下载失败: HTTP %d, size=%d", r.status_code, len(r.content))
                return None
        except Exception as e:
            logger.warning("PDF 下载异常: %s", e)
            return None
