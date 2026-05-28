"""
前导探路 — 快速探测 5 源健康状态

在 FallbackStoke 初始化时运行，5 秒内出结果。
后续调用根据探测结果跳过死源、直连备用、优雅降级。
"""

import logging
import time
import requests

logger = logging.getLogger(__name__)

SOURCE_STATUS: dict = {
    "mootdx": None,
    "akshare": None,
    "baostock": None,
    "efinance": None,
    "tencent": None,
}


def probe_sources(stoke_raw, timeout: float = 3.0) -> dict:
    """
    快速探测 5 源健康状态，更新全局 SOURCE_STATUS。

    选取每个源最轻量的端点：
      mootdx:   kline('000001', offset=1)  → TCP
      akshare:  concept_list               → HTTP 东方财富
      baostock: health_check               → HTTP 证券宝
      efinance: daily_billboard            → HTTP 东方财富
      tencent:  qt.gtimg.cn 实时行情        → HTTP 腾讯

    Returns:
        dict {source_name: bool}
    """
    global SOURCE_STATUS
    results = {}

    # --- mootdx ---
    t0 = time.time()
    try:
        df = stoke_raw.mootdx.get_kline("000001", frequency=9, start=0, offset=1)
        results["mootdx"] = not df.empty
    except Exception as e:
        logger.warning("探路 mootdx 失败: %s", e)
        results["mootdx"] = False
    logger.debug("mootdx 探路: %s (%.2fs)", results["mootdx"], time.time() - t0)

    # --- akshare ---
    t0 = time.time()
    try:
        df = stoke_raw.akshare.get_concept_list()
        results["akshare"] = not df.empty
    except Exception as e:
        logger.warning("探路 akshare 失败: %s", e)
        results["akshare"] = False
    logger.debug("akshare 探路: %s (%.2fs)", results["akshare"], time.time() - t0)

    # --- baostock ---
    t0 = time.time()
    try:
        results["baostock"] = stoke_raw.baostock.health_check()
    except Exception as e:
        logger.warning("探路 baostock 失败: %s", e)
        results["baostock"] = False
    logger.debug("baostock 探路: %s (%.2fs)", results["baostock"], time.time() - t0)

    # --- efinance ---
    t0 = time.time()
    try:
        df = stoke_raw.efinance.get_daily_billboard()
        results["efinance"] = not df.empty
    except Exception as e:
        logger.warning("探路 efinance 失败: %s", e)
        results["efinance"] = False
    logger.debug("efinance 探路: %s (%.2fs)", results["efinance"], time.time() - t0)

    # --- tencent 直连 ---
    t0 = time.time()
    try:
        r = requests.get(
            "http://qt.gtimg.cn/q=sh600519",
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        results["tencent"] = r.status_code == 200 and "600519" in r.text
    except Exception as e:
        logger.warning("探路 tencent 失败: %s", e)
        results["tencent"] = False
    logger.debug("tencent 探路: %s (%.2fs)", results["tencent"], time.time() - t0)

    SOURCE_STATUS.update(results)

    alive = sum(1 for v in results.values() if v)
    logger.info("前导探路完成: %d/%d 源存活 %s", alive, len(results), results)
    return results


def is_source_alive(name: str) -> bool:
    """查询某个源是否存活（未探测过返回 True，乐观假设可用）"""
    return SOURCE_STATUS.get(name) is not False


def akshare_ok() -> bool:
    """快捷查询 akshare 是否可用"""
    return is_source_alive("akshare")
