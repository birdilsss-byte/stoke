"""
发现层 — 注意力驱动的机会发现

不扫描 5000 只股票，只关注市场正在关注的东西。
5 条注意力通道：
  1. 涨停板 — 今日最强势股
  2. 强势股 — 含题材归因
  3. 热搜概念 — 市场关注焦点
  4. 北向资金 — 聪明钱方向
  5. 行业轮动 — 板块动量

所有数据通过 Stoke 获取（自动走缓存），不直接调 Source。
"""

import logging
from typing import List, Optional, TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from stoke.client import Stoke
    from stoke.context import MarketContext

logger = logging.getLogger(__name__)


class Discovery:
    """注意力驱动的机会发现"""

    def __init__(self, s: "Stoke", ctx: "MarketContext"):
        self.s = s
        self.ctx = ctx

    def scan(self, top_n: int = 20) -> List[dict]:
        """
        主入口：扫描候选标的

        流程：
          1. 涨停板 → 强势股 → 热搜概念 → 北向资金 → 行业轮动
          2. 五通道结果合并去重
          3. 按得分排序，取 top_n

        Returns:
            [{symbol, name, score, reason, source}]
        """
        logger.info("========== 发现层扫描开始 ==========")
        all_candidates = []

        # 通道 1：涨停板
        limit_up = self._channel_limit_up()
        all_candidates.extend(limit_up)

        # 通道 2：强势涨停（含题材归因）
        strong = self._channel_strong_stocks()
        all_candidates.extend(strong)

        # 通道 3：热搜概念股
        hot = self._channel_hot_concepts()
        all_candidates.extend(hot)

        # 通道 4：北向资金（聪明钱）
        northbound = self._channel_northbound()
        all_candidates.extend(northbound)

        # 通道 5：行业轮动
        sector = self._channel_sector_rotation()
        all_candidates.extend(sector)

        # 去重 + 排序
        unique = self._deduplicate(all_candidates)
        ranked = sorted(unique, key=lambda x: x["score"], reverse=True)

        self.ctx.candidates = ranked[:top_n]
        logger.info(
            "发现层扫描完成: %d 候选 → top %d",
            len(ranked), len(self.ctx.candidates),
        )
        return self.ctx.candidates

    # ---- 5 条注意力通道 ----

    def _channel_limit_up(self) -> List[dict]:
        """通道 1：涨停板"""
        try:
            df = self.s.limit_up()
            if df.empty:
                return []
            results = []
            for _, row in df.iterrows():
                score = min(row.get("board_count", 1) * 25, 100)
                results.append({
                    "symbol": row.get("symbol", ""),
                    "name": row.get("name", ""),
                    "score": score,
                    "reason": f"涨停({row.get('board_count', 1)}连板)",
                    "source": "limit_up",
                    "change_pct": row.get("change_pct", 0),
                })
            logger.debug("涨停板通道: %d 只", len(results))
            return results
        except Exception as e:
            logger.warning("涨停板通道异常: %s", e)
            return []

    def _channel_strong_stocks(self) -> List[dict]:
        """通道 2：强势涨停（含题材归因）"""
        try:
            df = self.s.strong_stocks()
            if df.empty:
                return []
            results = []
            for _, row in df.iterrows():
                reason = row.get("reason", "")
                score = 70  # 基础分
                if reason:
                    score += 15  # 有题材归因加分
                results.append({
                    "symbol": row.get("symbol", ""),
                    "name": row.get("name", ""),
                    "score": min(score, 100),
                    "reason": reason or "强势股",
                    "source": "strong_stocks",
                    "change_pct": row.get("change_pct", 0),
                })
            logger.debug("强势股通道: %d 只", len(results))
            return results
        except Exception as e:
            logger.warning("强势股通道异常: %s", e)
            return []

    def _channel_hot_concepts(self) -> List[dict]:
        """通道 3：热搜概念"""
        try:
            df = self.s.hot_keywords()
            if df.empty:
                return []
            seen = set()
            results = []
            for _, row in df.iterrows():
                sym = row.get("symbol", "")
                if sym and sym not in seen:
                    seen.add(sym)
                    results.append({
                        "symbol": sym,
                        "name": "",
                        "score": 60,
                        "reason": f"热搜概念: {row.get('concept_name', '')}",
                        "source": "hot_concepts",
                        "change_pct": 0,
                    })
            logger.debug("热搜概念通道: %d 只", len(results))
            return results
        except Exception as e:
            logger.warning("热搜概念通道异常: %s", e)
            return []

    def _channel_northbound(self) -> List[dict]:
        """通道 4：北向资金（聪明钱）"""
        try:
            df = self.s.northbound_flow()
            if df.empty:
                return []
            last = df.iloc[-1]
            net_buy = last.get("net_buy", 0) or 0
            if net_buy <= 0:
                logger.debug("北向资金净流出，跳过此通道")
                return []
            logger.debug("北向资金净流入: %.2f 亿", net_buy)
            return []  # 北向数据不含具体股票，仅记录方向
        except Exception as e:
            logger.warning("北向资金通道异常: %s", e)
            return []

    def _channel_sector_rotation(self) -> List[dict]:
        """通道 5：行业轮动 — 强势行业中的领头股"""
        try:
            df = self.s.sector_rank()
            if df.empty:
                return []
            results = []
            for _, row in df.head(5).iterrows():
                chg = row.get("change_pct", 0) or 0
                if chg > 1:
                    results.append({
                        "symbol": "",
                        "name": row.get("sector_name", ""),
                        "score": min(40 + chg, 80),
                        "reason": f"行业领涨: +{chg:.1f}%",
                        "source": "sector_rotation",
                        "change_pct": chg,
                    })
            logger.debug("行业轮动通道: %d 个行业", len(results))
            return results
        except Exception as e:
            logger.warning("行业轮动通道异常: %s", e)
            return []

    # ---- 辅助方法 ----

    def _deduplicate(self, candidates: List[dict]) -> List[dict]:
        """去重：同名股票保留最高分"""
        best = {}
        for c in candidates:
            key = c["symbol"] or c["name"]
            if not key:
                continue
            if key not in best or c["score"] > best[key]["score"]:
                best[key] = c
        return list(best.values())
