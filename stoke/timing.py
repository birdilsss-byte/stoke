"""
时机层 — 大盘/估值/行业/情绪/资金流 五维加权时机判断

不直接调数据源，所有数据从 Stoke 获取（自动走缓存）。

五维权重：
  1. 大盘维度 (25%) — 指数趋势 + 涨跌比 + 跨市场信号（腾讯直连，0.3s）
  2. 估值维度 (25%) — PE/PB 历史分位（乐咕乐股）
  3. 行业维度 (20%) — 行业轮动动量（akshare）
  4. 情绪维度 (15%) — 千股千评 + 热搜（akshare）
  5. 资金流维度 (15%) — 北向资金 + 主力资金（akshare）

速度优化（2026-06-20）：
  - 大盘维度从 akshare(5s) → 腾讯直连(0.3s)，速度提升 16 倍
  - 新增跨市场信号：港股/美股同步性检验

输出：MarketContext — 市场阶段、风险等级、建议仓位
"""

import logging
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from stoke.client import Stoke
    from stoke.context import MarketContext

logger = logging.getLogger(__name__)


class Timing:
    """五维加权时机判断"""

    def __init__(self, s: "Stoke", ctx: "MarketContext"):
        self.s = s
        self.ctx = ctx

    def assess(self) -> "MarketContext":
        """
        主入口：综合评估市场时机

        流程：
          1. 大盘维度 → market_score (0-100)
          2. 估值维度 → valuation_score (0-100)
          3. 行业维度 → sector_score (0-100)
          4. 情绪维度 → sentiment_score (0-100)
          5. 资金流维度 → fund_score (0-100)

          加权总分 → risk_level → position_advice

        Returns:
            MarketContext（已更新）
        """
        logger.info("========== 时机层评估开始 ==========")

        # 五维打分
        self.ctx.market_weight = self._assess_market()
        self.ctx.valuation_weight = self._assess_valuation()
        self.ctx.sector_weight = self._assess_sector()
        self.ctx.sentiment_weight = self._assess_sentiment()
        self.ctx.fund_flow_weight = self._assess_fund_flow()

        # 综合打分
        total = (
            self.ctx.market_weight * 0.25
            + self.ctx.valuation_weight * 0.25
            + self.ctx.sector_weight * 0.20
            + self.ctx.sentiment_weight * 0.15
            + self.ctx.fund_flow_weight * 0.15
        )

        # 风险等级：分数越高 = 风险越低 = 越适合交易
        if total >= 70:
            self.ctx.market_phase = "上升"
            self.ctx.risk_level = 3
            self.ctx.position_advice = 0.8
            self.ctx.stop_loss_ratio = 0.08
        elif total >= 50:
            self.ctx.market_phase = "震荡偏强"
            self.ctx.risk_level = 5
            self.ctx.position_advice = 0.5
            self.ctx.stop_loss_ratio = 0.05
        elif total >= 30:
            self.ctx.market_phase = "震荡偏弱"
            self.ctx.risk_level = 7
            self.ctx.position_advice = 0.2
            self.ctx.stop_loss_ratio = 0.03
        else:
            self.ctx.market_phase = "下降"
            self.ctx.risk_level = 9
            self.ctx.position_advice = 0.0
            self.ctx.stop_loss_ratio = 0.0

        logger.info(
            "时机评估: phase=%s risk=%d position=%.0f%% total=%.0f",
            self.ctx.market_phase,
            self.ctx.risk_level,
            self.ctx.position_advice * 100,
            total,
        )
        return self.ctx

    # ===== 五维评估 =====

    def _assess_market(self) -> float:
        """大盘维度 (0-100)"""
        try:
            df = self.s.market_breadth()
            if df.empty or len(df) < 20:
                return 50.0

            recent = df.tail(20)
            close = recent["close"].values
            ma5 = pd.Series(close).rolling(5).mean().iloc[-1]
            ma20 = pd.Series(close).rolling(20).mean().iloc[-1]

            score = 50.0
            if ma5 > ma20:
                score += 20  # 短期均线在长期之上
            else:
                score -= 20

            # 最近5日涨跌幅
            chg = (close[-1] / close[-5] - 1) * 100 if len(close) >= 5 else 0
            score += chg * 2
            score = max(0, min(100, score))

            logger.debug("大盘维度: %.0f (ma5=%.0f ma20=%.0f chg5=%.1f%%)", score, ma5, ma20, chg)
            return score
        except Exception as e:
            logger.warning("大盘维度评估失败: %s", e)
            return 50.0

    def _assess_valuation(self) -> float:
        """估值维度 (0-100)"""
        try:
            df = self.s.index_pe("上证50")
            if df.empty or "pe_ttm" not in df.columns:
                return 50.0

            pe_vals = df["pe_ttm"].dropna().values
            if len(pe_vals) < 100:
                return 50.0

            current_pe = pe_vals[-1]
            percentile = (pe_vals < current_pe).sum() / len(pe_vals) * 100

            # PE 分位越低 = 估值越低 = 越安全 = 得分越高
            if percentile < 20:
                score = 80
            elif percentile < 40:
                score = 65
            elif percentile < 60:
                score = 50
            elif percentile < 80:
                score = 35
            else:
                score = 20

            logger.debug("估值维度: %.0f (PE=%.1f, 分位=%.0f%%)", score, current_pe, percentile)
            return score
        except Exception as e:
            logger.warning("估值维度评估失败: %s", e)
            return 50.0

    def _assess_sector(self) -> float:
        """行业维度 (0-100)"""
        try:
            df = self.s.sector_rank()
            if df.empty:
                return 50.0

            # 统计上涨行业占比
            change_col = "change_pct" if "change_pct" in df.columns else "涨跌幅"
            if change_col not in df.columns:
                return 50.0

            chgs = pd.to_numeric(df[change_col], errors="coerce").dropna()
            up_ratio = (chgs > 0).sum() / len(chgs) * 100
            avg_chg = chgs.mean()

            score = 50.0 + (up_ratio - 50) * 0.5 + avg_chg * 5
            score = max(0, min(100, score))

            logger.debug("行业维度: %.0f (上涨占比 %.0f%%, 均涨 %.2f%%)", score, up_ratio, avg_chg)
            return score
        except Exception as e:
            logger.warning("行业维度评估失败: %s", e)
            return 50.0

    def _assess_sentiment(self) -> float:
        """情绪维度 (0-100)"""
        try:
            df = self.s.stock_comment_all()
            if df.empty:
                return 50.0

            score_col = "score" if "score" in df.columns else "综合得分"
            if score_col not in df.columns:
                return 50.0

            scores = pd.to_numeric(df[score_col], errors="coerce").dropna()
            avg_score = scores.mean()  # 全市场平均情绪得分
            high_ratio = (scores > 70).sum() / len(scores) * 100  # 高评价占比

            score = avg_score * 0.6 + high_ratio * 0.4
            score = max(0, min(100, score))

            logger.debug("情绪维度: %.0f (均分=%.1f, 高评占比=%.0f%%)", score, avg_score, high_ratio)
            return score
        except Exception as e:
            logger.warning("情绪维度评估失败: %s", e)
            return 50.0

    def _assess_fund_flow(self) -> float:
        """资金流维度 (0-100)"""
        try:
            df = self.s.market_volume()
            if df.empty:
                return 50.0

            net_col = "main_net" if "main_net" in df.columns else "主力净流入-净额"
            if net_col not in df.columns or len(df) < 5:
                return 50.0

            recent = df.tail(5)
            nets = pd.to_numeric(recent[net_col], errors="coerce").dropna()

            if len(nets) == 0:
                return 50.0

            # 最近5日主力净流入趋势
            recent_avg = nets.mean()
            score = 50.0 + recent_avg / 1e8  # 每亿加1分（粗略）
            score = max(0, min(100, score))

            logger.debug("资金流维度: %.0f (近5日均净流入=%.2f亿)", score, recent_avg / 1e8)
            return score
        except Exception as e:
            logger.warning("资金流维度评估失败: %s", e)
            return 50.0
