"""
CninfoSource — 巨潮公告全文

数据源: cninfo.com.cn (HTTP, 零鉴权)
覆盖: 沪深北交所全量公告列表 + 公告全文 HTML + 公告 PDF 下载

关键: 动态 orgId 映射（szse_stock.json，6198 只股缓存），
      硬编码 gssx0{code} 降为 fallback。

参考: a-stock-data V3.2.4 §7.1
"""

import json
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


class CninfoSource:
    """巨潮公告数据源"""

    def __init__(self, rate_limiter: Optional[RateLimiter] = None):
        self.limiter = rate_limiter or RateLimiter(interval=RATE_LIMIT.get("cninfo", 1.0))
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": _UA})
        self._orgid_cache: dict = {}  # code -> orgId 映射缓存
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

    # ==================== orgId 动态解析 ====================

    def _resolve_org_id(self, code: str) -> str:
        """
        动态解析股票代码对应的 orgId。

        先从 szse_stock.json 缓存中查找，
        找不到则降级为 'gssx0{code}' 回退格式。
        """
        if code in self._orgid_cache:
            return self._orgid_cache[code]

        try:
            url = "https://www.cninfo.com.cn/new/data/szse_stock.json"
            r = self._session.get(url, timeout=10)
            data = r.json()
            stock_list = data.get("stockList", [])
            for s in stock_list:
                sc = s.get("code", "")
                if sc == code:
                    org_id = s.get("orgId", "")
                    if org_id:
                        self._orgid_cache[code] = org_id
                        logger.debug("orgId 解析: %s -> %s", code, org_id)
                        return org_id
        except Exception as e:
            logger.warning("orgId 映射表请求失败: %s", e)

        # fallback: 硬编码格式
        fallback = f"gssx0{code}"
        self._orgid_cache[code] = fallback
        logger.debug("orgId 回退: %s -> %s", code, fallback)
        return fallback

    # ==================== 公告列表 ====================

    @retry_on_failure()
    def get_announcements(self, symbol: str,
                          page_size: int = 30,
                          page_num: int = 1) -> pd.DataFrame:
        """
        巨潮个股公告列表。

        Args:
            symbol: 6 位股票代码
            page_size: 每页条数
            page_num: 页码

        Returns:
            DataFrame 列:
            announcementId       -- 公告 ID
            announcementTitle    -- 公告标题
            announcementTime     -- 公告时间 (YYYY-MM-DD HH:MM)
            adjunctUrl           -- 公告 PDF 下载相对路径
            announcementType     -- 公告类型
        """
        self.limiter.wait()
        org_id = self._resolve_org_id(symbol)
        params = {
            "stock": f"{org_id},{symbol}",
            "pageNum": str(page_num),
            "pageSize": str(page_size),
            "tabName": "fulltext",
            "seDate": "",
            "plate": "",
            "category": "",
            "trade": "",
        }
        logger.info("获取公告列表: %s (orgId=%s)", symbol, org_id)
        r = self._session.post(
            "http://www.cninfo.com.cn/new/hisAnnouncement/query",
            params=params, timeout=15,
            headers={"Referer": "http://www.cninfo.com.cn/"},
        )
        d = r.json()
        rows = (d.get("announcements") or
                d.get("result") or [])
        if not rows:
            logger.info("公告列表: %s 无数据", symbol)
            return pd.DataFrame()

        # 提取关键字段
        records = []
        for row in rows:
            records.append({
                "announcementId": row.get("announcementId", ""),
                "announcementTitle": row.get("announcementTitle", ""),
                "announcementTime": str(row.get("announcementTime", ""))[:19],
                "adjunctUrl": row.get("adjunctUrl", ""),
                "announcementType": row.get("announcementType", ""),
            })

        df = pd.DataFrame(records)
        logger.info("公告列表: %s %d 条", symbol, len(df))
        return df

    # ==================== 公告全文 ====================

    @retry_on_failure()
    def get_announcement_detail(self, announcement_id: str) -> str:
        """
        获取公告全文（HTML 文本）。

        Args:
            announcement_id: 公告 ID

        Returns:
            公告全文 HTML 字符串
        """
        self.limiter.wait()
        params = {"announcementId": announcement_id}
        logger.info("获取公告全文: %s", announcement_id)
        try:
            r = self._session.get(
                "http://www.cninfo.com.cn/new/disclosure/detail",
                params=params, timeout=15,
                headers={"Referer": "http://www.cninfo.com.cn/"},
            )
            # 尝试从页面提取公告正文内容
            text = r.text
            # 简单的 HTML 正文提取（cninfo 页面结构比较固定）
            if text and len(text) > 200:
                logger.info("公告全文: %s (%d 字符)", announcement_id, len(text))
                return text
            return ""
        except Exception as e:
            logger.warning("公告全文获取失败 %s: %s", announcement_id, e)
            return ""

    # ==================== 公告 PDF 下载 ====================

    def download_announcement_pdf(self, adjunct_url: str,
                                  target_dir: str = "./announcements") -> Optional[str]:
        """
        下载公告 PDF。

        不走 @retry_on_failure。

        Args:
            adjunct_url: 从 get_announcements 获得的 adjunctUrl 路径
            target_dir: 下载目录

        Returns:
            下载文件的本地路径，失败返回 None
        """
        if not adjunct_url:
            logger.warning("download_announcement_pdf: adjunct_url 为空")
            return None

        url = f"http://www.cninfo.com.cn/{adjunct_url}"
        fname = adjunct_url.split("/")[-1] if "/" in adjunct_url else adjunct_url
        target = Path(target_dir) / fname
        if target.exists():
            logger.info("公告 PDF 已存在: %s", target)
            return str(target)

        logger.info("下载公告 PDF: %s", url)
        try:
            self.limiter.wait()
            r = self._session.get(
                url, timeout=60,
                headers={"Referer": "http://www.cninfo.com.cn/"},
            )
            if r.status_code == 200 and len(r.content) >= 512:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(r.content)
                logger.info("公告 PDF 下载成功: %s (%d KB)", target, len(r.content) // 1024)
                return str(target)
            else:
                logger.warning("公告 PDF 下载失败: HTTP %d", r.status_code)
                return None
        except Exception as e:
            logger.warning("公告 PDF 下载异常: %s", e)
            return None
