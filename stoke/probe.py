"""
前导探路 — 快速探测 5 源健康状态

在 Stoke 初始化时运行，5 秒内出结果。
后续调用根据探测结果跳过死源、直连备用、优雅降级。

用法::
    from stoke.probe import probe_sources, SOURCE_STATUS
    status = probe_sources()
    # {"mootdx": True, "akshare": True, "baostock": True, "efinance": True, "tencent": True}
"""

import logging
import requests

logger = logging.getLogger(__name__)

# 全局探测结果，模块级单例
SOURCE_STATUS: dict = {
    "mootdx": None,
    "akshare": None,
    "baostock": None,
    "efinance": None,
    "tencent": None,
}


def probe_sources(stoke_raw=None, timeout: float = 3.0) -> dict:
    """
    快速探测 5 源健康状态，更新全局 SOURCE_STATUS。

    选取每个源最轻量的端点：
      mootdx:   kline('000001', offset=1)   → TCP 通达信
      akshare:  concept_list                → 东方财富概念板块
      baostock: health_check                → 证券宝登录+查询
      efinance: daily_billboard             → 东方财富龙虎榜
      tencent:  qt.gtimg.cn 实时行情         → 腾讯财经 HTTP

    Args:
        stoke_raw: 可选，已有的 Stoke 裸实例
        timeout: 单个探测超时秒数

    Returns:
        dict {source_name: bool}
    """
    global SOURCE_STATUS
    import time

    results = {}

    # --- mootdx (TCP) ---
    _t0 = time.time()
    try:
        if stoke_raw:
            df = stoke_raw.mootdx.get_kline("000001", frequency=9, start=0, offset=1)
            results["mootdx"] = not df.empty
        else:
            from stoke.sources.mootdx_source import MootdxSource
            ms = MootdxSource()
            df = ms.get_kline("000001", frequency=9, start=0, offset=1)
            results["mootdx"] = not df.empty
    except Exception as e:
        logger.warning("探路 mootdx 失败: %s", e)
        results["mootdx"] = False
    logger.debug("mootdx 探路: %s (%.2fs)", results["mootdx"], time.time() - _t0)

    # --- akshare (HTTP, 东方财富) ---
    _t0 = time.time()
    try:
        if stoke_raw:
            df = stoke_raw.akshare.get_concept_list()
            results["akshare"] = not df.empty
        else:
            from stoke.sources.akshare_source import AKShareSource
            aks = AKShareSource()
            df = aks.get_concept_list()
            results["akshare"] = not df.empty
    except Exception as e:
        logger.warning("探路 akshare 失败: %s", e)
        results["akshare"] = False
    logger.debug("akshare 探路: %s (%.2fs)", results["akshare"], time.time() - _t0)

    # --- baostock (HTTP) ---
    _t0 = time.time()
    try:
        if stoke_raw:
            ok = stoke_raw.baostock.health_check()
        else:
            from stoke.sources.baostock_source import BaostockSource
            bs = BaostockSource()
            ok = bs.health_check()
            bs.close()
        results["baostock"] = ok
    except Exception as e:
        logger.warning("探路 baostock 失败: %s", e)
        results["baostock"] = False
    logger.debug("baostock 探路: %s (%.2fs)", results["baostock"], time.time() - _t0)

    # --- efinance (HTTP, 东方财富) ---
    _t0 = time.time()
    try:
        if stoke_raw:
            df = stoke_raw.efinance.get_daily_billboard()
            results["efinance"] = not df.empty
        else:
            from stoke.sources.efinance_source import EFinanceSource
            ef = EFinanceSource()
            df = ef.get_daily_billboard()
            results["efinance"] = not df.empty
    except Exception as e:
        logger.warning("探路 efinance 失败: %s", e)
        results["efinance"] = False
    logger.debug("efinance 探路: %s (%.2fs)", results["efinance"], time.time() - _t0)

    # --- tencent 直连 (HTTP, qt.gtimg.cn) ---
    _t0 = time.time()
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
    logger.debug("tencent 探路: %s (%.2fs)", results["tencent"], time.time() - _t0)

    # 更新全局状态
    SOURCE_STATUS.update(results)

    alive = sum(1 for v in results.values() if v)
    logger.info(
        "前导探路完成: %d/%d 源存活 %s",
        alive, len(results), results,
    )

    return results


def is_source_alive(name: str) -> bool:
    """查询某个源是否存活（未探测过返回 True，乐观假设可用）"""
    status = SOURCE_STATUS.get(name)
    return status is not False  # None（未探测）或 True 都视为可用


def akshare_ok() -> bool:
    """快捷查询 akshare 是否可用"""
    return is_source_alive("akshare")
